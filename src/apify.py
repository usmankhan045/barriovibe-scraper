"""Apify client for LinkedIn post search and author enrichment.

Two actors, both from HarvestAPI (no cookies, no LinkedIn account):
  - harvestapi/linkedin-post-search   : find posts       ($0.002 / post)
  - harvestapi/linkedin-profile-scraper: enrich authors  ($0.004 / profile)

Both moved to pay-per-event pricing in March 2026. A query returning nothing
still costs $0.001, so query count is itself a cost.

Every response is validated before it is allowed into the pipeline. Malformed
records are dropped with a logged reason rather than being passed on as partial
data: a lead built from a half-parsed post wastes an LLM call and can produce a
DM that references something the person never said.

Every response is also cached to disk. Re-running filters, scoring or DM
writing against cached data costs nothing, so iterating on the pipeline never
re-scrapes.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.budget import (
    PRICE_PER_INLINE_PROFILE,
    PRICE_PER_POST,
    PRICE_PER_STANDALONE_PROFILE,
    BudgetExceeded,
    Ledger,
)

log = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"
POST_SEARCH_ACTOR = "harvestapi~linkedin-post-search"
PROFILE_ACTOR = "harvestapi~linkedin-profile-scraper"

# Apify runs are synchronous via run-sync-get-dataset-items. Post search over
# several queries can take a few minutes, so the timeout is generous; the
# budget cap, not the clock, is what bounds cost.
REQUEST_TIMEOUT_S = 600
MAX_RETRIES = 3

# Profile lookups are chunked: a live test showed batches of 10 return 10/10
# while a batch of 16 returned 1 item with no error reported.
PROFILE_BATCH_SIZE = 10

# Every raw API response is cached to disk. Re-running filters, scoring or DM
# writing against cached data costs nothing, so development and debugging never
# re-scrape. Without this, every iteration on a filter costs real money.
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
RETRY_BACKOFF_S = 5


class ApifyError(RuntimeError):
    """Actor call failed in a way the pipeline cannot recover from."""


@dataclass(frozen=True)
class Post:
    """A validated LinkedIn post. Every field here is known-present and typed."""

    post_id: str
    url: str
    content: str
    posted_at: datetime
    author_name: str
    author_headline: str
    author_url: str
    author_public_id: str
    likes: int
    comments: int
    niche: str  # which niche's query found it
    query: str  # the exact query that found it
    author_profile: dict[str, Any] | None = None  # set by enrichment

    @property
    def engagement(self) -> int:
        return self.likes + self.comments

    @property
    def age_hours(self) -> float:
        return (datetime.now(timezone.utc) - self.posted_at).total_seconds() / 3600


def _http_post(url: str, payload: dict, token: str) -> list[dict]:
    """POST to Apify, returning dataset items. Retries transient failures."""
    body = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                raw = resp.read().decode("utf-8")
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ApifyError(
                    f"Expected a list of dataset items, got {type(parsed).__name__}"
                )
            return parsed
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            # 4xx other than 429 are our fault (bad input, bad token): no retry.
            if exc.code == 401 or exc.code == 403:
                raise ApifyError(
                    f"Apify rejected the token (HTTP {exc.code}). Check "
                    f"APIFY_TOKEN in .env. Detail: {detail}"
                ) from exc
            if 400 <= exc.code < 500 and exc.code != 429:
                raise ApifyError(
                    f"Apify rejected the request (HTTP {exc.code}): {detail}"
                ) from exc
            last_error = exc
            log.warning("Apify HTTP %s on attempt %s/%s: %s",
                        exc.code, attempt, MAX_RETRIES, detail[:200])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            log.warning("Apify call failed on attempt %s/%s: %s",
                        attempt, MAX_RETRIES, exc)

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_S * attempt)

    raise ApifyError(f"Apify call failed after {MAX_RETRIES} attempts: {last_error}")


def _normalise_query(query: str) -> str:
    """Make a query safe for LinkedIn's search engine.

    Smart/curly quotes silently break exact-phrase matching -- the query still
    runs and still costs money, it just matches far more broadly than intended.
    Any query edited in a word processor or copied from a doc can pick these up,
    so normalising here rather than trusting the config is the safer default.
    """
    return (
        query.replace("“", '"').replace("”", '"')
        .replace("‘", "'").replace("’", "'")
        .strip()
    )


def count_boolean_operators(query: str) -> int:
    """Count AND/OR/NOT in a query.

    LinkedIn caps boolean operators (HarvestAPI documents 5 for this actor) and
    the behaviour past the cap is undocumented -- it may error, truncate, or
    silently ignore the excess, the last of which would mean paying full price
    for results that ignore half the query. Queries are validated against this
    before any run.
    """
    import re as _re
    return len(_re.findall(r"\b(?:AND|OR|NOT)\b", query))


def _parse_timestamp(posted_at: Any) -> datetime | None:
    """Extract a UTC datetime from the actor's postedAt object.

    Prefers the epoch-ms timestamp over the date string: it is unambiguous and
    timezone-free. Returns None if neither is usable, which causes the post to
    be dropped rather than guessed at.
    """
    if not isinstance(posted_at, dict):
        return None

    ts = posted_at.get("timestamp")
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            pass

    date_str = posted_at.get("date")
    if isinstance(date_str, str) and date_str:
        try:
            parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def validate_post(raw: dict, niche: str, query: str, max_age_hours: float) -> tuple[Post | None, str]:
    """Turn a raw dataset item into a Post, or explain why it cannot be.

    Returns (post, "") on success or (None, reason) on rejection. Every
    rejection carries a reason so the run log can prove no good lead was lost
    to a silent parsing failure.
    """
    if not isinstance(raw, dict):
        return None, "not a dict"

    post_id = raw.get("id")
    if not post_id or not isinstance(post_id, (str, int)):
        return None, "missing post id"
    post_id = str(post_id)

    content = raw.get("content")
    if not isinstance(content, str) or not content.strip():
        return None, "empty content"
    content = content.strip()
    if len(content) < 40:
        # Too short to contain a real, specific pain signal. A DM written from
        # 20 characters would necessarily be generic.
        return None, f"content too short ({len(content)} chars)"

    author = raw.get("author")
    if not isinstance(author, dict):
        return None, "missing author object"

    author_name = author.get("name")
    if not isinstance(author_name, str) or not author_name.strip():
        return None, "missing author name"

    author_url = author.get("linkedinUrl")
    if not isinstance(author_url, str) or "linkedin.com" not in author_url:
        return None, "missing or invalid author url"

    # Company pages post too; they cannot be DMed as a person.
    if author.get("type") == "company":
        return None, "author is a company page, not a person"

    posted_at = _parse_timestamp(raw.get("postedAt"))
    if posted_at is None:
        return None, "unparseable postedAt"

    age_hours = (datetime.now(timezone.utc) - posted_at).total_seconds() / 3600
    if age_hours > max_age_hours:
        return None, f"too old ({age_hours:.0f}h > {max_age_hours:.0f}h)"
    if age_hours < -2:
        return None, f"timestamp is in the future ({age_hours:.0f}h)"

    engagement = raw.get("engagement")
    likes = comments = 0
    if isinstance(engagement, dict):
        raw_likes = engagement.get("likes")
        raw_comments = engagement.get("comments")
        likes = raw_likes if isinstance(raw_likes, int) and raw_likes >= 0 else 0
        comments = raw_comments if isinstance(raw_comments, int) and raw_comments >= 0 else 0

    public_id = author.get("publicIdentifier")
    public_id = public_id.strip() if isinstance(public_id, str) else ""

    headline = author.get("info")
    headline = headline.strip() if isinstance(headline, str) else ""

    return Post(
        post_id=post_id,
        url=raw.get("linkedinUrl") if isinstance(raw.get("linkedinUrl"), str) else "",
        content=content,
        posted_at=posted_at,
        author_name=author_name.strip(),
        author_headline=headline,
        author_url=author_url,
        author_public_id=public_id,
        likes=likes,
        comments=comments,
        niche=niche,
        query=query,
        author_profile=author if author.get("location") else None,
    ), ""


def _cache_key(actor: str, payload: dict) -> str:
    blob = json.dumps({"actor": actor, "payload": payload}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def cache_read(actor: str, payload: dict) -> list[dict] | None:
    """Return a cached response for this exact call, or None."""
    path = CACHE_DIR / f"{_cache_key(actor, payload)}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("items")
    except (json.JSONDecodeError, OSError):
        return None


def cache_write(actor: str, payload: dict, items: list[dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{_cache_key(actor, payload)}.json"
    try:
        path.write_text(json.dumps({
            "actor": actor,
            "payload": payload,
            "cached_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "items": items,
        }, indent=1), encoding="utf-8")
    except OSError as exc:
        log.warning("Could not cache response: %s", exc)


class ApifyClient:
    def __init__(
        self,
        token: str,
        ledger: Ledger,
        *,
        dry_run: bool = False,
        use_cache: bool = False,
    ) -> None:
        self.token = token
        self.ledger = ledger
        self.dry_run = dry_run
        # When True, a cached response is used instead of a paid call. Cached
        # hits are never charged to the ledger, because no money moved.
        self.use_cache = use_cache

    def search_posts(
        self,
        *,
        queries: list[str],
        niche: str,
        max_posts_per_query: int,
        posted_limit: str,
        author_keywords: str | None = None,
        industry_ids: list[int] | None = None,
        enrich_authors: bool = False,
        max_age_hours: float = 24.0,
    ) -> tuple[list[Post], dict[str, int]]:
        """Run one post-search call for a niche's query set.

        Returns (validated posts, rejection reason counts). Cost is reserved
        against the ledger before the call and recorded from the real item count
        afterwards, so the ledger reflects actual spend rather than the ceiling.
        """
        if not queries:
            return [], {}

        requested = max_posts_per_query * len(queries)

        # Shrink to fit rather than abandoning: on a tight budget, a smaller
        # sweep beats no sweep.
        #
        # enrich_authors defaults to False. Inline enrichment costs $0.002 on
        # EVERY post retrieved, including the ~80% that free local filters
        # discard. Geo enrichment happens after filtering instead, via
        # enrich_profiles(), so it is only paid for real candidates.
        unit_price = PRICE_PER_POST + (PRICE_PER_INLINE_PROFILE if enrich_authors else 0)
        affordable = self.ledger.max_affordable_units(unit_price)
        if affordable <= 0:
            raise BudgetExceeded(
                f"{niche}: no budget left for post search "
                f"(${self.ledger.remaining_usd:.4f} remaining)"
            )
        if requested > affordable:
            max_posts_per_query = max(1, affordable // len(queries))
            requested = max_posts_per_query * len(queries)
            log.warning(
                "%s: trimmed to %s posts/query to fit remaining budget ($%.4f)",
                niche, max_posts_per_query, self.ledger.remaining_usd,
            )

        self.ledger.reserve(unit_price, requested, f"post-search: {niche}")

        payload: dict[str, Any] = {
            "searchQueries": [_normalise_query(q) for q in queries],
            "maxPosts": max_posts_per_query,
            # Only 24h/week/month filter server-side. '1h' and '3months' are
            # applied client-side by the actor, meaning we would be charged for
            # posts that are then discarded.
            "postedLimit": posted_limit,
            # 'date' over 'relevance': the 24h window already bounds the set,
            # recency is itself the intent signal, and date ordering is stable
            # between runs so pagination does not re-serve (and re-charge for)
            # posts we already have.
            "sortBy": "date",
            "profileScraperMode": "short",
            # Charged at full post rate each. Never enabled in the main sweep.
            "scrapeReactions": False,
            "scrapeComments": False,
        }
        if author_keywords:
            payload["authorKeywords"] = author_keywords
        if industry_ids:
            payload["authorsIndustryId"] = industry_ids

        if self.use_cache:
            cached = cache_read(POST_SEARCH_ACTOR, payload)
            if cached is not None:
                log.info("%s: %s items from cache (no charge)", niche, len(cached))
                posts, rejections = [], {}
                for item in cached:
                    post, reason = validate_post(item, niche, queries[0], max_age_hours)
                    if post is not None:
                        posts.append(post)
                    else:
                        rejections[reason] = rejections.get(reason, 0) + 1
                return posts, rejections

        if self.dry_run:
            log.info("[dry-run] would call %s with %s", POST_SEARCH_ACTOR, payload)
            return [], {}

        # maxTotalChargeUsd is enforced by Apify itself. It is the backstop for
        # the whole system: if the ledger's arithmetic is ever wrong, this still
        # stops the run from spending more than the remaining budget.
        remaining = max(0.01, round(self.ledger.remaining_usd, 4))
        url = (
            f"{APIFY_BASE}/acts/{POST_SEARCH_ACTOR}/run-sync-get-dataset-items"
            f"?token={self.token}&maxTotalChargeUsd={remaining}"
        )
        items = _http_post(url, payload, self.token)
        cache_write(POST_SEARCH_ACTOR, payload, items)

        self.ledger.record(len(items), unit_price, f"post-search: {niche}")

        posts: list[Post] = []
        rejections: dict[str, int] = {}
        for item in items:
            post, reason = validate_post(item, niche, queries[0], max_age_hours)
            if post is not None:
                posts.append(post)
            else:
                rejections[reason] = rejections.get(reason, 0) + 1

        log.info(
            "%s: %s items -> %s valid posts (%s rejected)",
            niche, len(items), len(posts), sum(rejections.values()),
        )
        return posts, rejections

    def enrich_profiles(self, public_ids: list[str]) -> dict[str, dict]:
        """Fetch full profiles for authors whose inline data lacked a location.

        Fallback path only: the inline "main" mode should already carry location
        at half this price. Returns {publicIdentifier: profile}.
        """
        ids = [pid for pid in dict.fromkeys(public_ids) if pid]
        if not ids:
            return {}

        affordable = self.ledger.max_affordable_units(PRICE_PER_STANDALONE_PROFILE)
        if affordable <= 0:
            log.warning("No budget left for profile enrichment; skipping %s", len(ids))
            return {}
        if len(ids) > affordable:
            log.warning("Trimming enrichment from %s to %s to fit budget",
                        len(ids), affordable)
            ids = ids[:affordable]

        self.ledger.reserve(PRICE_PER_STANDALONE_PROFILE, len(ids), "profile-enrich")

        if self.dry_run:
            log.info("[dry-run] would enrich %s profiles", len(ids))
            return {}

        url = (
            f"{APIFY_BASE}/acts/{PROFILE_ACTOR}/run-sync-get-dataset-items"
            f"?token={self.token}"
        )

        # VERIFIED BY LIVE TEST: batches of 10 return 10/10, but a batch of 16
        # returned only 1 item with no error. The actor degrades silently above
        # some threshold, which would look like "everyone failed the geo check"
        # rather than a bug. Chunking keeps every request inside the safe range.
        out: dict[str, dict] = {}
        total_items = 0
        for start in range(0, len(ids), PROFILE_BATCH_SIZE):
            chunk = ids[start : start + PROFILE_BATCH_SIZE]
            chunk_payload = {
                "publicIdentifiers": chunk,
                "profileScraperMode": "Profile details no email ($4 per 1k)",
            }
            if self.use_cache:
                cached = cache_read(PROFILE_ACTOR, chunk_payload)
                if cached is not None:
                    for item in cached:
                        if isinstance(item, dict) and item.get("publicIdentifier"):
                            out[item["publicIdentifier"]] = item
                    log.info("Profile chunk from cache: %s items (no charge)",
                             len(cached))
                    continue

            try:
                items = _http_post(url, chunk_payload, self.token)
                cache_write(PROFILE_ACTOR, chunk_payload, items)
            except ApifyError as exc:
                log.error("Profile chunk %s-%s failed: %s",
                          start, start + len(chunk), str(exc)[:150])
                continue

            total_items += len(items)
            for item in items:
                if not isinstance(item, dict):
                    continue
                pid = item.get("publicIdentifier")
                if isinstance(pid, str) and pid:
                    out[pid] = item

            if len(items) < len(chunk):
                returned = {
                    i.get("publicIdentifier") for i in items if isinstance(i, dict)
                }
                missing = [i for i in chunk if i not in returned]
                log.warning(
                    "Profile chunk returned %s of %s; no data for: %s",
                    len(items), len(chunk), missing[:5],
                )

        # Charge for what actually came back, not what was asked for.
        self.ledger.record(total_items, PRICE_PER_STANDALONE_PROFILE, "profile-enrich")
        log.info("Enrichment: %s ids in %s chunks -> %s profiles",
                 len(ids), (len(ids) + PROFILE_BATCH_SIZE - 1) // PROFILE_BATCH_SIZE,
                 len(out))
        return out
