"""LLM client.

Two providers, chosen for what each job actually needs:

  WRITING   -> OpenRouter, z-ai/glm-5.2:free
              Rank 15 on Creative Writing v3 with a slop score of 13.11: lower
              than Kimi K2.6 (13.3) and 58% lower than gpt-oss-120b (31.35).
              Slop measures formulaic AI phrasing, which is the single thing
              that kills a cold DM, so it is the deciding metric here.
              Free tier: 20 req/min, 50 req/day without credits.

  SCORING   -> Cerebras, gpt-oss-120b
              Classification does not care about prose quality, and keeping it
              off OpenRouter leaves the whole 50/day allowance for DMs.
              Free tier: 5 req/min, 1M tokens/day, no credit card.

Both are OpenAI-compatible, so one client covers them. Provider and model come
from the environment: swapping either is a one-line change, not a rewrite,
because free-tier model availability shifts (Kimi, Llama 4 and Qwen3-32B were
all retired from Groq during 2026).
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

log = logging.getLogger(__name__)

PROVIDERS = {
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key_prefix": "sk-or-",
        "signup": "openrouter.ai -> Keys",
        # Free models 404 unless prompt publication is enabled. This is the
        # most common reason free models appear broken.
        "extra_headers": {
            "HTTP-Referer": "https://barriovibe.com",
            "X-Title": "BarrioVibe Lead Scraper",
            # Some providers block requests with no User-Agent outright.
            "User-Agent": "BarrioVibe-LeadScraper/1.0",
        },
        "min_interval_s": 3.0,   # 20 req/min
    },
    "cerebras": {
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "key_prefix": "csk-",
        "signup": "cloud.cerebras.ai -> API Keys",
        # Cerebras returns 403 "error code: 1010" (a bot block) when no
        # User-Agent is sent, which masks the real underlying status.
        "extra_headers": {"User-Agent": "BarrioVibe-LeadScraper/1.0"},
        "min_interval_s": 12.0,  # 5 req/min
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key_prefix": "gsk_",
        "signup": "console.groq.com -> API Keys",
        "extra_headers": {"User-Agent": "BarrioVibe-LeadScraper/1.0"},
        "min_interval_s": 2.0,
    },
    "mistral": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "key_prefix": "",
        "signup": "console.mistral.ai -> API Keys",
        "extra_headers": {},
        "min_interval_s": 2.0,
    },
}

REQUEST_TIMEOUT_S = 120
MAX_RETRIES = 4

# A provider's rate limit applies to the API KEY, not to the object holding it.
# The writer chain and the scorer chain each build their own LLMClient for the
# same Groq models, so per-instance pacing let two clients fire inside the same
# window and collect a 429 that neither had any way to see coming. Pacing state
# therefore lives per provider, shared by every client that talks to it.
_LAST_CALL_AT: dict[str, float] = {}

# When a model does rate-limit us, that verdict holds for a while. Without a
# memory of it, every subsequent lead re-tries the same dead model and pays the
# same multi-second wait before falling through the chain again. Recording the
# time a model becomes usable again turns that repeated cost into a single one.
_COOLDOWN_UNTIL: dict[str, float] = {}

# How long to skip a model after it rate-limits us. Short enough that a brief
# spike does not sideline a good model for the rest of the run.
COOLDOWN_S = 60.0


def seconds_until_any_ready(max_wait: float = COOLDOWN_S) -> float:
    """How long until at least one cooling-down model is usable again.

    0.0 when nothing is cooling down, so a caller that failed for reasons other
    than rate limiting retries immediately instead of sleeping for no reason.
    """
    if not _COOLDOWN_UNTIL:
        return 0.0
    now = time.monotonic()
    remaining = [until - now for until in _COOLDOWN_UNTIL.values() if until > now]
    if not remaining:
        return 0.0
    return min(min(remaining), max_wait)


class LLMError(RuntimeError):
    """Call failed in a way the caller cannot recover from."""


class RateLimited(LLMError):
    """Provider refused for rate reasons. Retryable."""


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str


class FallbackClient:
    """Tries several models in order until one answers.

    Free-tier models go temporarily unavailable: the upstream provider serving
    a given free variant gets overloaded and returns 429 regardless of your own
    usage. A single-model client would abort the run. This walks a preference
    list instead, so quality degrades gracefully rather than the day's leads
    being lost.

    Order matters: the first model is the best one for the job, later entries
    are acceptable substitutes.
    """

    def __init__(self, clients: list["LLMClient"]) -> None:
        if not clients:
            raise LLMError("FallbackClient needs at least one client")
        self.clients = clients

    @property
    def model(self) -> str:
        return self.clients[0].model

    def _ordered(self) -> list["LLMClient"]:
        """Preference order, with cooling-down models moved to the back.

        They are moved rather than dropped: if every model is cooling down we
        still make the call instead of failing the lead outright.
        """
        ready = [c for c in self.clients if not c.cooling_down()]
        cooling = [c for c in self.clients if c.cooling_down()]
        return ready + cooling

    def _run(self, method: str, messages: list[dict], kwargs):
        errors: list[str] = []
        clients = self._ordered()
        for client in clients:
            try:
                result = getattr(client, method)(messages, **kwargs)
                if client is not self.clients[0]:
                    log.info("Used %s/%s", client.provider, client.model)
                return result
            except LLMError as exc:
                errors.append(f"{client.provider}/{client.model}: {str(exc)[:120]}")
                continue
        raise LLMError("All models failed:\n  " + "\n  ".join(errors))

    def complete(self, messages: list[dict], **kwargs) -> "LLMResponse":
        return self._run("complete", messages, kwargs)

    def complete_json(self, messages: list[dict], **kwargs) -> dict:
        return self._run("complete_json", messages, kwargs)


class LLMClient:
    """Minimal OpenAI-compatible chat client with pacing and retries.

    Paces itself to the provider's documented rate limit rather than waiting
    to be refused: on a free tier, a 429 can cost far more wall-clock than the
    gap it would have taken to avoid one.
    """

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        *,
        dry_run: bool = False,
    ) -> None:
        if provider not in PROVIDERS:
            raise LLMError(
                f"Unknown provider {provider!r}. Known: {sorted(PROVIDERS)}"
            )
        self.provider = provider
        self.config = PROVIDERS[provider]
        self.api_key = api_key
        self.model = model
        self.dry_run = dry_run
        # Rate limits are enforced per API key, so pacing state is keyed by
        # provider and shared across every client using it.
        self._pace_key = provider
        self._cool_key = f"{provider}/{model}"
        # Do NOT wait out our own rate limit here. Moving to the next model in
        # the chain is faster than sleeping, and the model that refused us is
        # now in cooldown so we will not keep paying for it.
        self.rate_limit_retries = 1

        prefix = self.config["key_prefix"]
        if prefix and not api_key.startswith(prefix):
            raise LLMError(
                f"{provider} key should start with {prefix!r}. Get one from "
                f"{self.config['signup']}."
            )

    def cooling_down(self) -> bool:
        """True if this model rate-limited us recently enough to still skip."""
        return time.monotonic() < _COOLDOWN_UNTIL.get(self._cool_key, 0.0)

    def _start_cooldown(self) -> None:
        _COOLDOWN_UNTIL[self._cool_key] = time.monotonic() + COOLDOWN_S

    def _mark_called(self) -> None:
        _LAST_CALL_AT[self._pace_key] = time.monotonic()

    def _wait_turn(self) -> None:
        gap = self.config["min_interval_s"]
        elapsed = time.monotonic() - _LAST_CALL_AT.get(self._pace_key, 0.0)
        if elapsed < gap:
            time.sleep(gap - elapsed)
        # Claim the slot before the request goes out, so a concurrent client
        # on the same provider paces against this call rather than the last
        # completed one.
        self._mark_called()

    def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 500,
        json_mode: bool = False,
    ) -> LLMResponse:
        if self.dry_run:
            return LLMResponse("[dry-run]", self.model, self.provider)

        # Reasoning models spend part of the budget thinking before they write
        # anything. Asking for 500 tokens can yield zero content. Raising the
        # ceiling costs nothing on a free tier and is what makes these models
        # usable at all.
        if any(tag in self.model for tag in ("gpt-oss", "qwen3", "magistral",
                                             "nemotron", "deepseek")):
            max_tokens = max(max_tokens, 2000)

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            **self.config["extra_headers"],
        }
        body = json.dumps(payload).encode("utf-8")
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            self._wait_turn()
            req = urllib.request.Request(
                self.config["url"], data=body, method="POST", headers=headers
            )
            try:
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                    self._mark_called()
                    data = json.loads(resp.read().decode("utf-8"))

                choices = data.get("choices")
                if not choices:
                    raise LLMError(f"No choices in response: {str(data)[:200]}")

                message = choices[0].get("message", {}) or {}
                content = message.get("content")
                finish = choices[0].get("finish_reason")

                # Reasoning models (gpt-oss, and others) emit thinking into a
                # separate `reasoning` field first. If max_tokens is consumed
                # before the answer starts, `content` comes back empty with
                # finish_reason="length" -- a truncation, not a refusal.
                if (not content or not content.strip()) and finish == "length":
                    raise LLMError(
                        f"Output truncated before any content was produced "
                        f"(finish_reason=length, model={self.model}). The token "
                        f"budget was spent on reasoning."
                    )

                # Some models put the whole answer in `reasoning` when the
                # response is short. Better to use it than to fail.
                if not content or not content.strip():
                    reasoning = message.get("reasoning")
                    if isinstance(reasoning, str) and reasoning.strip():
                        log.info("%s returned content in the reasoning field",
                                 self.model)
                        content = reasoning

                if not isinstance(content, str) or not content.strip():
                    raise LLMError("Model returned empty content")
                return LLMResponse(content, self.model, self.provider)

            except urllib.error.HTTPError as exc:
                self._mark_called()
                detail = exc.read().decode("utf-8", errors="replace")[:400]

                if exc.code == 401:
                    raise LLMError(
                        f"{self.provider} rejected the API key. Check it at "
                        f"{self.config['signup']}."
                    ) from exc

                if exc.code == 404 and self.provider == "openrouter":
                    raise LLMError(
                        "OpenRouter returned 404 'no endpoints matching your "
                        "data policy'. Free models require prompt publication: "
                        "enable it at openrouter.ai/settings/privacy. "
                        f"(model={self.model})"
                    ) from exc

                if exc.code == 429:
                    # Distinguish OUR rate limit from the upstream provider
                    # being overloaded. Ours clears in seconds and is worth
                    # waiting for; theirs does not, so fall through to the
                    # next model in the chain immediately.
                    upstream_overloaded = (
                        "temporarily rate-limited upstream" in detail
                        or "overloaded" in detail
                    )
                    # Either way this model is out for now. Record that so
                    # later leads skip it instead of re-discovering it, and
                    # hand straight to the next model rather than sleeping:
                    # the chain is faster than the wait.
                    self._start_cooldown()
                    if upstream_overloaded or attempt >= self.rate_limit_retries:
                        log.info(
                            "%s/%s rate limited, cooling down %.0fs",
                            self.provider, self.model, COOLDOWN_S,
                        )
                        raise RateLimited(
                            f"{self.provider}/{self.model} unavailable: "
                            f"{'upstream overloaded' if upstream_overloaded else 'rate limited'}"
                        ) from exc
                    last_error = RateLimited(detail)
                    continue

                if exc.code == 402:
                    raise LLMError(
                        f"{self.provider} requires payment for this model "
                        f"({self.model}). Free-tier inference is not enabled on "
                        f"this account. Check the billing tab at "
                        f"{self.config['signup']}."
                    ) from exc

                if 400 <= exc.code < 500:
                    raise LLMError(
                        f"{self.provider} rejected the request "
                        f"(HTTP {exc.code}): {detail}"
                    ) from exc

                last_error = exc
                log.warning("%s HTTP %s (attempt %s/%s)",
                            self.provider, exc.code, attempt, MAX_RETRIES)

            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                self._mark_called()
                last_error = exc
                log.warning("%s call failed (attempt %s/%s): %s",
                            self.provider, attempt, MAX_RETRIES, exc)

            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)

        raise LLMError(f"{self.provider} failed after {MAX_RETRIES} attempts: {last_error}")

    def complete_json(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 700,
    ) -> dict:
        """Complete and parse JSON, tolerating the usual model wrapping.

        Not all free models support response_format, so the parser recovers
        JSON from prose rather than relying on the provider to enforce it.
        """
        response = self.complete(
            messages, temperature=temperature, max_tokens=max_tokens, json_mode=True
        )
        return parse_json(response.text)


def parse_json(text: str) -> dict:
    """Extract a JSON object from model output.

    Handles fenced blocks, leading commentary and trailing prose, all of which
    free models emit despite instructions. Raises LLMError when nothing usable
    is present, so a malformed score can never enter the pipeline as a silent
    default.
    """
    if not text:
        raise LLMError("Empty response, expected JSON")

    cleaned = text.strip()

    fence = re.search(r"```(?:json)?\s*(.+?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fall back to the outermost brace pair.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise LLMError(f"Could not parse JSON from response: {text[:200]}")


# ---------------------------------------------------------------------------
# Model preference chains.
#
# Free-model availability is volatile: the provider serving a free variant can
# be overloaded at any moment, and models get retired outright (Kimi, Llama 4
# and Qwen3-32B all vanished from Groq during 2026). Each job therefore has an
# ordered list rather than a single model.
#
# Writing order is by slop score from Creative Writing v3, lower being better,
# because formulaic phrasing is what makes a cold DM fail:
#   z-ai/glm-5.2            13.11  (rank 15, beats paid Kimi K2.6 at 13.3)
#   deepseek-v4-flash       20.92  (rank 32)
#   google/gemma-4-31b      29.69  (rank 50)
# Nemotron is unbenchmarked for prose but is a large model and stays last.
# ---------------------------------------------------------------------------

WRITER_CHAIN = (
    ("openrouter", "z-ai/glm-5.2:free"),
    ("openrouter", "deepseek/deepseek-v4-flash-0731:free"),
    # Groq has a SEPARATE quota from OpenRouter. A live run produced two
    # qualified leads with no message because every OpenRouter free model was
    # rate-limited at the same moment: they share one pool. gpt-oss-120b writes
    # sloppier prose (slop 31 vs GLM's 13), but a usable message beats none,
    # and the banned-phrase validator still rejects the worst of it.
    ("groq", "openai/gpt-oss-120b"),
    ("openrouter", "google/gemma-4-31b-it:free"),
    ("groq", "openai/gpt-oss-20b"),
    ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"),
)

# Scoring needs reliable JSON, not good prose. DeepSeek-V4-Flash leads because
# it supports structured outputs; Gemma also exposes response_format.
SCORER_CHAIN = (
    # Groq FIRST for scoring. Scoring runs 10-20x more often than writing, so
    # spending OpenRouter's scarce free quota on it starves the DM writer,
    # which is the stage where model quality actually matters. Classification
    # does not care about prose, and Groq enforces JSON schemas strictly.
    ("groq", "openai/gpt-oss-120b"),
    ("groq", "openai/gpt-oss-20b"),
    ("openrouter", "deepseek/deepseek-v4-flash-0731:free"),
    ("openrouter", "google/gemma-4-31b-it:free"),
    ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    ("openrouter", "z-ai/glm-5.2:free"),
)


def build_chain(
    chain: tuple[tuple[str, str], ...],
    keys: dict[str, str],
    *,
    dry_run: bool = False,
) -> FallbackClient:
    """Build a FallbackClient, skipping providers with no key configured."""
    clients: list[LLMClient] = []
    for provider, model in chain:
        key = keys.get(provider)
        if not key:
            continue
        try:
            clients.append(LLMClient(provider, key, model, dry_run=dry_run))
        except LLMError as exc:
            log.warning("Skipping %s/%s: %s", provider, model, exc)
    if not clients:
        raise LLMError(
            "No usable models. Check that OPENROUTER_API_KEY is set in .env."
        )
    return FallbackClient(clients)
