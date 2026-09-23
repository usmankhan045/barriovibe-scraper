"""Discord webhook delivery.

One message per lead, formatted so the DM can be copied in a single gesture:
the message body sits alone in a fenced code block, which Discord renders with
a copy button. Everything the reader needs to decide whether to send it --
who, where, what they said, why it scored -- sits above the block.

Failure policy: a lead that cannot be delivered is reported, never silently
dropped. Losing a qualified lead to a transient HTTP error would waste the
money already spent finding it, so sends are retried and anything still
failing is surfaced in the run summary.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Discord hard limits.
MAX_EMBED_DESCRIPTION = 4096
MAX_FIELD_VALUE = 1024
MAX_EMBEDS_PER_MESSAGE = 10

# Discord rate-limits webhooks. A small gap between sends keeps a day's batch
# well clear of it without needing bucket tracking.
SEND_GAP_S = 1.2
MAX_RETRIES = 3

# Tier presentation. Colours are Discord embed integers.
TIERS = (
    (75, "STRONG", 0x2ECC71),        # green
    (65, "SOLID", 0x3498DB),         # blue
    (0, "WORTH A LOOK", 0x95A5A6),   # grey
)


def tier_for(score: int) -> tuple[str, int]:
    for threshold, label, colour in TIERS:
        if score >= threshold:
            return label, colour
    return TIERS[-1][1], TIERS[-1][2]


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


@dataclass
class DeliveryResult:
    sent: int = 0
    failed: int = 0
    errors: list[str] = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


class DiscordSender:
    def __init__(self, webhook_url: str, *, dry_run: bool = False) -> None:
        self.webhook_url = webhook_url
        self.dry_run = dry_run

    def _post(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            req = urllib.request.Request(
                self.webhook_url,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    # Discord's edge returns 403 "error code: 1010" without a
                    # User-Agent; their API docs require one on every request.
                    "User-Agent": (
                        "BarrioVibeLeadScraper (https://barriovibe.com, 1.0)"
                    ),
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    if 200 <= resp.status < 300:
                        return
                    last_error = RuntimeError(f"HTTP {resp.status}")
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
                if exc.code == 429:
                    # Honour Discord's own backoff when it supplies one.
                    retry_after = 5.0
                    try:
                        retry_after = float(json.loads(detail).get("retry_after", 5))
                    except (ValueError, TypeError, AttributeError):
                        pass
                    log.warning("Discord rate limited; waiting %.1fs", retry_after)
                    time.sleep(min(retry_after, 30))
                    last_error = exc
                    continue
                if exc.code == 404:
                    raise RuntimeError(
                        "Discord webhook returned 404. The webhook URL is wrong "
                        "or was deleted. Check DISCORD_WEBHOOK_URL in .env."
                    ) from exc
                if 400 <= exc.code < 500:
                    raise RuntimeError(
                        f"Discord rejected the message (HTTP {exc.code}): {detail}"
                    ) from exc
                last_error = exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                log.warning("Discord send failed (attempt %s/%s): %s",
                            attempt, MAX_RETRIES, exc)

            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)

        raise RuntimeError(f"Discord send failed after {MAX_RETRIES} attempts: {last_error}")

    def send_lead(self, lead: dict) -> None:
        """Send one lead. `lead` carries the post, author, score and message."""
        score = int(lead.get("score", 0))
        tier, colour = tier_for(score)

        author = lead.get("author_name") or "Unknown"
        headline = lead.get("author_headline") or ""
        country = lead.get("country") or "?"
        niche = lead.get("niche") or ""

        fields = [
            {
                "name": "Why this lead",
                "value": _truncate(lead.get("pain") or "—", MAX_FIELD_VALUE),
                "inline": False,
            },
            {
                "name": "Their post",
                "value": _truncate(
                    f"> {(lead.get('post_excerpt') or '').replace(chr(10), ' ')}",
                    MAX_FIELD_VALUE,
                ),
                "inline": False,
            },
            {
                "name": "Fits",
                "value": _truncate(lead.get("service") or "—", MAX_FIELD_VALUE),
                "inline": True,
            },
            {
                "name": "Posted",
                "value": lead.get("posted_ago") or "—",
                "inline": True,
            },
        ]

        embed = {
            "title": f"{tier} · {score}/100 · {author}",
            "url": lead.get("post_url") or None,
            "description": _truncate(
                f"**{headline}**\n"
                f"{country} · {niche} · "
                f"[Profile]({lead.get('author_url', '')}) · "
                f"[Post]({lead.get('post_url', '')})",
                MAX_EMBED_DESCRIPTION,
            ),
            "color": colour,
            "fields": fields,
        }

        # The message sits in its own plain block so it can be copied cleanly
        # without the surrounding context coming with it.
        message = lead.get("message") or ""
        content = f"```\n{_truncate(message, 1800)}\n```"

        payload = {
            "content": content,
            "embeds": [embed],
            # Nothing here should ever ping anyone.
            "allowed_mentions": {"parse": []},
        }

        if self.dry_run:
            log.info("[dry-run] would send lead: %s (%s/100)", author, score)
            print(f"\n{'─' * 70}\n{tier} · {score}/100 · {author}")
            print(f"{headline}\n{country} · {niche}")
            print(f"Pain: {lead.get('pain')}")
            print(f"Fits: {lead.get('service')}")
            print(f"Post: {lead.get('post_url')}")
            print(f"\n{message}\n{'─' * 70}")
            return

        self._post(payload)

    def send_all(self, leads: list[dict]) -> DeliveryResult:
        result = DeliveryResult()
        # Best leads first: if anything fails partway, the strongest are already
        # delivered.
        for lead in sorted(leads, key=lambda x: int(x.get("score", 0)), reverse=True):
            try:
                self.send_lead(lead)
                result.sent += 1
            except Exception as exc:  # noqa: BLE001 - reported, never swallowed
                result.failed += 1
                who = lead.get("author_name", "?")
                result.errors.append(f"{who}: {exc}")
                log.error("Failed to deliver lead for %s: %s", who, exc)
            if not self.dry_run:
                time.sleep(SEND_GAP_S)
        return result

    def send_summary(self, text: str) -> None:
        """Post the run summary so each day's result is visible in-channel."""
        if self.dry_run:
            print(f"\n[dry-run] summary:\n{text}")
            return
        try:
            self._post({
                "content": _truncate(text, 1900),
                "allowed_mentions": {"parse": []},
            })
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to send run summary: %s", exc)
