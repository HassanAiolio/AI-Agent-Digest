"""Shared Groq client: JSON-mode chat with rate-limit-aware pacing.

Every LLM stage (item summaries, the morning brief, the weekly recap) goes
through chat_json(). Two things make the free tier reliable here:

1. Pacing from Groq's own headers. Each response reports how many tokens
   are left in the current minute and when that window resets. Groq counts
   a request's max_tokens against that budget up front, so before sending
   we wait for the window to reset if the request would not fit, instead
   of firing it and eating a 429.
2. Bounded reasoning. The gpt-oss models think before answering, and those
   hidden reasoning tokens count against max_tokens. At the default effort
   a tight budget runs out mid-JSON and Groq rejects the whole response
   (400 json_validate_failed) — the actual cause of the old fallback
   nights. reasoning_effort=low keeps thinking to a few hundred tokens,
   and a truncated reply is retried with a bigger budget, not abandoned.
3. A model chain. If the primary model keeps failing (overloaded, retired,
   quota), the same prompt goes to a smaller fallback model before anyone
   has to settle for raw abstracts.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

import requests

log = logging.getLogger("llm")

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(RuntimeError):
    pass


def available() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


def _duration(text: str | None) -> float | None:
    """Parse Groq reset durations like '7.66s', '2m59.5s', '120ms'."""
    if not text:
        return None
    total, matched = 0.0, False
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h)", text):
        matched = True
        total += float(value) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    if matched:
        return total
    try:
        return float(text)
    except ValueError:
        return None


class _Budget:
    """Tokens left in the current per-minute window, as last reported."""

    def __init__(self) -> None:
        self.remaining: float | None = None
        self.resets_at = 0.0

    def update(self, headers) -> None:
        rem = headers.get("x-ratelimit-remaining-tokens")
        reset = _duration(headers.get("x-ratelimit-reset-tokens"))
        if rem is not None:
            try:
                self.remaining = float(rem)
            except ValueError:
                self.remaining = None
        if reset is not None:
            self.resets_at = time.monotonic() + reset

    def wait_for(self, need: int) -> None:
        if self.remaining is None or self.remaining >= need:
            return
        delay = self.resets_at - time.monotonic()
        if delay > 0:
            log.info("pacing: %d tokens left, need ~%d — waiting %.1fs",
                     self.remaining, need, min(delay, 65))
            time.sleep(min(delay, 65))
        self.remaining = None  # unknown until the next response


_budget = _Budget()


def _retry_after(resp: requests.Response | None) -> float | None:
    """Seconds to wait before retrying a 429: the Retry-After header, or the
    "Please try again in 7.66s" Groq puts in the body when the header is absent."""
    if resp is None:
        return None
    header = _duration(resp.headers.get("retry-after"))
    if header is not None:
        return header
    m = re.search(r"try again in ([\dhms.]+)", resp.text or "", re.I)
    return _duration(m.group(1)) if m else None


def _strip_fences(text: str) -> str:
    return re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()


def _estimate_tokens(prompt: str) -> int:
    return len(prompt) // 3  # conservative chars-per-token for English + JSON


def chat_json(prompt: str, gcfg: dict, max_tokens: int, *, attempts: int = 3) -> dict:
    """Send one prompt, return the parsed JSON object. Raises LLMError once
    every model in the chain has exhausted its attempts."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise LLMError("GROQ_API_KEY not set")

    models = [gcfg.get("model", "openai/gpt-oss-120b")]
    if gcfg.get("fallback_model"):
        models.append(gcfg["fallback_model"])
    timeout = int(gcfg.get("request_timeout", 60))
    base_pause = float(gcfg.get("sleep_between_calls", 3))
    effort = gcfg.get("reasoning_effort", "low")

    last_error: Exception | None = None
    for model in models:
        budget = max_tokens
        for attempt in range(1, attempts + 1):
            _budget.wait_for(_estimate_tokens(prompt) + budget)
            resp = None
            try:
                resp = requests.post(
                    ENDPOINT,
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": budget,
                        "response_format": {"type": "json_object"},
                        **({"reasoning_effort": effort, "include_reasoning": False}
                           if "gpt-oss" in model and effort else {}),
                    },
                    timeout=timeout,
                )
                _budget.update(resp.headers)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                return json.loads(_strip_fences(content))
            except (requests.RequestException, KeyError, ValueError) as e:
                last_error = e
                status = resp.status_code if resp is not None else None
                body = " ".join((resp.text[:200] if resp is not None else "").split())
                log.warning("%s attempt %d/%d failed (%s): %s %s",
                            model, attempt, attempts, status or "no response", e, body)
                if status == 400 and "json_validate_failed" in body and attempt < attempts:
                    # Ran out of tokens mid-JSON (reasoning ate the budget).
                    budget = int(budget * 1.6)
                    continue
                if status in (400, 401, 403, 404, 413):
                    # bad request / auth / unknown model / over this model's
                    # size limit: retrying the same model won't help
                    break
                if attempt == attempts:
                    break
                if status == 429:
                    wait = _retry_after(resp)
                    time.sleep(min(wait, 65) if wait else min(base_pause * 2 ** attempt, 30))
                else:
                    time.sleep(min(base_pause * 2 ** attempt, 30))
        log.warning("model %s exhausted, %s", model,
                    "trying fallback" if model != models[-1] else "giving up")
    raise LLMError(str(last_error))
