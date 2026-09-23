"""DM writer.

The hardest constraint in the system: a message must read as though a person
who understood this specific post wrote it, in under 80 words, without any of
the register that marks cold outreach as machine-written.

Design decisions, each from research:

  - NEVER announce having read the post. "I came across your post" is the
    single most common AI-outreach opener and is banned. Instead the message
    opens by stating the person's own situation back to them as fact, which
    only someone who actually read it could do.

  - Quote a SPECIFIC detail. Research found generic pain restatement is what
    makes a message feel templated. The prompt requires a concrete noun from
    their post: the actual tool, the actual number, the actual failure.

  - Hint the solution, never pitch it. One clause on what would fix it, then a
    question. No service list, no credentials, no call booking.

  - Back-office framing only, unless their post asks otherwise. Research found
    customer-facing AI is negatively positioned: communities have been burned
    by it. Offering to remove internal manual work is welcome; offering to put
    a bot in front of their customers is not.

  - Output is validated, not trusted. Any banned phrasing means regenerate.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from config.banned import normalise_chars, violations
from config.services import BY_SLUG
from src.llm import LLMError

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # regeneration attempts when output fails validation

MAX_WORDS = 60
MIN_WORDS = 12  # a good reply to a one-line post is short


SYSTEM_PROMPT = """You are Usman. You run BarrioVibe, a small software and AI \
agency. Someone posted on LinkedIn and you are replying.

You want them to reply to you. That is the only goal. Not to impress them, not \
to explain everything you do, not to close a deal in one message.

THE MOST IMPORTANT RULE
Do not invent anything.

Whatever they wrote is the entire extent of what you know. You do not know why \
the situation happened, how long it has gone on, what it is costing them, who \
else is involved, or what they have already tried, unless they said so. \
Guessing at a backstory to sound perceptive makes you sound like a stranger \
who did not read carefully, and if the guess is wrong the conversation is over.

WHAT A GOOD MESSAGE DOES
Three things, in whatever order the post makes natural:

1. Shows you understood the specific thing they said. Reference one or two \
concrete details they gave, then move on. Do NOT summarise their post back to \
them: they know what they wrote, and a recap reads as padding. One clause of \
recognition is enough before you say something they do not already know.

2. Gives them one reason to believe you can handle it. Not credentials. Not \
years of experience. The believable version is a small concrete detail that \
only someone who does this work would mention: the thing that usually goes \
wrong, the part that is quicker than people expect, the question you would \
ask first. One line. It should read as a thought, not a claim.

3. Makes replying easy. This is the part most messages get wrong.

THE ASK
End with something that costs them almost nothing to say yes to. The smaller \
the ask, the more replies you get. You are not trying to get a meeting, you \
are trying to get a sentence back.

Good asks share a shape: they are specific, low effort, and the person can \
answer without committing to anything. Offering to look at something, asking \
which of two things is the problem, asking what they have already tried, \
offering to send one useful thing. Vary it. The right ask depends entirely on \
what they posted.

Bad asks: anything with a calendar in it, anything that asks them to explain \
their whole situation, anything that sounds like the start of a sales process, \
and anything that could be answered "no" and end there.

If they asked a question, answering it IS the ask. Say you do the work, give \
them one useful thing, and let them come back.

TONE
Write like a competent person who is not desperate for the work. Slight \
understatement. Normal words. Contractions. The confidence comes from being \
specific and relaxed, never from claiming anything.

NEVER
- Invent details they did not give
- Announce reading their post ("came across", "noticed", "saw your")
- Name services, list what BarrioVibe does, mention experience, client counts \
or results
- Compliment them or their company
- "I'd love to", "happy to", "let's connect", "reach out", "book a call", \
"quick call", "hop on a call", "free audit", "no pressure"
- Em dashes, exclamation marks, emoji
- Go over 60 words. Most should be half that.

BEFORE YOU WRITE
Ask three things about THIS post specifically:
  1. What did they actually say? Only that.
  2. What do they want to happen next?
  3. What is the smallest thing you could offer that moves them toward it?

Then write it. A message about a tax deadline and one about a broken checkout \
should share nothing but brevity and tone. If your message would still make \
sense with another post's details swapped in, it is too generic. Start again.

