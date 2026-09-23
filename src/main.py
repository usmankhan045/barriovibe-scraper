"""Pipeline entry point.

Stage order is deliberate, and the ordering is the cost-control design:

  1. SEARCH       paid   $0.002/post    Apify, 24h window enforced in code
  2. VALIDATE     free                  malformed, >24h old, company pages
  3. DEDUP        free                  post ID only, so a person can return
  4. HEADLINE     free                  recruiters, job seekers, hard vendors
  5. CONTENT      free                  job-hunt posts, spam, no-budget
  6. GRAMMAR      free                  competitor surveys, agency funnels
  7. BROADCAST    free                  announcements, listicles, commentary
  8. LOCALE       free                  excluded-market vocabulary
  9. GEO CHECK    paid   $0.004/lead    authoritative ISO country code
 10. QUALIFY      free tier             LLM scores 0-100, gate at 55
 11. WRITE DM     free tier             validated, regenerated until clean
 12. DELIVER      free                  Discord, one message per lead

Two principles govern the order:

Everything free runs before anything paid, and the geo check runs before
scoring so no LLM work is ever spent on someone who will be rejected for
location.

Stages 4-8 only remove UNAMBIGUOUS non-buyers. Judgement about whether a real
business situation is a lead belongs to stage 10, which reads the whole post.
An earlier design put that judgement in regex and lost genuine buyers whose
phrasing happened to resemble a vendor's.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from config import antisignals, grammar
from config.geo import (
    country_allowed,
    extract_country_code,
    locale_signal,
    prefilter_looks_excluded,
)
from config.niches import BY_KEY
from src.apify import ApifyClient, Post
from src.budget import (
    PRICE_PER_POST,
    PRICE_PER_STANDALONE_PROFILE,
    BudgetExceeded,
    Ledger,
)
from src.discord import DiscordSender
from src.dm import DMWriter, DMWriterError
from src.llm import SCORER_CHAIN, WRITER_CHAIN, LLMError, build_chain
from src.qualify import Qualifier
from src.queryplan import plan_run, plan_summary
from src.seen import SeenStore
from src.settings import ConfigError, load_settings

log = logging.getLogger("scrapper")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SEEN_PATH = DATA_DIR / "seen.json"
RUNS_DIR = DATA_DIR / "runs"


class Funnel:
    """Counts what happened at each stage so a thin day is explainable."""

    def __init__(self) -> None:
        self.retrieved = 0
        self.stages: Counter[str] = Counter()
        self.reasons: Counter[str] = Counter()

    def drop(self, stage: str, reason: str = "") -> None:
        self.stages[stage] += 1
        if reason:
            self.reasons[f"{stage}: {reason}"] += 1

    def report(self) -> str:
        lines = [f"Retrieved: {self.retrieved}"]
        for stage, count in self.stages.most_common():
            lines.append(f"  dropped at {stage}: {count}")
        return "\n".join(lines)


def run(settings, *, limit: int | None = None) -> int:
    started = datetime.now(timezone.utc)
    ledger = Ledger(cap_usd=settings.daily_budget_usd)
    funnel = Funnel()

    seen = SeenStore(SEEN_PATH)
    pruned = seen.prune()
    log.info("Dedup store: %s posts known (%s pruned)", len(seen), pruned)

    apify = ApifyClient(settings.apify_token, ledger, dry_run=settings.dry_run)
    keys = {
        "openrouter": settings.openrouter_api_key,
        "cerebras": settings.cerebras_api_key,
        "groq": settings.groq_api_key,
    }
    qualifier = Qualifier(build_chain(SCORER_CHAIN, keys), dry_run=settings.dry_run)
    writer = DMWriter(build_chain(WRITER_CHAIN, keys), dry_run=settings.dry_run)
    discord = DiscordSender(settings.discord_webhook_url, dry_run=settings.dry_run)

    # Ring-fence the geo-check budget before searching. Every lead must pass
    # geo, so running out of money there means paying to retrieve posts and
    # then throwing them away unverified.
    ledger.reserve_for_later(settings.daily_budget_usd * 0.40)

    # ---- 1. Search -------------------------------------------------------
    plan = plan_run(
        daily_budget_usd=settings.daily_budget_usd,
        price_per_post=PRICE_PER_POST,
        search_share=0.60,
    )
    log.info("Plan:\n%s", plan_summary(plan, PRICE_PER_POST))

    by_niche: dict[str, list] = {}
    for pq in plan:
        by_niche.setdefault(pq.niche, []).append(pq)

    posts: list[Post] = []
    for niche_key, queries in by_niche.items():
        niche = BY_KEY[niche_key]
        try:
            found, rejections = apify.search_posts(
                queries=[q.text for q in queries],
                niche=niche_key,
                max_posts_per_query=queries[0].max_posts,
                posted_limit=settings.posted_limit,
                author_keywords=niche.author_keywords,
                industry_ids=niche.industry_ids,
                enrich_authors=False,
                # Hard 24-hour window measured backwards from now, not from
                # the start of the day. A post 25 hours old is out.
                max_age_hours=24.0,
            )
            posts.extend(found)
            for reason, count in rejections.items():
                funnel.reasons[f"validate: {reason}"] += count
                funnel.stages["validate"] += count
        except BudgetExceeded as exc:
            log.warning("Stopping search: %s", exc)
            break
        except Exception as exc:  # noqa: BLE001
            log.error("Search failed for %s: %s", niche_key, exc)

    funnel.retrieved = len(posts) + funnel.stages.get("validate", 0)
    log.info("Retrieved %s valid posts", len(posts))

    if limit:
        posts = posts[:limit]

    # ---- 2-6. Free filters ----------------------------------------------
    survivors: list[Post] = []
    for post in posts:
        if seen.has_post(post.post_id):
            funnel.drop("dedup")
            continue

        reason = antisignals.vendor_headline_reason(post.author_headline, post.content)
        if reason:
            funnel.drop("anti-signal", reason.split(":")[0])
            continue

        reason = antisignals.content_reject_reason(post.content)
        if reason:
            funnel.drop("anti-signal", reason.split(":")[0])
            continue

        reason = grammar.hard_reject_reason(post.content)
        if reason:
            funnel.drop("grammar", reason)
            continue

        # NOTE: vendor_voice is deliberately NOT a rejection here. It is a
        # surface heuristic over phrasing, and a corpus audit showed it
        # flagging genuine buyers whose posts happened to use seller-adjacent
        # words ("DM me your portfolio and rates"). The scorer reads the whole
        # post and decides properly; the cost of scoring a dud is a fraction of
        # a cent, and the cost of dropping a buyer is a customer.
        signals = grammar.analyse(post.content)

        # Positive requirement, applied last and free: a post with no buying
        # or pain signal is not worth $0.004 to geo-check. A 101-post corpus
        # audit found ~3 real leads; the rest were thought leadership and job
        # hunts with no expressed need.
        if not antisignals.has_buying_signal(post.content):
            funnel.drop("no-signal", "no buying or pain language")
            continue

        if prefilter_looks_excluded(post.content, post.author_headline):
            funnel.drop("locale", "excluded market marker")
            continue
        if locale_signal(post.content, post.author_headline) == "south_asia":
            funnel.drop("locale", "south asia vocabulary")
            continue

        survivors.append(post)

    log.info("%s posts survived free filters", len(survivors))

    # ---- 7. Geo check (paid) --------------------------------------------
    geo_passed: list[tuple[Post, str]] = []
    ledger.release_reservation()  # the reserved stage has begun
    if survivors:
        affordable = ledger.max_affordable_units(PRICE_PER_STANDALONE_PROFILE)
        if affordable < len(survivors):
            log.warning(
                "Budget covers %s of %s geo lookups; checking the freshest",
                affordable, len(survivors),
            )
            survivors.sort(key=lambda p: p.posted_at, reverse=True)
            survivors = survivors[:affordable]

        ids = [p.author_public_id for p in survivors]
        log.info("Geo: %s survivors, %s with a publicIdentifier, budget covers %s",
                 len(survivors), len([i for i in ids if i]),
                 ledger.max_affordable_units(PRICE_PER_STANDALONE_PROFILE))
        try:
            profiles = apify.enrich_profiles(ids)
        except Exception as exc:  # noqa: BLE001
            log.error("Geo enrichment failed: %s", exc)
            profiles = {}

        for post in survivors:
            profile = profiles.get(post.author_public_id)
            code = extract_country_code(profile)
            if not code:
                funnel.drop("geo", "no location on profile")
                continue
            if not country_allowed(code):
                funnel.drop("geo", f"country {code}")
                continue
            geo_passed.append((post, code))

    log.info("%s leads in allowed countries", len(geo_passed))

    # ---- 8-9. Qualify and write -----------------------------------------
    leads: list[dict] = []
    for post, country in geo_passed:
        post_dict = {
            "author_name": post.author_name,
            "author_headline": post.author_headline,
            "content": post.content,
            "likes": post.likes,
            "comments": post.comments,
        }
        try:
            assessment = qualifier.assess(post_dict, post.niche)
        except LLMError as exc:
            log.error("Scoring failed for %s: %s", post.author_name, str(exc)[:120])
            funnel.drop("qualify", "scoring error")
            continue

        log.info(
            "SCORED %s | model=%s final=%s | %s | %s",
            post.author_name, assessment.raw_model_score, assessment.score,
            assessment.service_slug or "-", assessment.reasoning[:90],
        )
        log.info("   headline: %s", post.author_headline[:100])
        log.info("   post: %s", post.content[:180].replace("\n", " "))
        if assessment.adjustments:
            log.info("   adjustments: %s", ", ".join(assessment.adjustments))

        if assessment.score < settings.score_gate:
            funnel.drop("qualify", f"score {assessment.score}")
            continue

        lead = {
            "post_id": post.post_id,
            "author_name": post.author_name,
            "author_headline": post.author_headline,
            "author_url": post.author_url,
            "post_url": post.url,
            "post_excerpt": post.content[:400],
            "post_content": post.content,
            "country": country,
            "niche": BY_KEY[post.niche].label,
            "score": assessment.score,
            "pain": assessment.pain,
            "service_slug": assessment.service_slug,
            "posted_ago": f"{post.age_hours:.0f}h ago",
        }

        try:
            written = writer.write(lead)
            lead["message"] = written.text
        except DMWriterError as exc:
            # A lead whose DM cannot be written is still a lead. Deliver it
            # without a message rather than losing what was paid for.
            log.warning("DM failed for %s: %s", post.author_name, str(exc)[:120])
            lead["message"] = (
                "[No message written: the model could not produce one that "
                "passed validation. Write this one by hand.]"
            )

        from config.services import BY_SLUG
        service = BY_SLUG.get(assessment.service_slug)
        lead["service"] = service.name if service else "general"
        leads.append(lead)

    # Retry any lead whose message failed. Rate limits are transient and a lead
    # without a DM is the whole point of the pipeline lost, so it is worth one
    # more pass once the window has moved on.
    unwritten = [x for x in leads if x.get("message", "").startswith("[No message")]
    if unwritten:
        log.info("Retrying %s messages that failed on the first pass", len(unwritten))
        time.sleep(20)
        for lead in unwritten:
            try:
                lead["message"] = writer.write(lead).text
                log.info("Retry succeeded for %s", lead["author_name"])
            except DMWriterError as exc:
                log.warning("Retry failed for %s: %s",
                            lead["author_name"], str(exc)[:100])

    log.info("%s qualified leads", len(leads))

    # ---- 10. Deliver -----------------------------------------------------
    result = discord.send_all(leads) if leads else None

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    summary = (
        f"**Run complete** {started.date()}\n"
        f"Leads sent: {result.sent if result else 0}"
        f"{f' (failed {result.failed})' if result and result.failed else ''}\n"
        f"{funnel.report()}\n"
        f"{ledger.summary()}\n"
        f"Took {elapsed:.0f}s"
    )
    print("\n" + summary)

    if leads and not settings.dry_run:
        discord.send_summary(summary)
        for lead in leads:
            seen.add_post(lead["post_id"])
        seen.save()
        log.info("Dedup store updated: %s posts", len(seen))

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    ledger.write(RUNS_DIR / f"{started.strftime('%Y%m%d-%H%M%S')}-spend.json")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="BarrioVibe LinkedIn lead scraper")
    parser.add_argument("--dry-run", action="store_true",
                        help="scrape and score but send nothing and save nothing")
    parser.add_argument("--limit", type=int,
                        help="process at most N posts (for testing)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        settings = type(settings)(**{**settings.__dict__, "dry_run": True})

    log.info("Config: %s", settings.redacted)

    try:
        return run(settings, limit=args.limit)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
