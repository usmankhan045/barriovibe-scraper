"""Geographic gate.

The only trustworthy geo signal in the pipeline is `location.parsed.countryCode`
from the Apify profile data: an ISO-3166 alpha-2 code. Everything else
(`location.linkedinText`, post language, currency symbols) is advisory at best
and is never allowed to admit a lead on its own.

Rule: allowlist-only. A profile is admitted if and only if its country code is
explicitly in ALLOWED. Missing, null or unrecognised location => rejected.
A missing field is not a pass.
"""

# Admitted markets, ISO-3166 alpha-2.
# NOTE: the United Kingdom is "GB", never "UK". "UK" is not a valid ISO-2 code
# and would silently never match.
ALLOWED = frozenset({
    # Core anglophone
    "US",  # United States
    "GB",  # United Kingdom
    "CA",  # Canada
    "AU",  # Australia
    "NZ",  # New Zealand
    "IE",  # Ireland
    # Nordics
    "SE",  # Sweden
    "NO",  # Norway
    "DK",  # Denmark
    "FI",  # Finland
    "IS",  # Iceland
    # Western Europe
    "DE",  # Germany
    "NL",  # Netherlands
    "BE",  # Belgium
    "FR",  # France
    "AT",  # Austria
    "CH",  # Switzerland
    "LU",  # Luxembourg
    # Southern Europe
    "ES",  # Spain
    "IT",  # Italy
    "PT",  # Portugal
    # GCC
    "AE",  # United Arab Emirates
    "SA",  # Saudi Arabia
    "QA",  # Qatar
    "KW",  # Kuwait
    "BH",  # Bahrain
    "OM",  # Oman
    # Developed Asia-Pacific
    "SG",  # Singapore
    "JP",  # Japan
    "HK",  # Hong Kong
})

# Hard exclusions. These are already outside ALLOWED, so this set is redundant
# by construction -- it exists as a second barrier in case a future edit widens
# ALLOWED carelessly. BLOCKED always wins over ALLOWED.
BLOCKED = frozenset({
    "IN",  # India
    "PK",  # Pakistan
    "BD",  # Bangladesh
    "LK",  # Sri Lanka
    "NP",  # Nepal
})

# Cheap pre-filter signals, used ONLY to reject before paying for enrichment.
# These never admit a lead and never override a valid country code -- they run
# before the profile lookup purely to avoid spending money on obvious non-fits.
# Kept deliberately narrow: a false reject here costs a real lead, so only
# unambiguous markers are listed.
PREFILTER_REJECT_SUBSTRINGS = (
    "₹",
    "inr",
    "lakh",
    "crore",
)

PREFILTER_REJECT_CITIES = (
    "bengaluru", "bangalore", "hyderabad", "noida", "gurugram", "gurgaon",
    "mumbai", "pune", "chennai", "kolkata", "ahmedabad", "jaipur", "indore",
    "karachi", "lahore", "islamabad", "rawalpindi", "faisalabad",
    "dhaka", "chittagong", "colombo", "kathmandu",
)


def country_allowed(country_code: str | None) -> bool:
    """Return True only for an explicitly allowlisted ISO-2 country code.

    Defensive by design: None, empty, malformed or unknown codes all return
    False. Blocked codes return False even if someone adds them to ALLOWED.
    """
    if not country_code or not isinstance(country_code, str):
        return False
    code = country_code.strip().upper()
    if len(code) != 2:
        return False
    if code in BLOCKED:
        return False
    return code in ALLOWED


def extract_country_code(profile: dict | None) -> str | None:
    """Pull the country code out of an Apify profile object.

    Prefers `location.parsed.countryCode`, falls back to `location.countryCode`.
    Returns None if neither is a usable 2-letter string -- the caller must treat
    None as a rejection, never as an unknown-but-acceptable.
    """
    if not isinstance(profile, dict):
        return None
    location = profile.get("location")
    if not isinstance(location, dict):
        return None

    parsed = location.get("parsed")
    if isinstance(parsed, dict):
        code = parsed.get("countryCode")
        if isinstance(code, str) and len(code.strip()) == 2:
            return code.strip().upper()

    code = location.get("countryCode")
    if isinstance(code, str) and len(code.strip()) == 2:
        return code.strip().upper()

    return None


def prefilter_looks_excluded(*texts: str | None) -> bool:
    """Cheap, pre-spend reject check on raw post/headline text.

    Returns True when text carries an unambiguous marker of an excluded market.
    This runs BEFORE the paid profile lookup to avoid wasting budget. It is
    intentionally conservative: when in doubt it returns False and lets the
    authoritative country-code gate decide.
    """
    blob = " ".join(t.lower() for t in texts if isinstance(t, str) and t)
    if not blob:
        return False
    padded = f" {blob} "
    if _count_matches(PREFILTER_REJECT_SUBSTRINGS, padded):
        return True
    return _count_matches(PREFILTER_REJECT_CITIES, padded) > 0


