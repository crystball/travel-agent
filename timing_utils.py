from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Iterator


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def attraction_llm_enabled() -> bool:
    return env_flag("TRAVEL_AGENT_ATTRACTION_LLM", default=False)


def itinerary_llm_enabled() -> bool:
    return env_flag("TRAVEL_AGENT_ITINERARY_LLM", default=False)


def timing_enabled() -> bool:
    value = os.getenv("TRAVEL_AGENT_TIMING", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


@contextmanager
def timed_step(name: str) -> Iterator[None]:
    if not timing_enabled():
        yield
        return

    started_at = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started_at
        print(f"[timing] {name}: {elapsed:.2f}s")
