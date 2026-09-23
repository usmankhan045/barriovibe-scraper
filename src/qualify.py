"""Lead qualification and scoring.

Recall-first by instruction: reject genuine non-fits, never a borderline real
lead. The gate is 55, not 70, and the model is told explicitly that missing a
real lead is the worse error.

The score is not the model's opinion alone. Free-tier models are inconsistent
scorers, so deterministic signals computed in code (grammar, engagement,
locale, anti-signals) adjust the model's number. That keeps scoring stable
across model fallbacks, which matters because the chain may swap models
mid-run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from config import grammar
from config.niches import BY_KEY
from config.services import BY_SLUG, OFFERABLE_SLUGS, catalogue_for_prompt
from src.llm import LLMError

log = logging.getLogger(__name__)


@dataclass
class Assessment:
    score: int
    pain: str
    service_slug: str
    reasoning: str
    is_buyer: bool
    adjustments: list[str] = field(default_factory=list)
    raw_model_score: int = 0


SYSTEM_PROMPT = """You are helping BarrioVibe, a software and AI agency, decide \
which LinkedIn posts are worth a human reading.

Your job is judgement, not rule-following. Read the post and ask one question: \
could this person plausibly want something BarrioVibe sells, now or soon?

BE GENEROUS. A human reviews everything you pass, so a mediocre lead costs \
them ten seconds. A missed lead costs them a customer. When genuinely unsure, \
score in the middle and let the human decide.

WHAT MAKES A LEAD
Someone running a business who has a problem, a want, a frustration, or a \
decision in front of them.

It does not need to be stated as a request. Most people never write "I need \
help" -- they describe a situation, complain about something, mention what \
went wrong last week, or ask their network a question. Read for the situation \
underneath the words rather than matching phrases. Someone venting about their \
week and someone posting a formal request can be equally good leads.

Weigh these up:
- Do they describe their OWN business, in their own voice?
- Is there a specific detail: a number, a tool, a timeframe, a named failure?
- Is something going wrong, or about to?
- Did they try something that did not work? These are the best leads of all: \
budget exists, the need is proven, and they now know they cannot do it alone.
- Can they plausibly decide to spend money, or influence someone who can?

WHAT IS NOT A LEAD
Only these. Do not invent further reasons to reject:
- They sell what BarrioVibe sells, and this post is them marketing it
- They are looking for a job, not for a supplier
- It is pure broadcast with no situation of their own: an announcement, a \
congratulation, a listicle, industry commentary
- There is genuinely no business context at all

Do NOT reject someone because their job title is junior, because the post is \
short, because the need is implied rather than stated, or because you are not \
certain BarrioVibe is the perfect fit. Those are all reasons to score lower, \
not to reject.

SCORING
  80-100  clear situation, specific detail, plausibly can buy
  55-79   real situation, some ambiguity about fit or authority
  40-54   might be something, hard to tell, a human should glance at it
  0-39    one of the four non-lead cases above

Pick the single service that best fits. If nothing fits well but the person is \
still worth contacting, use "none" and score on the situation alone.

Return ONLY a JSON object:
{
  "is_buyer": true or false,
  "score": 0 to 100,
  "pain": "one sentence naming their situation, in their own details",
  "service_slug": "best-fitting slug from the list, or none",
  "reasoning": "one short sentence on why this score"
}"""


def _build_prompt(post: dict, niche_key: str) -> str:
    niche = BY_KEY.get(niche_key)
    allowed = niche.service_slugs if niche else tuple(OFFERABLE_SLUGS)
    services = "\n".join(
        f"- {slug}: {BY_SLUG[slug].name}. {BY_SLUG[slug].description}"
        for slug in allowed
        if slug in BY_SLUG
    )
    return f"""Assess this post.

AUTHOR
Name: {post.get('author_name', 'unknown')}
Headline: {post.get('author_headline', 'unknown')}

POST
\"\"\"
{(post.get('content') or '')[:2000]}
\"\"\"

ENGAGEMENT: {post.get('likes', 0)} likes, {post.get('comments', 0)} comments

SERVICES BARRIOVIBE CAN OFFER THIS PERSON (pick one slug, or "none")
{services}

