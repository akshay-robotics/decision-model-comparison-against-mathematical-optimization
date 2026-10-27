"""Deterministic supplied-arrival scenarios; horizons are nested prefixes."""

import random

from .problem import Instance, fingerprint


GENERATOR_VERSION = "queue-families-v1"
FAMILIES = ("empty", "ordinary", "delayed_burst", "competing_bursts", "lookahead", "clearance")
# Development fixture found by deterministic search, never a held-out test.
# With no extension: H15 favors EW (194.5 vs 198.5); H30 favors NS (325 vs 334).
REVERSAL_TAIL = ((0, 1), (1, 1), (0, 0), (0, 1), (1, 1), (1, 1), (1, 1),
                 (1, 0), (1, 1), (1, 0), (0, 0), (0, 21), (1, 1), (1, 0), (0, 0))


def generate_instance(family, seed, horizon):
    if family not in FAMILIES:
        raise ValueError(f"unknown case family: {family}")
    rng = random.Random(int(fingerprint({"generator": GENERATOR_VERSION, "family": family, "seed": seed}), 16))
    q = (rng.randrange(1, 10), rng.randrange(1, 10))
    # Generate from absolute time so increasing the requested horizon preserves
    # queues and every already-supplied arrival, not just the RNG seed.
    arrivals = [[0, 0] for _ in range(horizon)]
    kwargs = {}
    if family == "empty":
        q = (0, 0)
    elif family in ("ordinary", "clearance"):
        for t in range(horizon):
            arrivals[t] = [int(rng.random() < 0.35), int(rng.random() < 0.35)]
        if family == "clearance":
            kwargs = {"pending": "EW", "remaining": 3, "age": 8}
    elif family == "lookahead":
        q = (4, 19)
        for t, row in enumerate(REVERSAL_TAIL, 15):
            if t < horizon:
                arrivals[t] = list(row)
        # Seeds vary the extension; the published first-30-second fixture stays
        # fixed and is explicitly counted as one physical instance when shared.
        for t in range(30, horizon):
            arrivals[t] = [int(rng.random() < 0.3), int(rng.random() < 0.3)]
    else:
        bursts = ((24, 1), (55, 0), (95, 1)) if family == "delayed_burst" else (
            (12, 0), (18, 1), (45, 1), (50, 0), (80, 0), (86, 1), (110, 1))
        for t, group in bursts:
            amount = rng.randrange(10, 27)
            if t < horizon:
                arrivals[t][group] = amount
    return Instance(f"{family}-seed{seed}", family, seed, horizon, q, tuple(map(tuple, arrivals)), **kwargs)


def physical_identity(instance):
    return fingerprint({k: v for k, v in instance.record().items() if k not in ("case_id", "family", "seed")})
