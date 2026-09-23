"""Search queries per niche.

Built from verified verbatim phrases captured in research, not invented
phrasings. Design constraints, all of which cost money if ignored:

  1. LinkedIn caps boolean operators (~5 for this actor) and the behaviour past
     the cap is undocumented -- it may silently ignore the excess, which means
     paying full price for results that ignore half the query. Every query here
     is validated against that cap by tests.

  2. A query returning nothing still costs $0.001. So hyper-narrow queries that
     usually miss are a real waste. These are medium-breadth: one intent-phrase
     OR-group, tightened by the FREE server-side params (authorsIndustryId,
     authorKeywords) rather than by more boolean.

  3. Precision is spent on grammar and anti-signal filtering AFTER retrieval,
     which is free, rather than on boolean, which is capped and costs money.

  4. Straight quotes only. Smart quotes silently break exact-phrase matching.

Each query carries the research note explaining why it is here, so a future
edit can tell a verified phrase from a guess.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    text: str
    kind: str        # "pain" | "hiring" | "intent"
    confidence: str  # "verified" (captured verbatim) | "derived" | "hypothesis"
    note: str = ""


# ---------------------------------------------------------------------------
# B2B SaaS
# Strongest cluster is hiring FRUSTRATION (budget approved, no candidate) and
# agency/offshore failure (replacement mode), not plain hiring.
# ---------------------------------------------------------------------------
SAAS: tuple[Query, ...] = (
    Query(
        '("our team" OR "we need") AND ("senior developer" OR "senior engineer")',
        "hiring", "verified",
        "Employer-anchored. LIVE TEST: the unanchored version "
        "('still looking for a senior developer') matched job SEEKERS, not "
        "employers, because candidates use that exact phrasing about themselves.",
    ),
    Query(
        '("role has been open" OR "position has been open") AND ("months" OR "weeks")',
        "hiring", "verified",
        "Employer-side by construction: only an employer has an open role. "
        "Budget approved, no candidate. The highest-converting cluster.",
    ),
    Query(
        '("we are struggling to" OR "we cannot find") AND ("developers" OR "engineers")',
        "hiring", "verified",
        "First-person plural forces the employer side. Recruiters say 'my "
        "client is struggling', candidates say 'I am struggling'.",
    ),
    Query(
        '("our agency" OR "the agency") AND ("swapped" OR "junior" OR "failed")',
        "pain", "verified",
        "Agency bait-and-switch. Verified: 'quietly swapped their senior "
        "developers for cheaper, junior ones.' High replacement intent.",
    ),
    Query(
        '("stuck in" AND "POC") OR "never made it to production"',
        "pain", "verified",
        "AI pilot stalled. Near-zero noise -- non-buyers do not say this.",
    ),
    Query(
        '"we tried building it in-house" OR "tried to build it ourselves"',
        "pain", "verified",
        "Build failed, now open to buying. One of the two best AI triggers.",
    ),
    Query(
        '("our team is at capacity" OR "our team is stretched" OR "we are at capacity")',
        "pain", "verified",
        "Possessive-anchored. Verified: 'our in-house team was already at "
        "full capacity.'",
    ),
    Query(
        '("technical debt" OR "legacy") AND ("slowing" OR "blocking" OR "rewrite")',
        "pain", "derived",
        "Technical-buyer vocabulary, low noise from non-buyers.",
    ),
    Query(
        '("setting up" OR "expanding to") AND ("US entity" OR "Delaware")',
        "intent", "verified",
        "Maps to US company formation, NOT dev. Separate funnel, separate pitch.",
    ),
)

# ---------------------------------------------------------------------------
# Digital agencies
# Highest-noise niche. Directionality is essential: most "white label" posts
# are vendors OFFERING. The best-looking phrase found was posted by a
# competitor doing ICP research.
# ---------------------------------------------------------------------------
AGENCIES: tuple[Query, ...] = (
    Query(
        '"looking for" AND ("white label" OR "white-label") AND ("partner" OR "developer")',
        "intent", "verified",
        "Buyer-direction verb required. Bare 'white label' returns competitors.",
    ),
    Query(
        '"more client work" AND ("than we can handle" OR "in-house team")',
        "pain", "verified",
        "Verified best sentence-shape: 'more client work coming in than our "
        "in-house team can handle.'",
    ),
    Query(
        '("dev overflow" OR "development overflow") AND "hiring"',
        "pain", "verified",
        "CAUTION: the verbatim source of this phrase was a competitor doing ICP "
        "research. The audience-survey filter must catch those.",
    ),
    Query(
        '("burned by" OR "let down by") AND ("agency" OR "developer" OR "partner")',
        "pain", "verified",
        "Replacement mode. Verified: 'we have also been burned by a previous one.'",
    ),
    Query(
        '"dont have enough work" AND ("developer" OR "full time" OR "full-time")',
        "pain", "verified",
        "Tried hiring, workload does not justify FTE. Perfect white-label convert.",
    ),
    Query(
        '("clients are asking" OR "client asked") AND ("AI" OR "automation" OR "app")',
        "pain", "verified",
        "Sold something they cannot build. Verified: 'clients are starting to "
        "ask if they can just buy access to our AI workflows.'",
    ),
    Query(
        '("our developer" OR "our dev") AND ("ghosted" OR "went silent" OR "stopped responding")',
        "pain", "verified",
        "Dev noun REQUIRED: bare 'ghosted' on an agency account usually means "
        "the prospect ghosted them, which is a sales complaint, not our lead.",
    ),
)

# ---------------------------------------------------------------------------
# E-commerce / DTC
# Operational pain is the wedge. Marketing pain is the most agency-polluted
# category in the entire research -- deliberately under-weighted here.
# ---------------------------------------------------------------------------
ECOMMERCE: tuple[Query, ...] = (
    Query(
        '("new 3PL" OR "new fulfillment partner") AND ("looking" OR "need" OR "searching")',
        "intent", "verified",
        "Verified highest-intent string found: 'We need to find a new 3PL "
        "urgently.' 'New' implies displacing an incumbent.",
    ),
    Query(
        '"would not recommend" AND ("3PL" OR "fulfillment")',
        "intent", "verified",
        "Best precision-per-effort: no 3PL ever posts a negative-recommendation "
        "ask, so it self-filters vendors.",
    ),
    Query(
        '("our inventory" OR "our orders") AND ("does not match" OR "not syncing" OR "manually")',
        "pain", "verified",
        "The integration wedge: manual work between Shopify, 3PL and CRM.",
    ),
    Query(
        '"spreadsheet" AND ("every morning" OR "every month") AND ("our" OR "we")',
        "pain", "verified",
        "First-person required -- 'still using spreadsheets?' is ERP vendor copy.",
    ),
    Query(
        '("anyone know" OR "recommendations for") AND "Shopify developer"',
        "intent", "verified",
        "Purest buyer construction captured in research.",
    ),
    Query(
        '("developer" OR "dev") AND ("does not respond" OR "stopped responding" OR "disappeared")',
        "pain", "verified",
        "Abandoned-developer: urgent, low-competition, hard for vendors to fake.",
    ),
    Query(
        '("fired our" OR "parting ways with") AND ("agency" OR "3PL" OR "developer")',
        "pain", "verified",
        "Verified: 'I fired our marketing agency.' Active replacement window.",
    ),
)

# ---------------------------------------------------------------------------
# Professional services
# Best fit for the AI/automation offer. Back-office pitches only: document
# extraction and report assembly never touch the client relationship.
# ---------------------------------------------------------------------------
PROFESSIONAL: tuple[Query, ...] = (
    Query(
        '("manual data entry" OR "re-keying" OR "rekeying") AND ("our" OR "we")',
        "pain", "verified",
        "Core repetitive-work pain. First-person required.",
    ),
    Query(
        '("chasing clients" OR "chasing documents") AND ("every" OR "still")',
        "pain", "verified",
        "Client document collection: a universal professional-services drain.",
    ),
    Query(
        '("owner reports" OR "client reports" OR "monthly reporting") AND ("hours" OR "time sink" OR "manually")',
        "pain", "verified",
        "Strongest automation fit found. Verified: 'the spreadsheet-to-PDF "
        "pipeline was eating 3-4 hours every month.'",
    ),
    Query(
        '("document review" OR "reviewing contracts") AND ("hours" OR "manually")',
        "pain", "verified",
        "Direct RAG fit -- answers from their own documents with citations. "
        "Trimmed to 3 operators: the 6-operator version risked LinkedIn "
        "silently ignoring the excess and returning broad, paid-for noise.",
    ),
    Query(
        '"busy season" AND ("drowning" OR "behind" OR "capacity")',
        "pain", "derived",
        "Accounting-specific, strongly seasonal (Jan-Apr).",
    ),
    Query(
        '("tried ChatGPT" OR "tried AI") AND ("did not work" OR "gave up" OR "hallucinat")',
        "pain", "verified",
        "Failed DIY AI. They have the need and now know they need help.",
    ),
    Query(
        '("we are hiring" OR "we need to hire") AND ("admin" OR "coordinator" OR "assistant")',
        "hiring", "verified",
        "Employer-anchored. Budget already allocated for a human doing work "
        "that could be automated instead.",
    ),
)


# ---------------------------------------------------------------------------
# Cross-niche referral requests.
#
# LIVE TEST RESULT: "can anyone recommend" + a service noun was the highest
# yielding construction tested, with 4 of 5 results passing every filter. Other
# high-intent phrases returned 0-5 posts per MONTH. Asking peers for a referral
# is the one form of buying intent people still express publicly, because it
# reads as community participation rather than admitting a problem.
#
# These run across all niches rather than inside one.
# ---------------------------------------------------------------------------
REFERRAL: tuple[Query, ...] = (
    Query(
        '("can anyone recommend" OR "anyone recommend") AND ("developer" OR "development")',
        "intent", "verified",
        "LIVE TEST: best performing query, 4/5 results passed all filters.",
    ),
    Query(
        '("looking for recommendations" OR "any recommendations") AND ("agency" OR "developer" OR "automation")',
        "intent", "verified",
        "Referral-request construction, buyer-side by definition.",
    ),
    Query(
        '("can anyone recommend" OR "anyone know a good") AND ("bookkeeper" OR "accountant" OR "Shopify")',
        "intent", "verified",
        "Same construction across the service categories BarrioVibe covers.",
    ),
    Query(
        '("who do you use for" OR "who did you use for") AND ("development" OR "automation" OR "website")',
        "intent", "verified",
        "Peer-referral ask. Impossible for a vendor to post without inverting it.",
    ),
)

ALL_QUERIES: dict[str, tuple[Query, ...]] = {
    "saas": SAAS,
    "agencies": AGENCIES,
    "ecommerce": ECOMMERCE,
    "professional": PROFESSIONAL,
    "referral": REFERRAL,
}


def queries_for(niche_key: str) -> tuple[Query, ...]:
    return ALL_QUERIES.get(niche_key, ())