Return only the message."""


@dataclass
class WrittenMessage:
    text: str
    attempts: int
    rejected: list[str]  # validation failures on discarded attempts


class DMWriterError(RuntimeError):
    pass


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _strip_wrapping(text: str) -> str:
    """Models often wrap output in quotes or a code fence despite instructions."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    text = text.strip()
    if len(text) > 1 and text[0] in "\"'" and text[-1] == text[0]:
        text = text[1:-1].strip()
    # Some models prepend a label.
    text = re.sub(r"^(?:message|dm|draft)\s*:\s*", "", text, flags=re.IGNORECASE)

    # Several free models leak chain-of-thought before the answer ("The user
    # asks... So we must output..."). Drop everything up to the last such
    # marker rather than sending reasoning to a prospect.
    for marker in (
        "\n\nFinal message:", "\n\nMessage:", "\n\nHere is the message:",
        "\n\nHere's the message:", "\n\nOutput:", "\n\nAnswer:",
    ):
        if marker.lower() in text.lower():
            idx = text.lower().rindex(marker.lower())
            text = text[idx + len(marker):]
    if re.match(r"^(?:the user (?:asks|wants)|we must|so we|i need to|okay,|let me)", text, re.IGNORECASE):
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) > 1:
            text = paragraphs[-1]

    # Typography the model chose (curly quotes, em dashes, non-breaking
    # hyphens) is fixed here rather than counted as a validation failure.
    # Regenerating over a character we can replace burns a model call, and on
    # a free tier that call costs a rate-limit wait as well.
    return normalise_chars(text)


def _validate(text: str, first_name: str) -> list[str]:
    """All reasons this message is unusable. Empty means send it."""
    problems = violations(text)

    words = _word_count(text)
    if words > MAX_WORDS:
        problems.append(f"too long ({words} words, max {MAX_WORDS})")
    if words < MIN_WORDS:
        problems.append(f"too short ({words} words, min {MIN_WORDS})")

    # A message that never uses their name or any second person is not a DM.
    if first_name and first_name.lower() not in text.lower():
        if not re.search(r"\byou(?:r|'re|ve)?\b", text, re.IGNORECASE):
            problems.append("does not address the person")

    # Truncated output: the model ran out of tokens mid-sentence. Sending
    # "...I've been through" would read as broken.
    stripped = text.rstrip()
    if stripped and stripped[-1] not in ".?!\"')":
        problems.append("ends mid-sentence (truncated)")

    # Placeholder leakage from the model.
    if re.search(r"\[[^\]]{2,30}\]|\{\{.*?\}\}|<[a-z_]+>", text):
        problems.append("contains an unfilled placeholder")

    # A question is usually the right ending, but requiring one forces every
    # message into the same shape, which is the templated feel we are trying to
    # avoid. Only flag a message that is both long and closed: short, pointed
    # statements can invite a reply perfectly well.
    if "?" not in text and _word_count(text) > 55:
        problems.append("long with no question, gives them nothing to answer")

    return problems


class DMWriter:
    def __init__(self, client, *, dry_run: bool = False) -> None:
        """`client` is an LLMClient or FallbackClient."""
        self.client = client
        self.dry_run = dry_run

    def _call(self, messages: list[dict], temperature: float) -> str:
        try:
            return self.client.complete(
                messages, temperature=temperature, max_tokens=1200
            ).text
        except LLMError as exc:
            raise DMWriterError(str(exc)) from exc

    def write(self, lead: dict) -> WrittenMessage:
        """Write one message, regenerating until it passes validation."""
        first_name = (lead.get("author_name") or "").split()[0] if lead.get("author_name") else ""
        service = BY_SLUG.get(lead.get("service_slug", ""))
        service_line = (
            f"{service.name}: {service.description}" if service else "general software work"
        )

        user_prompt = f"""Write the message.

WHO THEY ARE
Name: {lead.get('author_name', 'there')}
Headline: {lead.get('author_headline', 'unknown')}

WHAT THEY POSTED (this is the only thing you know about them; use its specifics)
\"\"\"
{lead.get('post_content', '')[:1500]}
\"\"\"

THE PROBLEM THEY HAVE
{lead.get('pain', 'unclear')}

WHAT BARRIOVIBE WOULD DO ABOUT IT (hint at this, do not pitch it, do not name it as a service)
{service_line}

Write the message to {first_name or 'them'} now."""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        rejected: list[str] = []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if self.dry_run:
                return WrittenMessage("[dry-run: no message generated]", attempt, [])

            # Temperature climbs slightly on retry: a rejected message usually
            # means the model settled into the marketing register, and nudging
            # it out works better than asking the same way again.
            # Higher temperature on purpose. The whole point is that two
            # messages about two different posts should not share a shape, and
            # low temperature collapses toward one safe template.
            raw = self._call(messages, temperature=0.95 + 0.1 * (attempt - 1))
            text = _strip_wrapping(raw)
            problems = _validate(text, first_name)

            if not problems:
                return WrittenMessage(text, attempt, rejected)

            rejected.append(f"attempt {attempt}: {'; '.join(problems[:4])}")
            log.info("DM rejected (attempt %s): %s", attempt, problems[:3])

            # Tell the model exactly what failed so the retry is informed.
            messages = messages[:2] + [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": (
                        "That message is unusable for these reasons:\n"
                        + "\n".join(f"- {p}" for p in problems)
                        + "\n\nWrite it again, fixing every one of them. Return "
                        "only the message."
                    ),
                },
            ]

        raise DMWriterError(
            f"Could not write a clean message after {MAX_ATTEMPTS} attempts. "
            f"Failures: {rejected}"
        )
