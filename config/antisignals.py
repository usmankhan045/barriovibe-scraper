"""Author and content anti-signals.

Research finding that drives this file: when scraping posts that match obvious
pain keywords, the MAJORITY are written by competing vendors rather than
buyers. A sample of posts adjacent to one "do you need a CTO?" post was ~70%
dev shops and fractional-CTO agencies selling the same services BarrioVibe
sells.

So the author filter runs FIRST, before any phrase matching and before any
LLM call. It is free and removes the bulk of the noise.

IMPORTANT: these filters are deliberately PERMISSIVE. A corpus audit found
rigid keyword gates rejecting genuine buyers on job title alone. They now
remove only unambiguous non-buyers (recruiters, job seekers, spam, excluded
markets); anything ambiguous goes to the scorer, which reads the whole post.

Every rule here REJECTS. Nothing in this file can admit a lead. That asymmetry
is deliberate: the cost of a false reject is one lost lead, and the rules are
written narrowly to keep that rare.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# 1. Competing sellers. Same services, different logo.
# Matched against the author's HEADLINE only, never the post body -- a founder
# may legitimately write "we hired an agency" in a post, and that is a lead,
# not a rejection.
# ---------------------------------------------------------------------------
# Job seekers and individual contributors. Live testing showed hiring-related
# queries retrieve mostly CANDIDATES ("still looking", "open to work") rather
# than employers. They are real people with real frustration, but they are not
# buyers of agency services.
JOBSEEKER_HEADLINE_TERMS = (
    "open to work", "opentowork", "immediate joiner", "actively seeking",
    "seeking new opportunities", "looking for opportunities",
    "aspiring", "student", "intern at", "fresher", "graduate",
    "ex-", "formerly at", "career break", "between roles",
)

# Individual contributor titles: these people have the problem but not the
# budget or authority to buy a solution.
IC_HEADLINE_TERMS = (
    "software engineer at", "developer at", "engineer at",
    "senior engineer", "senior developer", "full stack developer",
    "frontend developer", "backend developer", "data analyst",
    "system engineer", "qa engineer", "test engineer", "devops engineer",
    "designer at", "consultant at", "analyst at", "specialist at",
    "associate at", "manager at tata", "technical recruiter",
)

VENDOR_HEADLINE_TERMS = (
    # Agency/shop self-description
    "agency", "studio", "labs", "softtech", "infotech", "technologies",
    "solutions", "software house", "dev shop", "development company",
    "it services", "outsourcing", "offshore", "nearshore",
    # Service-selling role descriptions
    "fractional cto", "virtual cto", "cto as a service", "staff augmentation",
    "we build", "we help startups", "we help companies", "helping startups",
    "helping founders", "helping brands", "helping businesses",
    # Recruiting/staffing -- they post the exact hiring-frustration language
    # we hunt for, but they are selling the shortage, not suffering it.
    "recruitment", "recruiter", "talent acquisition", "staffing",
    "executive search", "headhunter", "talent partner", "hiring partner",
    # Lead-gen / growth sellers
    "lead generation", "growth hacker", "appointment setting", "cold email",
    "b2b leads", "smma", "social media marketing agency",
    # Coaches and course sellers
    "coach", "mentor", "course creator", "business coach", "consultant to",
    "i teach", "i help you",
)

# Exact-ish role titles that are unambiguously vendor-side even without other
# signals. Kept separate because these need word-boundary matching to avoid
# rejecting e.g. "Head of Consulting" at a real buyer.
VENDOR_HEADLINE_PATTERNS = (
    # "I help European enterprises hire...", "I help agencies fix..." -- the
    # canonical service-seller headline construction on LinkedIn.
    r"\bi help\b",
    r"\bhelping\s+(?:\w+\s+){0,2}(?:to\s+)?(?:hire|scale|grow|build|fix|save|automate|with)",
    # "...at a fraction of the cost", "...without the overhead" -- pricing
    # claims in a headline mean the person is selling.
    r"\bfraction of the (?:cost|price)\b",
    r"\bwithout the (?:overhead|cost|hassle)\b",
    r"\bfounder\b.{0,30}\bagency\b",
    r"\bceo\b.{0,30}\b(agency|studio|labs)\b",
    r"\bbdm\b",
    r"\bbusiness development\b.{0,25}\b(agency|software|it|outsourc)",
    r"\bsales\b.{0,20}\b(agency|software house|outsourc)",
)

# ---------------------------------------------------------------------------
# 2. Engagement bait / thought leadership. High-emotion pain language, zero
# buying intent. Matched against the POST BODY.
# ---------------------------------------------------------------------------
BAIT_PHRASES = (
    "what do you think?",
    "thoughts? 👇",
    "thoughts 👇",
    "what's been your experience",
    "whats been your experience",
    "curious how you think about",
    "agree or disagree",
    "am i wrong?",
    "got value? kindly repost",
    "kindly repost",
    "repost ♻",
    "follow me for more",
    "follow for more",
    "comment below and i'll",
    "comment 'yes'",
    'comment "yes"',
    "most founders don't realise",
    "most founders don't realize",
    "most startups don't fail because",
    "the biggest lie in",
    "here's the truth",
    "heres the truth",
    "unpopular opinion",
    "hot take:",
    "let that sink in",
)

# Vendor case studies dressed as buyer pain -- the trickiest class, because
# they quote a real buyer's pain verbatim.
CASE_STUDY_TELLS = (
    "a client we",
    "a startup we",
    "a saas startup we recently",
    "one of our clients",
    "a founder we worked with",
    "here's how one",
    "heres how one",
    "we recently helped",
    "we helped a",
    "case study:",
    "how we helped",
    "our client was struggling",
)

# Job-search posts. LIVE RUN: these reached the paid geo check at $0.004 each
# before the scorer rejected them. The referral queries ("can anyone recommend",
# "looking for recommendations") match job seekers asking for role referrals as
# readily as businesses asking for vendor referrals, so the body must be
# checked, not just the headline.
JOBSEEKER_CONTENT_TELLS = (
    "looking for new job",
    "looking for a new job",
    "looking for job opportunities",
    "looking for new opportunities",
    "open to new opportunities",
    "open to work",
    "seeking new opportunities",
    "seeking a new role",
    "seeking employment",
    "actively looking for a role",
    "actively looking for a position",
    "my notice period",
    "immediately available for",
    "available for hire",
    "please refer me",
    "any leads or recommendations",
    "would be grateful for any leads",
    "recently graduated",
    "recently laid off",
    "was laid off",
    "my resume",
    "my cv is attached",
    "attached is my cv",
    "hire me",
    "#opentowork",
    # Variants seen in the live run that the literal list missed.
    "looking for remote opportunities",
    "looking for opportunities",
    "actively looking for a permanent",
    "looking for a permanent role",
    "looking for a role",
    "transition into the",
    "help my friend find",
    "helping a close friend",
    "helping a friend find",
    "for a talented colleague",
    "job hunt",
    "job search",
)

# A referral request is a LEAD when it seeks a vendor, and NOISE when it seeks
# a job. Both use "can anyone recommend", so the distinction is what follows.
JOB_REFERRAL_RE = re.compile(
    r"\b(?:looking|searching|hunting|open)\s+for\s+"
    r"(?:a\s+|new\s+|any\s+)*"
    r"(?:job|jobs|role|roles|position|positions|opportunit\w+|work|employment)\b"
    r"|\b(?:any|some)\s+(?:leads|openings|vacancies|referrals)\b"
    r"|\brole\s+within\s+the\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# 3. Wrong ICP -- real people, real posts, but no budget or out of scope.
# ---------------------------------------------------------------------------
NO_BUDGET_TELLS = (
    "equity only",
    "equity-only",
    "no pay initially",
    "unpaid",
    "for equity",
    "looking for a technical co-founder",
    "technical cofounder",
    "technical co-founder",
    "pre-revenue",
    "bootstrapped with no funding",
    "no budget",
    "free of charge",
    "pro bono",
    "volunteer",
    "internship",
    "student project",
)

# ---------------------------------------------------------------------------
# 4. Job-board bots and ATS auto-posts: structurally like hiring posts, but
# nobody is home to receive a DM.
# ---------------------------------------------------------------------------
ATS_TELLS = (
    "apply here:",
    "apply now:",
    "click here to apply",
    "view job and apply",
    "see the details below",
    "job id:",
    "req id:",
    "requisition",
    "equal opportunity employer",
    "graduate scheme",
    "year in industry",
)

_VENDOR_RE = re.compile("|".join(VENDOR_HEADLINE_PATTERNS), re.IGNORECASE)


# ---------------------------------------------------------------------------
# POSITIVE REQUIREMENT: explicit buying or pain language.
#
# A 101-post corpus audit found only ~3 genuine business leads. The other 98
# were job seekers, thought leadership and self-promotion. Filtering that noise
# reactively means chasing an unbounded list of patterns; requiring a positive
# signal bounds the problem instead.
#
# This is the one rule in this module that ADMITS rather than rejects, and it
# runs last: a post must show a buying or pain signal to be worth paying to
# geo-check.
# ---------------------------------------------------------------------------

BUYING_SIGNALS = (
    # Direct vendor solicitation
    "can anyone recommend", "anyone recommend", "any recommendations",
    "looking for recommendations", "recommendations for a",
    "anyone know a good", "anyone know any", "does anyone know a",
    "who do you use for", "who did you use", "can someone recommend",
    "looking to hire a", "looking for an agency",
    "looking for a partner", "looking for a supplier",
    # "looking for a <service noun>" as a general construction. Handled by
    # regex below rather than enumerating every noun.
    "in the market for", "getting quotes", "taking recommendations",
    # Replacement intent
    "looking to switch", "switching from", "alternatives to",
    "moving away from", "replacing our", "we are replacing",
    "parting ways with", "fired our", "let go of our",
    "burned by", "let down by", "disappointed with our",
    # Stated operational pain, first person
    "we are struggling", "we're struggling", "struggling with our",
    "drowning in", "wasting hours", "eating up our", "takes us hours",
    "still doing this manually", "still doing it manually",
    "doing this by hand", "copy and paste", "copy-pasting",
    "does not scale", "doesn't scale", "falling over", "keeps breaking",
    "our system", "our stack", "our process is",
    # Capacity and delivery pressure
    "cannot keep up", "can't keep up", "at capacity", "over capacity",
    "turned down work", "turning away work", "had to say no to",
    "behind on", "slipped", "missed the deadline", "overdue",
    # Hiring frustration: the employer has budget and no candidate. Verified in
    # research as the highest-converting cluster for an agency pitch.
    "has been open for", "been open for months", "cannot find anyone",
    "can't find anyone", "cannot find the right", "no good candidates",
    "months and still no", "role is still open", "position is still open",
    # Failed attempt (highest-intent state in the research)
    "we tried", "tried using", "didn't work for us", "did not work for us",
    "gave up on", "never got it working", "stuck in",
)

# Buying language used by someone looking for a JOB, not a vendor. Checked
# first because the phrasing overlaps almost exactly.
JOB_CONTEXT = (
    "opportunity", "opportunities", "role", "position", "vacancy",
    "hiring me", "my next", "my career", "job", "cv", "resume",
    "paralegal", "assistant opportunit",
)


# "looking for / need / searching for" + a thing BarrioVibe sells. A regex
# rather than an enumerated list, because the noun varies endlessly
# ("a Shopify developer", "a new 3PL", "an automation partner").
# First-person ownership near the buying phrase: "we", "our", "I", "my", or a
# possessive form. Without this, a consultant describing the market reads as a
# buyer describing themselves.
_FIRST_PERSON_NEAR_RE = re.compile(
    r"\b(?:we|we're|weve|we've|our|ours|us|i|i'm|im|i've|ive|my|mine)\b",
    re.IGNORECASE,
)

# Referral asks, covering the grammatical variants people actually type:
# "anyone know / anyone knows / does anyone know / anybody know / who knows".
# An enumerated list misses conjugations, and a missed variant is a lost lead.
REFERRAL_ASK_RE = re.compile(
    r"\b(?:can\s+)?(?:any\s?(?:one|body)|some\s?(?:one|body)|who)\s+"
    r"(?:here\s+)?(?:knows?|recommend\w*|suggest\w*|has\s+used|used)\b"
    r"|\bdoes\s+any\s?(?:one|body)\s+(?:know|have|use)\b"
    r"|\b(?:any|some)\s+recommendations?\b"
    r"|\blooking\s+for\s+recommendations?\b",
    re.IGNORECASE,
)

# Verbs and nouns that suggest an unmet need, wanting, difficulty or change.
# Broad on purpose: this is a sieve, not a gate. The scorer decides.
# First person attached to a business noun. Borrowed in spirit from the
# grammar module: this is the single most reliable "this is about me" signal.
_FIRST_PERSON_BUSINESS_RE = re.compile(
    r"\b(?:our|my|we|i)\s+(?:\w+\s+){0,2}"
    r"(?:team|company|business|site|website|store|shop|app|product|platform|"
    r"system|systems|stack|process|ops|operations|staff|people|devs?|"
    r"developers?|engineers?|designer|agency|firm|client|clients|customers?|"
    r"orders?|inventory|stock|books|accounts|admin|reporting|reports|data|"
    r"crm|erp|checkout|launch|roadmap|project|build|contractor|supplier|"
    r"vendor|partner|3pl|warehouse|tools?|software|spreadsheets?)\b"
    r"|\b(?:we|i)\s+(?:are|were|have|had|need|hired|tried|spent|lost|built|"
    r"run|manage|use|used|switched|replaced|struggle|struggled)\b",
    re.IGNORECASE,
)

# Past or continuous action by the author, including subject-dropped forms
# ("spent the whole weekend", "been chasing this for weeks").
_PAST_ACTION_RE = re.compile(
    r"\b(?:spent|spend|wasted|lost|tried|hired|fired|built|broke|missed|"
    r"turned down|gave up|been|was|were|had|keep|kept|still)\b",
    re.IGNORECASE,
)

_NEED_SHAPED_RE = re.compile(
    r"\b(?:need|needs|needed|needing|want|wants|wanted|looking|look|search\w*|"
    r"find|finding|hire|hiring|recommend\w*|suggest\w*|advice|advise|help|"
    r"struggl\w*|stuck|broke|broken|break\w*|fail\w*|issue|issues|problem\w*|"
    r"challenge\w*|pain|painful|frustrat\w*|annoy\w*|hate|tired|exhaust\w*|"
    r"overwhelm\w*|drown\w*|behind|late|delay\w*|slow|slow\w*|manual\w*|"
    r"tedious|repetitive|waste|wasting|wasted|spend\w*|spent|cost\w*|expensive|"
    r"replace|replacing|switch\w*|migrat\w*|move|moving|upgrade|refresh|rebuild|"
    r"fix|fixing|improve|improving|automat\w*|scale|scaling|grow\w*|capacity|"
    r"bandwidth|resource\w*|short-staffed|understaffed|quote|quotes|budget|"
    r"vendor|supplier|partner|agency|freelanc\w*|contractor|outsourc\w*)\b",
    re.IGNORECASE,
)

SEEKING_RE = re.compile(
    r"\b(?:looking for|look for|need|needing|needs|searching for|search for|"
    r"in search of|want|wanting|after|seeking|to find|find us|hire)\s+"
    r"(?:to \w+\s+)?"
    r"(?:a |an |some |the |our |new |another |someone |somebody )*"
    r"(?:\w+\s+){0,3}"
    r"(?:developer|dev|engineer|programmer|designer|agency|partner|freelancer|"
    r"consultant|contractor|team|studio|shop|firm|company|provider|supplier|"
    r"vendor|3pl|fulfilment|fulfillment|bookkeeper|accountant|automation|"
    r"integration|website|web site|app|software|system|platform|crm|erp|"
    r"chatbot|help with|to help|to build|to fix|to finish|to take over)\b",
    re.IGNORECASE,
)


# Pure broadcast: announcements, congratulations, industry commentary,
# motivational content. These are the only posts with no chance of being a
# lead, so they are the only thing this sieve removes.
_BROADCAST_RE = re.compile(
    r"\b(?:excited|thrilled|delighted|proud|honou?red|pleased)\s+to\s+"
    r"(?:announce|share|reveal|introduce)\b"
    r"|\bcongratulations?\s+to\b"
    r"|\bwelcome\s+to\s+the\s+team\b"
    r"|\bjoin(?:ing|ed)?\s+us\s+(?:at|for)\b"
    r"|\bregister\s+(?:now|here|today)\b"
    r"|\b(?:webinar|conference|summit|panel|podcast episode)\b"
    r"|\bthe\s+future\s+of\s+\w+\s+is\b"
    r"|\bhere\s+is\s+what\s+nobody\b"
    r"|\b\d+\s+(?:lessons|things|ways|tips|reasons|mistakes)\s+"
    r"(?:i|we|you|every|that)\b",
    re.IGNORECASE,
)


def has_buying_signal(content: str | None) -> str | None:
    """Loose sieve. Passes almost everything; removes only pure broadcast.

    INVERTED ON PURPOSE. An earlier version required matching a vocabulary of
    need words, and it lost real leads whose pain used none of them:

        "honestly the site is embarrassing at this point"
        "spent the whole weekend reconciling spreadsheets again"
        "third contractor this year who has gone quiet on us"

    No keyword list anticipates how people actually write. So instead of
    listing what a lead looks like, this lists what a NON-lead looks like:
    announcements, congratulations, event promotion, listicles, and
    "the future of X is Y" commentary. Everything else goes to the scorer,
    which reads the full post and judges intent properly.

    The cost asymmetry justifies it: passing a dud costs $0.004 for a geo
    check, while dropping a real lead costs a customer.
    """
    c = _norm(content)
    if not c:
        return None

    match = _BROADCAST_RE.search(c)
    if match:
        return None  # broadcast content, not a lead

    # Short posts are fine when they ask something: "Can anyone recommend a
    # website developer?" is eleven words and one of the best leads there is.
    if "?" in c:
        return "asks a question"

    # A short statement with no question carries too little to judge, and too
    # little for a DM to reference specifically.
    if len(c.split()) < 12:
        return None

    return "worth reading"


def _norm(text: str | None) -> str:
    return (text or "").lower().strip()


# Headline terms that are DECISIVE: someone whose whole business is selling
# these services is a competitor no matter what a single post says.
HARD_VENDOR_TERMS = (
    # Recruiting and staffing: they post "looking for a developer" constantly,
    # on behalf of clients. Never the buyer.
    "recruitment", "recruiter", "talent acquisition", "staffing",
    "executive search", "headhunter", "talent partner", "hiring partner",
    "fractional cto", "virtual cto", "cto as a service", "staff augmentation",
    "software house", "dev shop", "development company", "outsourcing",
    "offshore", "nearshore", "white label", "we build", "i teach",
    "course creator", "smma", "lead generation", "appointment setting",
    "cold email", "b2b leads",
)


def vendor_headline_reason(
    headline: str | None, content: str | None = None
) -> str | None:
    """Reject sellers, job seekers and non-buyers. Headline first, post second.

    A headline is WEAK evidence. A corpus audit found three genuine buyers
    rejected on job title alone while their post was an explicit purchase
    request:

      "Founder | ... Technologies"   -> "Looking for a freelancer who can help
                                         with website design & development"
      "... Business Coach ..."       -> "Can anyone recommend a bookkeeper to
                                         advise me through the year"
      "Social Media Specialist at"   -> "Anyone knows a good Shopify Developer
                                         available for freelance work?"

    So when `content` carries an explicit buying signal, a soft headline
    objection is overridden. Hard vendor terms (whole business is selling what
    BarrioVibe sells) still reject regardless.
    """
    h = _norm(headline)
    if not h:
        return None  # No headline is not evidence of anything; let it through.

    # Hard terms reject no matter what the post says.
    for term in HARD_VENDOR_TERMS:
        if term in h:
            return f"vendor headline (decisive): {term!r}"

    # Everything below is overridable by an explicit buying request.
    buying = has_buying_signal(content) if content else None

    for term in JOBSEEKER_HEADLINE_TERMS:
        if term in h:
            if buying:
                continue  # a job seeker does not ask to hire a developer
            return f"job seeker: {term!r}"

    # An IC title only disqualifies when no decision-maker title is present:
    # "Founder & Software Engineer" is a buyer, "Software Engineer at X" is not.
    decision_maker = any(t in h for t in (
        "founder", "co-founder", "cofounder", "owner", "ceo", "cto", "coo",
        "managing director", "managing partner", "partner at", "principal",
        "president", "vp ", "vice president", "head of", "director of",
    ))
    # NOTE: the individual-contributor list is no longer a rejection. A corpus
    # audit found real buyers behind IC titles ("Social Media Specialist at X"
    # asking for a Shopify developer). Job title is weak evidence of purchasing
    # authority, and the scorer weighs it properly with the post in hand. Kept
    # as a signal for the scorer rather than a gate.
    _ = decision_maker

    for term in VENDOR_HEADLINE_TERMS:
        if term in h:
            if buying:
                continue
            return f"vendor headline: {term!r}"

    match = _VENDOR_RE.search(h)
    if match and not buying:
        return f"vendor headline pattern: {match.group(0)!r}"

    return None


def headline_is_placeholder(headline: str | None) -> bool:
    """True when a headline carries no professional identity ("--", "n/a").

    Deliberately NOT a rejection: a live corpus audit found a genuine buyer
    ("Can anyone recommend a Durham-based accountant...") behind a "--"
    headline. It is passed to the scorer as a weak negative signal instead.
    """
    h = _norm(headline)
    return not h or h.strip(" -–—.·|/") == "" or h in {"n/a", "na", "none"}


def content_reject_reason(content: str | None) -> str | None:
    """Reject bait, vendor case studies, no-budget and ATS posts on body text."""
    c = _norm(content)
    if not c:
        return "empty content"

    for tell in JOBSEEKER_CONTENT_TELLS:
        if tell in c:
            return f"job seeker post: {tell!r}"

    match = JOB_REFERRAL_RE.search(c)
    if match:
        return f"job-seeking referral request: {match.group(0)[:40]!r}"

    for phrase in BAIT_PHRASES:
        if phrase in c:
            return f"engagement bait: {phrase!r}"

    for tell in CASE_STUDY_TELLS:
        if tell in c:
            return f"vendor case study: {tell!r}"

    for tell in NO_BUDGET_TELLS:
        if tell in c:
            return f"no budget: {tell!r}"

    ats_hits = [t for t in ATS_TELLS if t in c]
    if len(ats_hits) >= 2:
        # One alone is weak ("see the details below" appears in real founder
        # hiring posts). Two or more means an ATS template.
        return f"ats template: {ats_hits[:2]}"

    # Hashtag stacks correlate with vendor and bait accounts, but a genuine
    # founder hiring post can carry a dozen tags too. Requiring a second
    # signal avoids dropping real posts on formatting alone.
    hashtags = c.count("#")
    if hashtags >= 12:
        return f"hashtag spam ({hashtags} tags)"
    if hashtags >= 8 and any(t in c for t in (
        "dm me", "link in bio", "follow for", "check out our", "our services",
        "we offer", "contact us", "book now", "limited slots",
    )):
        return f"hashtag stack + promotion ({hashtags} tags)"

    # Contact details in the body mean the author is selling, not buying.
    if re.search(r"\b(?:info|sales|contact|hello)@[a-z0-9.-]+\.[a-z]{2,}", c):
        return "contact email in body (selling)"

    return None


def first_person_ownership(content: str | None) -> bool:
    """True when the post describes the author's OWN situation.

    The research distinguishes a lead from marketing content by person:
      "most agencies struggle with X"        -> content marketing, not a lead
      "we turned down a project last week"   -> a real lead

    A pain phrase without first-person company context is bait. This is used as
    a signal by the qualifier, not as a hard gate, because some genuine posts
    open impersonally before turning personal.
    """
    c = _norm(content)
    if not c:
        return False
    markers = (
        " we ", " we're", " we've", " weve", " our ", " us ",
        " i ", " i'm", " im ", " i've", " ive ", " my ",
    )
    padded = f" {c} "
    return any(m in padded for m in markers)


