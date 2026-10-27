"""Medium-reasoning GPT-6.1 Sol adapter using the matched traffic question."""

from datetime import datetime, timezone
from copy import deepcopy
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request
from .security import open_api_request as urlopen

from .controllers import (GROUP_SERVICE_CAPACITY, MODEL_HORIZON, SWITCH_PENALTY,
                          YELLOW_SERVICE_CAPACITY, TERMINAL_QUEUE_PENALTY, CURRENT_OBJECTIVE, matched_observation)
from dataclasses import asdict
from .openrouter import (PROMPT_SHA256, PROMPT_VERSION, signal_question, prompt_sha256, load_api_key)


SOL_MODEL = "openai/gpt-6.1-sol"
REASONING_EFFORT = "medium"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
CHOICE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "signal_choice",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"choice": {"type": "string", "enum": ["NS", "EW"]}},
            "required": ["choice"],
            "additionalProperties": False,
        },
    },
}


def sol_payload(observation):
    """Use the exact Decisions question and state in a chat JSON envelope."""
    content = {
        "state": matched_observation(observation).record(),
        "questions": {"signal": signal_question(len(observation.arrivals))},
    }
    return {
        "model": SOL_MODEL,
        "messages": [{"role": "user", "content": json.dumps(content, sort_keys=True, separators=(",", ":"))}],
        "reasoning_effort": REASONING_EFFORT,
        "response_format": deepcopy(CHOICE_SCHEMA),
        "max_completion_tokens": 4096,
    }


class SolMediumReasoning:
    name = "sol-medium"

    def __init__(self, api_key=None, timeout=120.0, transport=None, horizon=MODEL_HORIZON):
        signal_question(horizon)
        self.horizon = horizon
        self.api_key = api_key if api_key is not None else load_api_key()
        if not self.api_key:
            raise RuntimeError("GPT-6.1 Sol requires OPENROUTER_API_KEY in the server environment or project .env")
        self.timeout = timeout
        self.transport = transport or self._post
        self.requests = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.model = SOL_MODEL
        self.provider = None
        self.request_dates = []
        self.records = []

    def _post(self, payload):
        request = Request(
            CHAT_URL,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"OpenRouter chat HTTP {exc.code}") from None
        except (URLError, TimeoutError) as exc:
            raise RuntimeError("OpenRouter chat request failed") from None

    def decide(self, observation):
        if len(observation.arrivals) != self.horizon:
            raise ValueError("controller horizon and forecast length differ")
        legal = matched_observation(observation).legal_actions
        if len(legal) == 1:
            return legal[0]
        if set(legal) != {"NS", "EW"}:
            raise RuntimeError(f"unexpected signal actions: {legal}")
        requested_at = datetime.now(timezone.utc).isoformat()
        response = self.transport(sol_payload(observation))
        try:
            content = response["choices"][0]["message"]["content"]
            action = json.loads(content)["choice"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("GPT-6.1 Sol returned no valid signal choice") from exc
        if action not in legal:
            raise RuntimeError("GPT-6.1 Sol returned an illegal signal choice")
        usage = response.get("usage") or {}
        self.requests += 1
        self.input_tokens += int(usage.get("prompt_tokens") or 0)
        self.output_tokens += int(usage.get("completion_tokens") or 0)
        self.cost_usd += float(usage.get("cost") or 0)
        self.model = response.get("model") or SOL_MODEL
        self.provider = response.get("provider")
        self.request_dates.append(requested_at)
        self.records.append({
            "simulation_time_seconds": observation.time,
            "requested_at_utc": requested_at,
            "response_id": response.get("id"),
            "model": self.model,
            "provider": self.provider,
            "choice": action,
            "confidence": None,
            "probabilities": None,
            "finish_reason": response["choices"][0].get("finish_reason"),
            "usage": usage,
        })
        return action

    def metadata(self):
        return {
            "information_mode": "matched",
            "api_mode": "chat/completions",
            "reasoning_effort": REASONING_EFFORT,
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": prompt_sha256(self.horizon),
            "objective_horizon_steps": self.horizon,
            "service_capacity_per_group_per_second": GROUP_SERVICE_CAPACITY,
            "yellow_service_capacity_per_group_per_second": YELLOW_SERVICE_CAPACITY,
            "switch_penalty": SWITCH_PENALTY,
            "terminal_queue_penalty": TERMINAL_QUEUE_PENALTY,
            "objective": asdict(CURRENT_OBJECTIVE),
            "requested_model": SOL_MODEL,
            "returned_model": self.model,
            "provider": self.provider,
            "request_count": self.requests,
            "first_request_utc": self.request_dates[0] if self.request_dates else None,
            "last_request_utc": self.request_dates[-1] if self.request_dates else None,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 9),
            "decisions": self.records,
        }