Return the JSON object now."""


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def apply_signals(model_score: int, post: dict) -> tuple[int, list[str]]:
    """Adjust the model's score using deterministic signals.

    These are computed in code rather than asked of the model, so they stay
    consistent even when the fallback chain swaps to a different model.
    """
    score = model_score
    notes: list[str] = []
    content = post.get("content") or ""
    signals = grammar.analyse(content)

    if signals["first_person_business"]:
        score += 8
        notes.append("+8 describes own business")
    elif signals["first_person"]:
        score += 4
        notes.append("+4 first person")

    # Penalties are deliberately modest. They stack, and a real lead that
    # happens to generalise in one sentence should not be pushed under the gate
    # by arithmetic the model never saw. The model reads the whole post; these
    # only nudge.
    if signals["vendor_voice"]:
        score -= 15
        notes.append("-15 vendor voice")

    if signals["generalising"]:
        score -= 6
        notes.append("-6 generalising about the category")

    if signals["seller_direction"] and not signals["buyer_direction"]:
        score -= 12
        notes.append("-12 offering rather than seeking")

    if signals["buyer_direction"]:
        score += 10
        notes.append("+10 actively looking")

    # Engagement: research found low-but-nonzero with discussion is the sweet
    # spot. Viral posts are influencer content whose author already has a full
    # inbox; zero engagement carries no corroboration either way.
    likes = post.get("likes", 0) or 0
    comments = post.get("comments", 0) or 0
    if likes > 300:
        score -= 10
        notes.append("-10 viral post (influencer content)")
    elif likes > 100:
        score -= 4
        notes.append("-4 high engagement")
    if comments >= 2 and likes <= 60:
        score += 6
        notes.append("+6 real discussion, small audience")

    # Specificity: numbers in a post usually mean a real situation rather than
    # a general observation.
    import re as _re
    if _re.search(r"\b\d+\s*(?:hours?|days?|weeks?|months?|years?|%|k\b)", content, _re.I):
        score += 5
        notes.append("+5 specific quantity")

    # Typos suggest a human writing quickly rather than proofread marketing.
    typo_markers = ("their were", "more easier", "alot ", "recieve", "seperate",
                    "definately", "occured", "tommorow")
    if any(t in content.lower() for t in typo_markers):
        score += 3
        notes.append("+3 unpolished writing")

    # Never let the deterministic signals move the score by more than 25 points
    # in either direction. They are a nudge, not a second opinion that can
    # overrule a model that actually read the post.
    delta = max(-25, min(25, score - model_score))
    return _clamp(model_score + delta), notes


class Qualifier:
    def __init__(self, client, *, dry_run: bool = False) -> None:
        self.client = client
        self.dry_run = dry_run

    def assess(self, post: dict, niche_key: str) -> Assessment:
        if self.dry_run:
            return Assessment(0, "[dry-run]", "", "[dry-run]", False)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(post, niche_key)},
        ]

        try:
            data = self.client.complete_json(messages, temperature=0.2, max_tokens=500)
        except LLMError as exc:
            log.warning("Qualification failed for %s: %s",
                        post.get("author_name"), str(exc)[:150])
            raise

        raw_score = data.get("score")
        try:
            raw_score = int(float(raw_score))
        except (TypeError, ValueError):
            raw_score = 0
        raw_score = _clamp(raw_score)

        is_buyer = bool(data.get("is_buyer", False))
        pain = str(data.get("pain") or "").strip()
        reasoning = str(data.get("reasoning") or "").strip()
        slug = str(data.get("service_slug") or "").strip()

        # A slug the model invented, or one this niche cannot sell, is dropped
        # rather than passed on: it would produce a DM offering the wrong thing.
        niche = BY_KEY.get(niche_key)
        allowed = set(niche.service_slugs) if niche else set(OFFERABLE_SLUGS)
        if slug not in allowed:
            if slug and slug != "none":
                log.info("Model picked out-of-scope service %r; clearing", slug)
            slug = ""

        # "not a buyer" is a strong opinion but not a veto. Capping at 45 kept
        # borderline leads under the 55 gate no matter what the deterministic
        # signals said, which is exactly the rigidity that loses real leads.
        if not is_buyer:
            raw_score = min(raw_score, 52)

        final_score, adjustments = apply_signals(raw_score, post)

        return Assessment(
            score=final_score,
            pain=pain,
            service_slug=slug,
            reasoning=reasoning,
            is_buyer=is_buyer,
            adjustments=adjustments,
            raw_model_score=raw_score,
        )