# ---------------------------------------------------------------------------
# Locale lexicon.
#
# Vocabulary is itself geographic. A post saying "suitability report", "FCA"
# and "paraplanner" is British; one saying "RIA", "SEC" and "401k" is American;
# one saying "lakh", "GST" or "FBR" is South Asian. This is free to check,
# harder to fake than a stated location, and catches posts whose author has no
# resolvable company (where the paid profile lookup may return nothing).
#
# Used to BIAS and to REJECT -- never to admit. Only the ISO country code from
# the profile lookup can admit a lead.
# ---------------------------------------------------------------------------

SOUTH_ASIA_LEXICON = (
    # Currency and numbering
    "₹", "inr", "lakh", "lakhs", "crore", "crores", "rupee", "rupees",
    # Tax and regulatory bodies
    "gst ", "gstin", "fbr", "nadra", "secp", "iris portal", "ntn",
    "pseb", "weboc", "tds ", "itr ", "pan card", "aadhaar", "aadhar",
    # Market and employment vocabulary
    "notice period", "ctc ", "lpa ", "fresher", "freshers",
    "hsc", "ssc", "b.tech", "btech", "mtech", "iit ", "nit ",
    # Time zone. "ist" alone is not listed: it matched inside "assist",
    # "specialist" and "logistics", rejecting genuine leads.
    "indian standard time",
)

UK_LEXICON = (
    "companies house", "hmrc", "fca", "vat", "ltd", "limited company",
    "paraplanner", "suitability report", "acturis", "intelliflo",
    "consumer duty", "making tax digital", "paye", "national insurance",
    "£", "gbp", "cv ", "sole trader", "ir35",
)

US_LEXICON = (
    "irs", "401k", "401(k)", "llc", "c-corp", "s-corp",
    "delaware", "ein ", "w-2", "1099", "ams360", "applied epic",
    "resume", "zip code", "$", "usd",
)

EU_LEXICON = (
    "gdpr", "€", "eur ", "gmbh", "bv ", "sarl", "oy ", "ab ", "aps ",
    "vat number", "kvk", "handelsregister", "iban",
)

GULF_LEXICON = (
    "aed", "dirham", "dubai", "abu dhabi", "dmcc", "jafza", "difc",
    "adgm", "riyadh", "jeddah", "doha", "kuwait city", "manama",
    "free zone", "mainland licence", "mainland license",
)


def _count_matches(patterns: tuple[str, ...], blob: str) -> int:
    """Count pattern hits using word boundaries where the pattern is a word.

    Naked substring matching caused a real false reject: "ist " matched inside
    "assist me", marking a UK Shopify lead as South Asian. Anything alphabetic
    is matched on word boundaries; symbols and currency signs are matched
    literally because \b does not apply to them.
    """
    import re as _re
    total = 0
    for pattern in patterns:
        token = pattern.strip()
        if not token:
            continue
        if token.replace(" ", "").replace(".", "").replace("(", "").isalnum():
            if _re.search(rf"\b{_re.escape(token)}\b", blob, _re.IGNORECASE):
                total += 1
        elif token in blob:
            total += 1
    return total


def locale_signal(*texts: str | None) -> str | None:
    """Best-guess market from vocabulary. Advisory only.

    Returns "south_asia" | "uk" | "us" | "eu" | "gulf" | None. A "south_asia"
    result is actionable on its own -- it means do not spend money on the
    profile lookup. Every other result is a weak positive hint that the
    authoritative country-code check still has to confirm.
    """
    blob = " ".join(t.lower() for t in texts if isinstance(t, str) and t)
    if not blob:
        return None
    padded = f" {blob} "

    scores = {
        "south_asia": _count_matches(SOUTH_ASIA_LEXICON, padded),
        "uk": _count_matches(UK_LEXICON, padded),
        "us": _count_matches(US_LEXICON, padded),
        "eu": _count_matches(EU_LEXICON, padded),
        "gulf": _count_matches(GULF_LEXICON, padded),
    }
    # South Asia needs TWO independent markers, not one. A single ambiguous hit
    # was rejecting real leads, and the authoritative country-code check runs
    # immediately afterwards anyway, so this filter only needs to avoid paying
    # for obvious cases -- it does not need to be the last line of defence.
    if scores["south_asia"] >= 2:
        return "south_asia"
    # One unambiguous marker (currency, tax body) is still decisive.
    if scores["south_asia"] == 1 and _count_matches(
        ("₹", "fbr", "gstin", "nadra", "secp", "lakh", "crore", "aadhaar"), padded
    ):
        return "south_asia"

    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else None


# Geo terms appended to search queries to bias retrieval toward allowlisted
# markets. LinkedIn matches these against post text and author context, so they
# reduce (but do not eliminate) non-tier-1 posts entering the funnel.
#
# Kept to ONE boolean group so it consumes as little of the ~5-operator cap as
# possible. Rotated per run so a single day's sweep is not locked to one market.
GEO_QUERY_GROUPS = (
    '("United States" OR "USA")',
    '("United Kingdom" OR "London")',
    '("Canada" OR "Australia")',
    '("Germany" OR "Netherlands")',
    '("Dubai" OR "UAE")',
    '("Singapore" OR "Ireland")',
    '("New York" OR "California")',
    '("Sweden" OR "Denmark")',
)
