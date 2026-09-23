# BarrioVibe LinkedIn lead scraper

Finds people on LinkedIn who have just described a problem BarrioVibe can
solve, writes each of them a personalised message, and posts the lot to a
Discord channel for review before anything is sent.

Runs once a day. Costs about $1 a day in Apify credit. Everything else is free.

---

## What it does, in order

| # | Stage | Cost | What it removes |
|---|---|---|---|
| 1 | Search | $0.002/post | — |
| 2 | Validate | free | malformed records, posts over 24h old, company pages |
| 3 | Dedup | free | posts already sent |
| 4 | Headline | free | recruiters, staffing firms, job seekers, offshore outsourcers |
| 5 | Content | free | job-hunt posts, hashtag spam, no-budget posts |
| 6 | Grammar | free | competitor market research, agency funnels |
| 7 | Broadcast | free | announcements, congratulations, listicles, commentary |
| 8 | Locale | free | excluded-market vocabulary |
| 9 | **Geo check** | $0.004/lead | anyone outside the allowed countries |
| 10 | Qualify | free tier | scores 0-100, gate at 55 |
| 11 | Write DM | free tier | regenerates until the message passes validation |
| 12 | Deliver | free | — |

Two rules govern that order. **Everything free runs before anything paid.** And
the **geo check runs before scoring**, so no model time is spent on someone who
will be rejected for location.

### The design decision that matters most

Stages 4-8 only remove people who are unambiguously not buyers. They do not try
to decide whether a real business situation counts as a lead. That judgement
belongs to stage 10, which reads the whole post.

An earlier version put that judgement into regex and keyword lists. It rejected
genuine buyers because of their job title or because their phrasing happened to
resemble a vendor's. On a 101-post sample it passed 8 posts; the current design
passes 62 and keeps every known real lead.

The reasoning is cost asymmetry: paying $0.004 to geo-check a dud is trivial,
while dropping a real buyer costs a customer.

---

## Setup

Copy `.env.example` to `.env` and fill in five values:

