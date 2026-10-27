"""Explicit benchmark modes and credential-free request/response recording."""

import json
import time
from urllib.error import HTTPError
from urllib.request import Request
from ..security import open_api_request as urlopen

from ..openrouter import DECISION_MODELS, DECISIONS_URL, load_api_key, matched_payload, signal_question
from ..sol import CHAT_URL, SOL_MODEL, sol_payload
from .problem import CURRENT_OBJECTIVE, fingerprint


REMOTE_MODELS = {**DECISION_MODELS, "sol-medium": SOL_MODEL}


def payload_for(instance, name, mode):
    if instance.objective != CURRENT_OBJECTIVE:
        raise ValueError("remote prompt is frozen to the current objective; custom objectives need a new prompt protocol")
    if name not in REMOTE_MODELS:
        raise ValueError("unknown remote model")
    if mode == "first-action":
        return (CHAT_URL, sol_payload(instance.observation())) if name == "sol-medium" else (
            DECISIONS_URL, matched_payload(instance.observation(), REMOTE_MODELS[name]))
    if mode != "full-plan":
        raise ValueError("unknown evaluation mode")
    if name != "sol-medium":
        raise ValueError("full-plan generation is not verified for Decisions endpoints; no chat substitution")
    payload = sol_payload(instance.observation())
    content = json.loads(payload["messages"][0]["content"])
    rules = signal_question(instance.horizon)["instructions"]
    rules = rules[rules.index("Initialize queues"):rules.index("Choose the switch only")]
    content["questions"] = {"plan": {
        "instructions": f"Construct a minimum-cost feasible {instance.horizon}-step action schedule. "
            f"Minimize the sum of end-of-step NS and EW queues plus {CURRENT_OBJECTIVE.switch_penalty} per initiated switch "
            f"plus {CURRENT_OBJECTIVE.terminal_queue_penalty} times the final NS+EW queue. "
            f"The final queue also remains in the running sum. {rules} "
            "Return JSON with actions: exactly one NS or EW desired-phase token per step. "
            "During yellow/all-red return the outgoing current_phase as a no-op. "
            "Do not supply a cost or omit forced steps."}}
    payload["messages"][0]["content"] = json.dumps(content, sort_keys=True, separators=(",", ":"))
    payload["response_format"]["json_schema"] = {
        "name": "signal_plan", "strict": True,
        "schema": {"type": "object", "properties": {"actions": {
            "type": "array", "items": {"type": "string", "enum": ["NS", "EW"]},
            "minItems": instance.horizon, "maxItems": instance.horizon}},
            "required": ["actions"], "additionalProperties": False}}
    return CHAT_URL, payload


def model_configuration(instance, name, mode, timeout):
    url, payload = payload_for(instance, name, mode)
    questions = (json.loads(payload['messages'][0]['content'])['questions']
                 if 'messages' in payload else payload['questions'])
    return {"name": name, "model": REMOTE_MODELS[name], "endpoint": url, "mode": mode,
            "timeout_seconds": timeout, "payload_sha256": fingerprint(payload),
            "prompt_sha256": fingerprint(questions),
            "reasoning_effort": payload.get("reasoning_effort"),
            "max_completion_tokens": payload.get("max_completion_tokens"),
            "response_format": payload.get("response_format")}


def request_model(instance, name, mode, timeout=120, transport=None, save_raw=None):
    """One attempt, no retries; account for usage even when the output is invalid."""
    url, payload = payload_for(instance, name, mode)
    key = load_api_key() if transport is None else None
    def redact(text):
        return text.replace(key, "[REDACTED]") if key else text
    def save(label, value):
        if save_raw:
            save_raw(label, redact(value))
    save("request", json.dumps({"endpoint": url, "payload": payload}, sort_keys=True))
    began = time.perf_counter()
    result = {"status": "failed", "valid": False, "action": None, "plan": None,
              "input_tokens": None, "output_tokens": None, "cost_usd": None,
              "returned_model": None, "provider": None}
    try:
        if transport is not None:
            response = transport(payload)
            raw = json.dumps(response)
        else:
            if not key:
                raise RuntimeError("OPENROUTER_API_KEY is missing")
            request = Request(url, data=json.dumps(payload).encode(),
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            try:
                with urlopen(request, timeout=timeout) as stream:
                    raw = stream.read().decode("utf-8")
            except HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                save("response", raw)
                raise RuntimeError(f"HTTP {exc.code}: {redact(raw)[:1000]}") from exc
            save("response", raw)
            response = json.loads(raw)
        save("response", raw)
        usage = response.get("usage") or {}
        result.update(input_tokens=usage.get("input_tokens", usage.get("prompt_tokens")),
                      output_tokens=usage.get("output_tokens", usage.get("completion_tokens")),
                      cost_usd=usage.get("cost"), returned_model=response.get("model"),
                      provider=response.get("provider"), response_id=response.get("id"))
        if name == "sol-medium":
            choice = response["choices"][0]
            result["finish_reason"] = choice.get("finish_reason")
            if choice.get("finish_reason") != "stop":
                raise ValueError("non-stop completion (truncated, refused, or otherwise incomplete)")
            output = json.loads(choice["message"]["content"])
            field = "choice" if mode == "first-action" else "actions"
            if not isinstance(output, dict) or set(output) != {field}:
                raise ValueError("output does not match required schema")
            result["action" if mode == "first-action" else "plan"] = output[field]
        else:
            result["action"] = response["answers"]["signal"]["choice"]
        if mode == "first-action" and result["action"] not in instance.legal_actions:
            raise ValueError("model returned an illegal first action")
        result.update(status="returned", valid=True)
    except Exception as exc:
        result["error"] = redact(f"{type(exc).__name__}: {exc}")
    result["latency_ms"] = 1000 * (time.perf_counter() - began)
    return result
