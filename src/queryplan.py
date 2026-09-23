"""Query assembly and per-niche budget planning.

Two jobs:

  1. Attach a geo bias group to each query so retrieval skews toward
     allowlisted markets. The actor has NO location parameter (verified against
     its full 24-field input schema), so biasing through the query text is the
     only way to reduce non-tier-1 posts entering the funnel. It reduces waste;
     it does not replace the authoritative country-code check later.

  2. Split the daily budget across enabled niches and size each query so the
     run fits the cap. Empty queries cost $0.001 each, so query count is itself
     a cost: fewer, medium-breadth queries beat many narrow ones.

The geo group rotates by day so a single day's sweep is not locked to one
market, and every market gets covered across a week.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from config import niches as niche_config
from config.geo import GEO_QUERY_GROUPS
from config.queries import Query, queries_for
from src.apify import count_boolean_operators

log = logging.getLogger(__name__)

# LinkedIn's documented cap for this actor. Behaviour past it is undocumented
# and may be a silent ignore, which would mean paying full price for results
# that disregard half the query -- so a query that would exceed it goes out
# without the geo group rather than risking the whole query being degraded.
MAX_BOOLEAN_OPERATORS = 5


@dataclass(frozen=True)
class PlannedQuery:
    text: str
    niche: str
    kind: str
    confidence: str
    max_posts: int
    geo_biased: bool
    source: Query


def geo_group_for(run_date: date | None = None) -> str:
    """Pick the day's geo bias group, rotating through markets."""
    day = (run_date or date.today()).toordinal()
    return GEO_QUERY_GROUPS[day % len(GEO_QUERY_GROUPS)]


def apply_geo_bias(query_text: str, geo_group: str) -> tuple[str, bool]:
    """DISABLED after live testing. Always returns the query unchanged.

    Requiring a country name in the POST TEXT returns zero results: people do
    not write "United States" in a post about their own hiring problem. A live
    test confirmed a working query returning 3 posts dropped to 0 the moment a
    geo group was appended.

    Geography is therefore enforced only where it is authoritative: the
    `location.parsed.countryCode` check on the author's profile, which runs
    before any scoring or DM writing so no work is wasted on a rejected market.
    The free locale-lexicon check still rejects obvious South Asia signals
    before that paid lookup.
    """
    return query_text, False


def plan_run(
    *,
    daily_budget_usd: float,
    price_per_post: float,
    search_share: float = 0.60,
    run_date: date | None = None,
) -> list[PlannedQuery]:
    """Build the day's query plan within budget.

    `search_share` reserves the remainder for the authoritative geo check, so
    the funnel cannot break at its last step for lack of money -- the failure
    mode where posts are retrieved and then dropped unverified, wasting
    everything already spent on them.
    """
    enabled = niche_config.ENABLED
    if not enabled:
        log.warning("No niches enabled; nothing to plan")
        return []

    search_budget = daily_budget_usd * search_share
    shares = niche_config.budget_shares()
    geo_group = geo_group_for(run_date)

    plan: list[PlannedQuery] = []
    for niche in enabled:
        niche_budget = search_budget * shares[niche.key]
        queries = queries_for(niche.key)
        if not queries:
            log.warning("Niche %s has no queries defined", niche.key)
            continue

        affordable_posts = int(niche_budget / price_per_post)
        per_query = max(1, affordable_posts // len(queries))

        for query in queries:
            text, biased = apply_geo_bias(query.text, geo_group)
            plan.append(PlannedQuery(
                text=text,
                niche=niche.key,
                kind=query.kind,
                confidence=query.confidence,
                max_posts=per_query,
                geo_biased=biased,
                source=query,
            ))

    return plan


def plan_summary(plan: list[PlannedQuery], price_per_post: float) -> str:
    if not plan:
        return "Empty plan."
    by_niche: dict[str, list[PlannedQuery]] = {}
    for pq in plan:
        by_niche.setdefault(pq.niche, []).append(pq)

    lines = []
    total_posts = 0
    for key, queries in by_niche.items():
        label = niche_config.BY_KEY[key].label
        posts = sum(q.max_posts for q in queries)
        biased = sum(1 for q in queries if q.geo_biased)
        total_posts += posts
        lines.append(
            f"  {label:32} {len(queries)} queries x {queries[0].max_posts:>3} "
            f"= {posts:>4} posts  (${posts * price_per_post:.3f}, "
            f"{biased}/{len(queries)} geo-biased)"
        )
    lines.append(
        f"  {'TOTAL':32} {len(plan)} queries, {total_posts} posts max, "
        f"${total_posts * price_per_post:.3f}"
    )
    return "\n".join(lines)
