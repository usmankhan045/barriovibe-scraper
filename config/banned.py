"""Banned phrasing for generated DMs.

These are enforced as a validation pass over the model's output, not merely as
prompt instructions. Models drift back toward this register under pressure, so
a message containing any of it is rejected and regenerated rather than trusted.

Two categories, both fatal:

  1. AI TELLS -- phrasing that marks a message as machine-written. A prospect
     who senses a generated message stops reading, which defeats the entire
     point of personalising it.

  2. VENDOR TELLS -- the cold-outreach register the research found people
     actively resent. Verified reaction to exactly this kind of message:
     "I'm more tired of people trying to sell me their vibe coded software."
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# 1. Characters that read as machine-written.
#
# These are a typography problem, not a writing problem: the sentence around a
# curly apostrophe is exactly as good as the same sentence with a straight one.
# Rejecting a whole generation over one costs a full model call (and, on a free
# tier, a rate-limit wait) to buy back a character we can simply replace. So
# they are NORMALISED before validation rather than rejected, and no longer
# appear in `violations()`.
#
# The em dash is deliberately mapped to ", " rather than "-": an em dash joins
# two clauses, and a hyphen between clauses reads as a typo where a comma reads
# as normal writing.
# ---------------------------------------------------------------------------
CHAR_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("\u2014", ", "),   # em dash
    ("\u2013", "-"),    # en dash
    ("\u2011", "-"),    # non-breaking hyphen
    ("\u2012", "-"),    # figure dash
    ("\u2015", "-"),    # horizontal bar
    ("\u2018", "'"),    # curly open single
    ("\u2019", "'"),    # curly apostrophe
    ("\u201a", "'"),    # single low quote
    ("\u201c", '"'),    # curly open double
    ("\u201d", '"'),    # curly close double
    ("\u201e", '"'),    # double low quote
    ("\u2026", "..."),  # ellipsis
    ("\u00a0", " "),    # non-breaking space
    ("\u202f", " "),    # narrow no-break space
    ("\u2009", " "),    # thin space
    ("\u200b", ""),     # zero-width space
    ("\ufeff", ""),     # BOM / zero-width no-break space
    ("\u2032", "'"),    # prime
    ("\u2033", '"'),    # double prime
    ("\u00ab", '"'),    # guillemets
    ("\u00bb", '"'),
)

_CHAR_TABLE = {ord(bad): good for bad, good in CHAR_REPLACEMENTS}


def normalise_chars(text: str | None) -> str:
    """Replace machine-looking typography with its plain-ASCII equivalent.

    Applied to model output before validation. Idempotent, so it is safe to
    call more than once on the same string.
    """
    if not text:
        return ""

    # A non-breaking hyphen sitting between two letters is almost always a
    # mangled apostrophe ("it\u2011s", "don\u2011t"), not a real hyphen. Mapping it
    # to "-" would produce "it-s". Handle that case before the table.
    text = re.sub(r"(?<=[A-Za-z])\u2011(?=(?:s|t|re|ve|ll|d|m)\b)", "'", text)

    text = text.translate(_CHAR_TABLE)
    # An em dash mapped to ", " can collide with a comma the model already
    # wrote, or land before existing punctuation.
    text = re.sub(r",\s*,+", ",", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*([.!?;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    # An em dash at the very start of a line becomes a stray leading comma.
    text = re.sub(r"(?m)^\s*,\s*", "", text)
    return text.strip()

# ---------------------------------------------------------------------------
# 2. Opening formulas. Nearly every AI-written cold message starts with one,
#    which is precisely why they no longer work.
# ---------------------------------------------------------------------------
BANNED_OPENERS: tuple[str, ...] = (
    "caught my attention",
    "caught my eye",
    "came across your",
    "came across this",
    "i came across",
    "stumbled upon",
    "stumbled across",
    "i noticed you",
    "i noticed that",
    "noticed your post",
    "saw your post",
    "just saw your",
    "i was reading your",
    "your post about",
    "reaching out because",
    "reaching out to see",
    "wanted to reach out",
    "thought i'd reach out",
    "hope this finds you well",
    "hope you're well",
    "hope you are doing well",
    "hope all is well",
    "trust you are well",
    "i hope this message",
    "quick question for you",
)

# ---------------------------------------------------------------------------
# 3. Filler and hedging that adds length without meaning.
# ---------------------------------------------------------------------------
BANNED_FILLER: tuple[str, ...] = (
    "i'd love to",
    "would love to",
    "i would love to",
    "happy to share",
    "happy to chat",
    "happy to help",
    "feel free to",
    "don't hesitate",
    "let's connect",
    "let me know if",
    "just wanted to",
    "i wanted to",
    "hoping to connect",
    "looking to connect",
    "if you're open to",
    "if that resonates",
    "does that resonate",
    "worth a conversation",
    "worth a chat",
    "pick your brain",
    "hop on a call",
    "jump on a call",
    "quick call",
    "15 minutes",
    "15 min",
    "book a call",
    "book a demo",
    "schedule a call",
    "calendar link",
    "no pressure",
    "no strings",
    "free audit",
    "free consultation",
    "free strategy",
    "discovery call",
    "jump on a zoom",
    "grab 15",
    "find a time",
    "my calendar",
    "calendly",
    "circle back",
    "touch base",
    "reach out",
)

# ---------------------------------------------------------------------------
# 4. The vendor register itself. Research found these actively resented.
# ---------------------------------------------------------------------------
BANNED_VENDOR: tuple[str, ...] = (
    # The agency's own name. Naming it turns a message into an advert; the
    # prospect can see who sent it from the profile.
    "barriovibe",
    "barrio vibe",
    "we help companies",
    "we help businesses",
    "we help brands",
    "we help founders",
    "we help agencies",
    "we specialize in",
    "we specialise in",
    "our team of",
    "we are a leading",
    "we're a leading",
    "full-service agency",
    "one-stop shop",
    "end-to-end solution",
    "cutting edge",
    "cutting-edge",
    "state of the art",
    "best in class",
    "world class",
    "game changer",
    "game-changer",
    "revolutionize",
    "revolutionise",
    "seamless",
    "seamlessly",
    "leverage our",
    "unlock",
    "supercharge",
    "10x your",
    "scale your business",
    "take your business to",
    "drive growth",
    "delighted to",
    "thrilled to",
    "excited to share",
)

# ---------------------------------------------------------------------------
# 5. Corporate-AI vocabulary.
# ---------------------------------------------------------------------------
BANNED_AI_VOCAB: tuple[str, ...] = (
    "delve",
    "delving",
    "tapestry",
    "landscape of",
    "in today's",
    "in the realm of",
    "navigate the",
    "navigating the",
    "robust",
    "streamline",
    "streamlining",
    "streamlined",
    "elevate",
    "empower",
    "empowering",
    "holistic",
    "synergy",
    "synergies",
    "paradigm",
    "myriad",
    "plethora",
    "furthermore",
    "moreover",
    "additionally",
    "it's worth noting",
    "that being said",
    "at the end of the day",
    "needless to say",
)

ALL_BANNED: tuple[tuple[str, str], ...] = tuple(
    [(phrase, "opener") for phrase in BANNED_OPENERS]
    + [(phrase, "filler") for phrase in BANNED_FILLER]
    + [(phrase, "vendor") for phrase in BANNED_VENDOR]
    + [(phrase, "ai-vocab") for phrase in BANNED_AI_VOCAB]
)

# Rule-of-three constructions ("faster, cheaper, and better") are a strong
# LLM signature in short copy.
TRIPLE_RE = re.compile(
    r"\b\w+(?:ly)?,\s+\w+(?:ly)?,\s+and\s+\w+", re.IGNORECASE
)

# "It's not X, it's Y" and "not just X but Y" are similarly characteristic.
NEGATIVE_PARALLEL_RE = re.compile(
    r"\b(?:it'?s not (?:just )?(?:about )?\w+.{0,40}?,? it'?s|"
    r"not just \w+.{0,30}? but)\b",
    re.IGNORECASE,
)


def violations(text: str | None) -> list[str]:
    """Every banned pattern present. Empty list means the message is clean."""
    if not text:
        return ["empty message"]

    found: list[str] = []
    lowered = text.lower()

    for phrase, category in ALL_BANNED:
        if phrase in lowered:
            found.append(f"{category}: {phrase!r}")

    if TRIPLE_RE.search(text):
        found.append("rule-of-three construction")

    if NEGATIVE_PARALLEL_RE.search(text):
        found.append("negative parallelism ('not X, it's Y')")

    # Exclamation marks read as salesy in cold outreach.
    if text.count("!") > 0:
        found.append("exclamation mark")

    # Emoji: fine in a LinkedIn post, wrong in a first cold DM.
    if re.search(r"[\U0001F300-\U0001FAFF☀-➿]", text):
        found.append("emoji")

    return found


def is_clean(text: str | None) -> bool:
    return not violations(text)