```
APIFY_TOKEN=apify_api_...          # apify.com -> Settings -> API tokens
OPENROUTER_API_KEY=sk-or-v1-...    # openrouter.ai -> Keys
GROQ_API_KEY=gsk_...               # console.groq.com -> API Keys (optional)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

**OpenRouter needs one extra step.** Enable "Free model publication" at
openrouter.ai/settings/privacy, or every free-model call returns 404. Note that
this means prompts may be published to public datasets.

Check the setup without spending anything:

```bash
python3 -m src.settings
```

---

## Running it

```bash
python3 -m src.main                # normal run
python3 -m src.main --dry-run      # scrape and score, send nothing, save nothing
python3 -m src.main --limit 20     # cap posts processed, for testing
```

### Spending less while developing

Every Apify response is cached under `data/cache/`. Re-running filters, scoring
or DM writing against cached data costs nothing. Use this rather than
re-scraping: iterating on a filter should never cost money.

---

## Configuration

Everything tunable lives in `.env`:

| Setting | Default | Notes |
|---|---|---|
| `DAILY_BUDGET_USD` | `1.00` | Hard cap. The run aborts rather than exceed it. Refuses any value above 5 as a typo guard. |
| `SCORE_GATE` | `55` | Minimum score to reach Discord. Deliberately low: a human reviews everything. |
| `POSTED_LIMIT` | `24h` | Sent to LinkedIn. A stricter 24h check is also enforced in code and cannot be overridden. |
| `WRITER_MODEL` | `z-ai/glm-5.2:free` | Ranked 15th on Creative Writing v3 with a slop score of 13.11, lower than the paid Kimi K2.6. |
| `SCORER_PROVIDER` | `groq` | Scoring runs far more often than writing, so it uses Groq's separate quota and leaves OpenRouter for the DMs. |

### Budget

The cap is split 60/40 between search and the geo check. The geo portion is
ring-fenced before searching starts, so the funnel cannot run out of money at
its last step and discard posts it already paid for.

At $1/day that is roughly 300 posts and 100 geo lookups.

### Models

Both jobs use ordered fallback chains (`src/llm.py`). Free models go
temporarily unavailable, and models get retired outright, so a single-model
setup would stop the run. The chains are ordered by fitness for the job:
writing by prose quality, scoring by JSON reliability.

---

## Which leads it looks for

Five query groups, in `config/niches.py`:

- **Referral requests** (highest yield, 1.5x budget weight) — people asking
  their network to recommend a supplier. This runs across all industries rather
  than inside one, because asking for a referral is the one form of buying
  intent people still express publicly: it reads as community participation
  rather than admitting a problem. Live testing found it the best performing
  query type by a wide margin.
- **B2B SaaS** — hiring frustration, agency failure, stalled AI pilots
- **Digital agencies** — capacity crunch, white-label need, client asks they cannot build
- **E-commerce / DTC** — the manual work between Shopify, the 3PL and the spreadsheet
- **Professional services** — repetitive document and reporting work

**Logistics and real estate are disabled.** Research measured roughly 3% usable
posts in logistics, where operators post problems as war stories they already
solved rather than as requests for help. Real estate had the worst noise ratio
of any vertical examined, with coaching content deliberately written in the
target vocabulary. Both are retained in config and can be re-enabled.

### Geography

30 allowed markets, checked against `location.parsed.countryCode` from the
author's profile. South Asia is hard-blocked. A missing location is a
rejection, never a pass.

The actor has **no location parameter** (verified against its full input
schema), so geography cannot be filtered at search time. It is enforced at
stage 9 instead.

---

## The messages

Written by an LLM, then validated in code. A message containing banned phrasing
is rejected and regenerated rather than sent.

What the validator enforces (`config/banned.py`):

- No em dashes or other machine typography
- No AI-outreach openers: "came across", "noticed", "caught my attention"
- No calendar CTAs: "book a call", "discovery call", "free audit"
- No naming the agency or listing services
- Under 60 words, no exclamation marks, no emoji
- Nothing truncated mid-sentence

What the prompt asks for (`src/dm.py`):

- **Invent nothing.** Whatever they wrote is the entire extent of what is
  known. Guessing at a backstory reads as a stranger who did not read
  carefully, and a wrong guess ends the conversation.
- Match their length. An 11-word post gets a short reply.
- Credibility through one specific observation, never a claim.
- An ask that costs almost nothing to say yes to.

There are deliberately **no worked examples in the prompt**. One example makes
every output copy its shape, which is the templated feel the whole design
avoids.

---

## Layout

```
config/
  niches.py       which niches are on, and what each can be sold
  queries.py      search queries, 93% built from verbatim phrases found in research
  services.py     all 44 BarrioVibe services; only 26 are offerable abroad
  geo.py          country allowlist and locale vocabulary
  antisignals.py  headline and content filters
  grammar.py      operator-vs-vendor discrimination
  banned.py       phrasing the DM writer may not produce
  industries.py   LinkedIn industry IDs for server-side filtering

src/
  main.py       the pipeline
  settings.py   env loading and validation
  budget.py     spend ledger and the hard cap
  apify.py      search and profile enrichment, with caching
  llm.py        provider-agnostic client with fallback chains
  qualify.py    scoring
  dm.py         message writing and validation
  discord.py    delivery
  seen.py       dedup store
  queryplan.py  query assembly and budget planning

data/
  seen.json     post IDs already sent
  cache/        every Apify response, so development costs nothing
  runs/         per-run spend ledgers
```

---

## Honest expectations

On a 101-post sample gathered across several searches spanning a month, the
pipeline produced 17 qualified leads. A single day of genuinely fresh posts
will produce fewer: realistically **3 to 6 leads a day** at $1.

That is a property of the channel, not a fault in the system. Research across
six niches found the same thing repeatedly: founders rarely post buying
questions publicly, because doing so invites fifty cold pitches. The richest
verbatim pain found during research was on Shopify Community and G2 reviews,
not LinkedIn.

The system works. LinkedIn is simply thinner than it looks.
