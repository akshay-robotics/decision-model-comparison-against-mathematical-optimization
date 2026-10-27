"""OpenRouter Decisions API adapter for the signal-only SUMO pilot."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request
from .security import open_api_request as urlopen

from .controllers import (GROUP_SERVICE_CAPACITY, MODEL_HORIZON, SWITCH_PENALTY,
                          YELLOW_SERVICE_CAPACITY, TERMINAL_QUEUE_PENALTY, CURRENT_OBJECTIVE, matched_observation)
from dataclasses import asdict


DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
MICROSOFT_MODEL = "microsoft/microsoft-decision-1"
JEV_MODEL = "typesafe/jev-1.13"
LUNA_MODEL = "openai/gpt-6-luna-decisions"
DECISION_MODELS = {
    "microsoft": MICROSOFT_MODEL,
    "jev": JEV_MODEL,
    "luna": LUNA_MODEL,
}
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
PROMPT_VERSION = "matched-queue-v8-terminal-queue"
def signal_question(horizon):
    if type(horizon) is not int or horizon < 1:
        raise ValueError("planning horizon must be a positive integer")
    instructions = (
        f"Choose the first action of a {horizon}-step plan with one-second steps. "
        "Compare BOTH legal first actions: keep current_phase green for step 1, or initiate "
        "a switch to the other phase immediately at the start of step 1. For each first action, "
        f"consider its best legal continuation through step {horizon} and compare objective "
        f"J = sum of end-of-step NS and EW queues over steps 1 through {horizon} "
        f"plus {SWITCH_PENALTY} for each phase switch initiated within the horizon. "
        f"Also add {TERMINAL_QUEUE_PENALTY} times the sum of NS and EW queues at the end of step {horizon}. "
        f"Thus J = sum(q_NS[t]+q_EW[t], t=1..{horizon}) + {SWITCH_PENALTY}*switch_count "
        f"+ {TERMINAL_QUEUE_PENALTY}*(q_NS[{horizon}]+q_EW[{horizon}]). "
        "The final queue is included in the running sum and additionally in the terminal penalty. "
        "This penalizes residual modeled queues; queue discharge is not the same as completing a SUMO trip. "
        "Initialize queues from queue_totals. Forecast row t in arrivals_forecast_NS_EW "
        "is [NS, EW] arrivals during step t, starting at t=0. In every step add that row's "
        "arrivals, then serve the minimum of available queue and capacity: when a group stays "
        f"green, capacity is {GROUP_SERVICE_CAPACITY} vehicles for that group; during yellow, "
        f"capacity is {YELLOW_SERVICE_CAPACITY} for the outgoing group; during all-red, capacity is zero. "
        "The red group always serves zero. End-of-step queue = prior queue + arrivals - service. "
        "A switch makes the outgoing phase yellow immediately for ceil(yellow_seconds) steps, "
        "then both groups all-red for ceil(switch_clearance_seconds - yellow_seconds) steps; "
        "only then does the requested phase become green. A newly green phase must remain "
        "green for ceil(min_green_seconds) steps before another switch. Use current_phase, "
        "phase_elapsed_seconds, pending_phase, clearance_remaining_seconds, and legal_actions "
        "to enforce the current state and legal transitions. Use only the supplied forecast; "
        "do not invent future demand or choose a phase merely because its current queue is larger. "
        "Choose the switch only if its best J is strictly lower than the best J from staying. "
        "If the objectives tie, keep current_phase. Return only a legal action."
    )
    question = {
        "type": "choice",
        "instructions": instructions,
        "criteria": {
            "NS": "Keep NS green now, or request NS and start clearance now if EW is green.",
            "EW": "Keep EW green now, or request EW and start clearance now if NS is green.",
        },
    }
    return question


def prompt_sha256(horizon):
    return hashlib.sha256(json.dumps(signal_question(horizon), sort_keys=True).encode("utf-8")).hexdigest()


SIGNAL_QUESTION = signal_question(MODEL_HORIZON)
MATCHED_INSTRUCTIONS = SIGNAL_QUESTION["instructions"]
PROMPT_SHA256 = prompt_sha256(MODEL_HORIZON)


def matched_payload(observation, model, information_mode="matched"):
    """Only `model` differs across the three matched Decisions requests."""
    state = matched_observation(observation).record()
    if information_mode == "rich":
        state["queues_by_approach"] = observation.queues
        state["approaching_by_approach"] = observation.approaching
    return {"model": model, "state": state, "questions": {"signal": signal_question(len(observation.arrivals))}}


def load_api_key():
    """Prefer the process environment, then a local Git-ignored .env file."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    for line in lines:
        name, separator, value = line.strip().partition("=")
        if separator and name == "OPENROUTER_API_KEY":
            value = value.strip().strip('"\'')
            return value or None
    return None


