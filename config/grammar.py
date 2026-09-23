"""Grammatical operator-vs-vendor discrimination.

Three independent research passes converged on the same finding: the reliable
way to tell a real operator from a vendor performing their prospect's pain is
GRAMMAR, not vocabulary. Vendors write marketing copy that uses the operator's
exact words on purpose, so keyword matching cannot separate them.

    Second person + question mark  -> VENDOR
        "Drowning in tickets?"  "Still using spreadsheets?"
        "You're a DTC brand looking for external help..."

    First person + declarative    -> OPERATOR
        "We're drowning in tickets."
        "We need to find a new 3PL urgently."

Verified example of why keywords fail: a warehouse-software vendor publishes
"The wrong WMS creates manual work, slows down client onboarding, and turns
billing into a weekly headache" -- indistinguishable from a real complaint at
the keyword level, and completely distinguishable at the grammar level.

This module returns SIGNALS, not verdicts. The qualifier weighs them alongside
the post content. Only the hardest tells (the capitalised DM trigger) are
treated as outright rejections.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# First-person ownership: the author is describing their own situation.
# ---------------------------------------------------------------------------
FIRST_PERSON_RE = re.compile(
    r"\b(?:we|we're|weve|we've|our|ours|us|i|i'm|im|i've|ive|my|mine)\b",
    re.IGNORECASE,
)

# Stronger still: first person attached to a business noun. "our warehouse",
# "my team", "we hired" -- these are very hard for marketing copy to fake,
# because vendor copy addresses "your" business, not "our" business.
FIRST_PERSON_BUSINESS_RE = re.compile(
    r"\b(?:our|my)\s+"
    r"(?:team|company|business|store|shop|agency|firm|warehouse|clients?|"
    r"customers?|developers?|devs?|engineers?|staff|stack|crm|erp|website|"
    r"site|app|platform|systems?|tools?|process|ops|operations|books|"
    r"accounts?|inventory|orders?|tickets?|support|roadmap|product)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Second person: vendor copy addresses the reader's business.
# ---------------------------------------------------------------------------
# Addressing an indefinite crowd rather than the reader personally. This is how
# people ask their network for a recommendation, and it must never be mistaken
# for vendor copy addressing a prospect.
CROWD_ASK_RE = re.compile(
    r"\b(?:any\s?(?:one|body)|some\s?(?:one|body)|who\s+(?:here|knows)|"
    r"does\s+any\s?(?:one|body)|can\s+any\s?(?:one|body)|"
    r"has\s+any\s?(?:one|body)|everyone|connections|network|folks|friends)\b",
    re.IGNORECASE,
)

SECOND_PERSON_RE = re.compile(
    r"\b(?:you|you're|youre|your|yours|you'll|youll|you've|youve)\b",
    re.IGNORECASE,
)

# Subject-dropped first person. Real operators frequently omit the pronoun,
# especially when venting: "Have had two roles open for months", "Spent all
# weekend on this", "Been looking for a dev for three months". Marketing copy
# almost never does this -- it is proofread into full sentences.
SUBJECT_DROPPED_RE = re.compile(
    r"(?:^|\n|\. )\s*(?:have had|had|been|spent|tried|hired|lost|struggled|"
    r"looking for|still looking|just spent|finally|ended up)\b",
    re.IGNORECASE,
)

# Impersonal category assertion: a general claim about a product category or
# business type, with no owner attached. This is how vendor SEO copy is written
# so it matches the buyer's search terms without ever saying "we sell this".
CATEGORY_ASSERTION_RE = re.compile(
    r"\bthe\s+(?:wrong|right|best|worst|old|legacy|typical|average)\s+"
    r"[a-z]{2,20}\s+(?:creates?|causes?|leads?|means?|results?|costs?|makes?|"
    r"turns?|slows?|breaks?|kills?)\b",
    re.IGNORECASE,
)

# Generalising subject: "most agencies", "every founder", "9 out of 10 brands".
# A real operator writes about their own company; a vendor writes about the
# category. This is the single clearest content-marketing tell.
GENERALISING_RE = re.compile(
    r"\b(?:most|many|every|all|9 out of 10|90%|majority of|some)\s+"
    r"(?:agenc|founder|brand|compan|startup|business|team|saas|ecom|"
    r"marketer|owner|operator|client|merchant|firm|store)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Hard rejections -- near-100% vendor in verified sampling.
# ---------------------------------------------------------------------------

# "DM me SCALE", "DM me 'FLYWHEEL'", "Comment GROWTH below".
# A capitalised one-word trigger is the signature of an agency funnel.
DM_TRIGGER_RE = re.compile(
    r"\b(?:dm|pm|message|comment|type)\s+(?:me\s+)?['\"]?[A-Z]{3,}['\"]?",
)

# Credential-stacking openers: "After 15 years scaling 8-figure brands",
# "I've audited over 200 DTC brands". Always a seller.
CREDENTIAL_STACK_RE = re.compile(
    r"\b(?:after|over|i(?:'ve| have))\s+"
    r"(?:\d+\+?\s*(?:years?|brands?|clients?|companies|stores?)|"
    r"audited|scaled|helped|worked with)\s+"
    r"(?:\d+|over \d+|hundreds|dozens)",
    re.IGNORECASE,
)

# Round-multiple outcome claims: "2x to 6x ROI", "$10K to $100K/mo".
OUTCOME_CLAIM_RE = re.compile(
    r"(?:\d+x\s*(?:→|->|to)\s*\d+x|"
    r"\$\d+[km]\s*(?:→|->|to)\s*\$\d+[km]|"
    r"\b(?:scaled|grew|took)\s+(?:them|it|us)?\s*from\s+\$?\d+)",
    re.IGNORECASE,
)

# Emoji-bulleted listicles: near-universal in vendor content, rare in genuine
# operator venting.
EMOJI_BULLET_RE = re.compile(r"(?:^|\n)\s*(?:🔹|✅|➡|→|💥|🚀|📈|👉|✔)")

# Soft-sell closers.
SOFT_SELL_RE = re.compile(
    r"\b(?:book a call|book a demo|learn more|link in bio|link in comments|"
    r"free audit|free consultation|let's chat|happy to share how|"
    r"that's what we do at|follow me for|follow for more)\b",
    re.IGNORECASE,
)

# Agency outsourcing its own overflow -- looks like a buyer, is a competitor.
OVERFLOW_RE = re.compile(r"\boverflow\s+(?:work|capacity|projects?)\b", re.IGNORECASE)

# "our clients" means the author serves clients: they are a vendor. Distinct
# from "our customers", which a product business legitimately says.
HAS_CLIENTS_RE = re.compile(r"\bour\s+clients?\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Competitor market research. The subtlest false positive there is: a vendor
# asks the audience to describe their pain in a category the vendor sells, so
# the post reads exactly like a buyer surfacing demand.
#
# Verified examples that fooled keyword matching completely:
#   "Agency owners, how are you handling dev overflow without hiring
#    full-time?"                       -- posted by a dev agency doing ICP research
#   "Marketing agency owners: What is your absolute biggest headache when
#    working with a white-label web developer"  -- posted by a developer
#                                                  building that offering
#
# The tell is the vocative: addressing a professional group by name and then
# asking them about their problems. A real operator describes their own
# situation; they do not survey their peer group.
# ---------------------------------------------------------------------------
# The group noun must be ADDRESSED, not SOUGHT. A vocative ("Founders, what is
# your biggest headache?") is a vendor surveying prospects. The same noun as
# the object of a search ("looking for a freelancer who can help") is a buyer.
#
# Requiring a vocative boundary -- start of line, or a comma or colon straight
# after the noun -- separates the two without listing either case.
AUDIENCE_SURVEY_RE = re.compile(
    r"(?:^|\n|\.\s+)\s*"
    r"(?:hey |hi |ok |so )?"
    # An optional qualifier ("marketing", "ecommerce", "saas") then the group
    # noun, then an optional role word. Built compositionally rather than
    # enumerated, so new group names work without editing this.
    r"(?:\w+\s+){0,2}"
    r"(?:agenc\w*|founders?|ceos?|owners?|freelancers?|devs?|developers?|"
    r"marketers?|operators?|consultants?|accountants?|lawyers?|recruiters?|"
    r"brands?|merchants?|sellers?|folks|people|everyone)"
    r"(?:\s+(?:owners?|founders?|leads?|managers?))?"
    r"\s*[,:]\s*"
    r"(?:what|how|who|which|when|why|do you|are you|have you|"
    r"tell me|i'm curious|im curious|quick question)\b",
    re.IGNORECASE,
)

# Explicit admissions of building an offering -- these appear in the body of
# market-research posts and are unambiguous.
BUILDING_OFFERING_RE = re.compile(
    r"\b(?:i'?m |i am |we'?re |we are )?"
    r"(?:transitioning my business to offer|building (?:my|our) "
    r"(?:agency )?offering|before i start pitching|"
    r"(?:want|looking) to build (?:my|our) (?:agency )?(?:offering|service)|"
    r"validating (?:this|an|my) (?:idea|offer)|doing some (?:market )?research)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Directionality. On LinkedIn most "white label" / "partner" posts are vendors
# OFFERING, not agencies SEEKING. Bare keyword matching returns competitors.
# ---------------------------------------------------------------------------
# The author asking OTHERS to send credentials, rates or availability. The
# person being asked to prove themselves is the supplier, so the author is the
# buyer.
# The author stating what THEY supply. Distinguishes "send me your rates"
# (buyer collecting quotes) from "we build X, DM me" (seller collecting leads).
SELLER_OFFERS_RE = re.compile(
    r"\b(?:we|i)\s+(?:build|make|design|develop|provide|offer|deliver|handle|"
    r"specialise|specialize|help)\b"
    r"|\b(?:our|my)\s+(?:team|agency|studio|company|service|portfolio)\b"
    r"|\b(?:now\s+|currently\s+)?(?:offering|offer|available for|taking on|"
    r"open for|accepting|onboarding)\b"
    r"|\bwhite[\s-]?label\s+(?:development|services?|work|partner)\b",
    re.IGNORECASE,
)

INVITES_PITCHES_RE = re.compile(
    r"\b(?:dm|pm|message|send|share|drop|forward)\s+me\s+"
    r"(?:\w+\s+){0,3}"
    r"(?:your|a|the)?\s*"
    r"(?:portfolio|rates?|pricing|quote|cv|profile|work|examples?|"
    r"availability|details|links?|proposal)",
    re.IGNORECASE,
)

SELLER_DIRECTION_RE = re.compile(
    r"\b(?:offering|we provide|we offer|providing|taking on|now accepting|"
    r"open for|available for|for hire|seeking (?:partnerships?|agencies|clients)|"
    r"partner with (?:us|me)|work with (?:us|me)|our team (?:of|handles|builds)|"
    r"we specialis|we specializ|dm me if you need|reach out if you need|"
    r"happy to share how we|white[ -]?label (?:friendly|services? available))\b",
    re.IGNORECASE,
)

BUYER_DIRECTION_RE = re.compile(
    r"\b(?:looking for|we need|i need|need a|need an|anyone know|"
    r"can anyone recommend|recommendations? for|who do you use|"
    r"burned by|let down by|any recommendations|searching for|"
    r"trying to find|in the market for|help me find|suggestions for|"
    r"has anyone used|would love (?:a )?recommend)\b",
    re.IGNORECASE,
)

# "Ghosted" on an agency account ~90% means the PROSPECT ghosted them -- a
# sales-pipeline complaint, not a delivery-capacity problem. Only counts as a
# delivery signal when a dev noun is nearby.
GHOSTED_DEV_RE = re.compile(
    r"\b(?:developer|dev|devs|contractor|freelancer|agency|team|designer|"
    r"programmer|engineer)\b[^.!?\n]{0,60}\b(?:ghosted|went silent|went dark|"
    r"stopped responding|disappeared|never replied)\b"
    r"|\b(?:ghosted|went silent|went dark|stopped responding|disappeared)\b"
    r"[^.!?\n]{0,60}\b(?:developer|dev|devs|contractor|freelancer|agency|"
    r"team|designer|programmer|engineer)\b",
    re.IGNORECASE,
)

GHOSTED_ANY_RE = re.compile(
    r"\b(?:ghosted|went silent|went dark|stopped responding)\b", re.IGNORECASE
)


HARD_REJECT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("competitor market research (audience survey)", AUDIENCE_SURVEY_RE),
    ("building their own offering", BUILDING_OFFERING_RE),
    ("dm trigger (agency funnel)", DM_TRIGGER_RE),
    ("credential stacking (seller)", CREDENTIAL_STACK_RE),
    ("outcome claim (seller)", OUTCOME_CLAIM_RE),
    ("soft-sell closer", SOFT_SELL_RE),
    ("agency overflow work", OVERFLOW_RE),
)


def hard_reject_reason(content: str | None) -> str | None:
    """Reject only the near-certain vendor tells. Returns a reason or None."""
    if not content:
        return "empty content"
    for label, pattern in HARD_REJECT_RULES:
        if pattern.search(content):
            return label
    return None


def analyse(content: str | None) -> dict[str, object]:
    """Grammar signals for the qualifier to weigh.

    Deliberately returns evidence rather than a verdict: a post can open
    impersonally and still be a genuine lead, so a single impersonal sentence
    must not be fatal on its own.
    """
    text = content or ""
    if not text.strip():
        return {
            "first_person": False, "first_person_business": False,
            "second_person": False, "generalising": False,
            "second_person_hook": False, "bare_interrogative_hook": False,
            "seller_direction": False, "buyer_direction": False,
            "ghosted_by_dev": False, "ghosted_by_prospect": False,
            "emoji_bullets": 0, "mentions_own_clients": False,
            "question_hook": False, "operator_voice": False, "vendor_voice": False,
        }

    # The hook line is the first non-empty line: where vendor copy puts its
    # second-person question ("Drowning in tickets?").
    hook = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    question_hook = hook.endswith("?") and bool(SECOND_PERSON_RE.search(hook))

    # Asking the crowd for something is NOT a vendor hook, even though it is
    # phrased impersonally. The distinction is what the question is about:
    #
    #   vendor: asks about the READER's situation    "Drowning in tickets?"
    #   buyer:  asks the crowd for a THING           "Anyone know a good dev?"
    #
    # An address to an indefinite audience ("anyone", "does anybody", "who
    # here") is the buyer form and must never count as a vendor tell.
    crowd_ask = bool(CROWD_ASK_RE.search(hook))

    second_person_hook = (
        not crowd_ask
        and bool(SECOND_PERSON_RE.search(hook))
        and not bool(FIRST_PERSON_RE.search(hook))
    )

    # A bare interrogative hook with no first-person subject is vendor copy:
    #   "Drowning in support tickets?"
    #   "Still Using Spreadsheets to Manage Inventory?"
    # Nobody opens a description of their own problem this way -- an operator
    # asking for help says "our checkout is broken, anyone know a dev?", which
    # carries "our". The exception is a genuine question to peers, which is why
    # this only fires when the hook has no first-person marker anywhere.
    bare_interrogative_hook = (
        hook.endswith("?")
        and not crowd_ask
        and not FIRST_PERSON_RE.search(hook)
        and len(hook.split()) <= 12
    )

    first_person = bool(FIRST_PERSON_RE.search(text))
    first_person_business = bool(FIRST_PERSON_BUSINESS_RE.search(text))
    second_person = bool(SECOND_PERSON_RE.search(text))
    generalising = bool(GENERALISING_RE.search(text))
    emoji_bullets = len(EMOJI_BULLET_RE.findall(text))
    mentions_own_clients = bool(HAS_CLIENTS_RE.search(text))

    # Subject-dropped operator voice. Real posts often omit the pronoun:
    # "Have had two open roles for months", "Spent the whole weekend fixing".
    # Without this, genuine hiring-frustration posts -- the highest-value
    # cluster in the research -- are silently lost.
    subject_dropped = bool(SUBJECT_DROPPED_RE.search(text))

    # Impersonal category assertion with no owner: the signature of vendor copy
    # written to rank for the buyer's keywords. "The wrong WMS creates manual
    # work, slows client onboarding, and turns billing into a headache."
    impersonal_assertion = (
        not first_person
        and not subject_dropped
        and bool(CATEGORY_ASSERTION_RE.search(text))
    )

    # Operator voice: talks about their own business, and is not primarily
    # addressing the reader's.
    operator_voice = (
        first_person_business
        or subject_dropped
        or (first_person and not question_hook)
    )

    # Directionality: is this person shopping, or selling? On LinkedIn most
    # "white label" and "partner" posts are vendors offering, not agencies
    # seeking, so a keyword match alone returns competitors.
    seller_direction = bool(SELLER_DIRECTION_RE.search(text))
    buyer_direction = bool(BUYER_DIRECTION_RE.search(text))

    # WHO SUPPLIES WHOM. This is the reliable question, and vocabulary alone
    # cannot answer it because both sides use the same words ("DM me", "rates",
    # "portfolio"). What separates them is whether the author names a thing
    # THEY supply.
    #
    #   author says what they supply            -> seller
    #   author asks others what they supply     -> buyer
    #
    # An author who does both ("we build MVPs, send me your portfolio") is
    # recruiting or collecting leads, and is treated as a seller.
    author_supplies = bool(SELLER_OFFERS_RE.search(text))
    author_asks_others_to_supply = bool(INVITES_PITCHES_RE.search(text))

    if author_asks_others_to_supply and not author_supplies:
        buyer_direction = True
        seller_direction = False
    elif author_supplies:
        seller_direction = True

    # "Ghosted" without a dev noun nearby means the PROSPECT ghosted them: a
    # sales complaint, not a delivery-capacity problem. Distinguishing these
    # keeps the pipeline from filling with the wrong kind of pain entirely.
    ghosted_by_dev = bool(GHOSTED_DEV_RE.search(text))
    ghosted_by_prospect = bool(GHOSTED_ANY_RE.search(text)) and not ghosted_by_dev

    # Vendor voice. Two independent tells, OR one decisive tell on its own.
    # A second-person question hook and a generalising subject are each strong
    # enough alone: no genuine operator opens by asking the reader about the
    # reader's own business, or by describing what "most brands" do.
    # Offering a service without any sign of shopping for one is decisive on
    # its own: this is a vendor advertising, whatever else the post contains.
    decisive = (
        question_hook or second_person_hook or bare_interrogative_hook
        or generalising or impersonal_assertion
        or (seller_direction and not buyer_direction)
    )
    vendor_signals = sum((
        question_hook,
        second_person_hook,
        bare_interrogative_hook,
        generalising,
        impersonal_assertion,
        emoji_bullets >= 2,
        mentions_own_clients,
        second_person and not first_person,
        seller_direction and not buyer_direction,
    ))
    # First-person business context rescues a post from a single weak tell:
    # someone can say "our clients" and still be describing their own pain.
    # Direction outranks every hook heuristic. Someone asking others to send
    # credentials is buying, whatever the surface phrasing looks like: "your"
    # in "send me your rates" refers to the supplier, not to the reader.
    if author_asks_others_to_supply and not author_supplies:
        vendor_voice = False
    else:
        vendor_voice = (decisive or vendor_signals >= 2) and not (
            first_person_business and vendor_signals < 2
        )

    return {
        "first_person": first_person,
        "first_person_business": first_person_business,
        "second_person": second_person,
        "generalising": generalising,
        "emoji_bullets": emoji_bullets,
        "mentions_own_clients": mentions_own_clients,
        "question_hook": question_hook,
        "seller_direction": seller_direction,
        "buyer_direction": buyer_direction,
        "ghosted_by_dev": ghosted_by_dev,
        "ghosted_by_prospect": ghosted_by_prospect,
        "second_person_hook": second_person_hook,
        "bare_interrogative_hook": bare_interrogative_hook,
        "operator_voice": operator_voice,
        "vendor_voice": vendor_voice,
    }