class OpenRouterDecisions:
    """Identical typed question and observation for each OpenRouter model."""

    def __init__(self, name="microsoft", api_key=None, timeout=10.0,
                 transport=None, information_mode="matched", horizon=MODEL_HORIZON):
        if name not in DECISION_MODELS:
            raise ValueError(f"unknown decision model: {name}")
        if information_mode not in ("matched", "rich"):
            raise ValueError("information_mode must be matched or rich")
        signal_question(horizon)
        self.horizon = horizon
        self.information_mode = information_mode
        self.name = name if information_mode == "matched" else f"{name}-rich"
        self.requested_model = DECISION_MODELS[name]
        self.api_key = api_key if api_key is not None else load_api_key()
        if not self.api_key:
            raise RuntimeError("OpenRouter Decisions requires OPENROUTER_API_KEY in the server environment or project .env")
        self.timeout = timeout
        self.transport = transport or self._post
        self.requests = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.model = self.requested_model
        self.provider = None
        self.request_dates = []
        self.records = []

    def _post(self, payload):
        request = Request(
            DECISIONS_URL,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"OpenRouter Decisions HTTP {exc.code}") from None
        except (URLError, TimeoutError) as exc:
            raise RuntimeError("OpenRouter Decisions request failed") from None

    def decide(self, observation):
        if len(observation.arrivals) != self.horizon:
            raise ValueError("controller horizon and forecast length differ")
        matched = matched_observation(observation)
        legal = matched.legal_actions
        if len(legal) == 1:
            return legal[0]
        if set(legal) != {"NS", "EW"}:
            raise RuntimeError(f"unexpected signal actions: {legal}")
        payload = matched_payload(observation, self.requested_model, self.information_mode)
        requested_at = datetime.now(timezone.utc).isoformat()
        response = self.transport(payload)
        try:
            action = response["answers"]["signal"]["choice"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError("OpenRouter Decisions returned no signal choice") from exc
        if action not in legal:
            raise RuntimeError("OpenRouter Decisions returned an illegal signal choice")
        usage = response.get("usage") or {}
        self.requests += 1
        self.input_tokens += int(usage.get("input_tokens") or 0)
        self.output_tokens += int(usage.get("output_tokens") or 0)
        self.cost_usd += float(usage.get("cost") or 0)
        self.model = response.get("model") or self.requested_model
        self.provider = response.get("provider")
        self.request_dates.append(requested_at)
        self.records.append({
            "simulation_time_seconds": observation.time,
            "requested_at_utc": requested_at,
            "response_id": response.get("id"),
            "model": self.model,
            "provider": self.provider,
            "choice": action,
            "confidence": response["answers"]["signal"].get("confidence"),
            "probabilities": response["answers"]["signal"].get("probabilities"),
            "usage": usage,
        })
        return action

    def metadata(self):
        return {
            "information_mode": self.information_mode,
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": prompt_sha256(self.horizon),
            "objective_horizon_steps": self.horizon,
            "service_capacity_per_group_per_second": GROUP_SERVICE_CAPACITY,
            "yellow_service_capacity_per_group_per_second": YELLOW_SERVICE_CAPACITY,
            "switch_penalty": SWITCH_PENALTY,
            "terminal_queue_penalty": TERMINAL_QUEUE_PENALTY,
            "objective": asdict(CURRENT_OBJECTIVE),
            "requested_model": self.requested_model,
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


class MicrosoftDecisions(OpenRouterDecisions):
    def __init__(self, **kwargs):
        super().__init__(name="microsoft", **kwargs)
