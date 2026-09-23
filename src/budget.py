"""Spend ledger and hard budget cap.

Every paid Apify operation must be reserved through this ledger BEFORE it is
issued. The cap is a refusal, not a warning: when the next call would cross the
ceiling the pipeline stops and reports what it managed to do, rather than
overrunning and draining a small balance.

Prices are per-unit USD, taken from the actors' published pricing. They are
declared here as named constants so a pricing change is a one-line edit and so
no magic number is ever buried in a call site.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# --- Apify pricing, USD per unit -------------------------------------------
# The actor migrated to PAY_PER_EVENT on 2026-03-09. These are the free/bronze
# tier rates pulled from the live Apify API, not the stale per-1k figures in the
# actor README. Budgeting at the free-tier rate is pessimistic on purpose: if
# the account is on a higher tier the real spend lands under the cap.
PRICE_PER_POST = 0.002

# A query that returns nothing is still charged, because the actor consumes
# resources scraping the search pages. This is what makes a "many narrow
# queries" strategy expensive: 60 misses = $0.06 of pure waste.
PRICE_PER_EMPTY_QUERY = 0.001

# profileScraperMode="main" adds this to EVERY post retrieved, including the
# ~80% that local filters discard. That is why enrichment happens after
# filtering via the standalone actor instead of inline here.
PRICE_PER_INLINE_PROFILE = 0.002

# harvestapi/linkedin-profile-scraper standalone: $0.004 per profile, paid only
# for posts that survived every free local filter.
PRICE_PER_STANDALONE_PROFILE = 0.004

# Reactions and comments are charged at the full post rate. maxComments=10 on a
# single post costs $0.022 -- 11x a bare post. Never enabled in the main sweep.
PRICE_PER_REACTION = 0.002
PRICE_PER_COMMENT = 0.002


class BudgetExceeded(RuntimeError):
    """Raised when an operation would cross the configured ceiling."""


@dataclass
class Ledger:
    """Tracks projected spend for a single run against a hard ceiling.

    Usage is strictly reserve-then-record:

        ledger.reserve(PRICE_PER_POST, count, "post-search: saas")
        ... issue the call ...
        ledger.record(actual_units, PRICE_PER_POST, "post-search: saas")

    `reserve` raises before the money is spent. `record` books what was actually
    consumed, which is usually less than reserved because actors commonly return
    fewer items than the requested maximum.
    """

    cap_usd: float
    spent_usd: float = 0.0
    entries: list[dict] = field(default_factory=list)
    # Money set aside for a later stage. Earlier stages cannot see or spend it.
    # Without this, search consumes the whole cap and the geo check -- which
    # every lead must pass -- is left with nothing, so posts are retrieved and
    # then discarded unverified. That wastes everything already spent on them.
    reserved_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.cap_usd <= 0:
            raise ValueError("cap_usd must be positive")

    @property
    def remaining_usd(self) -> float:
        """Spendable now, excluding anything ring-fenced for a later stage."""
        return max(0.0, self.cap_usd - self.spent_usd - self.reserved_usd)

    @property
    def total_remaining_usd(self) -> float:
        """Everything left including reservations."""
        return max(0.0, self.cap_usd - self.spent_usd)

    def reserve_for_later(self, amount: float) -> None:
        self.reserved_usd = max(0.0, amount)

    def release_reservation(self) -> None:
        """Called when the reserved stage begins, freeing the ring-fence."""
        self.reserved_usd = 0.0

    def can_afford(self, unit_price: float, units: int) -> bool:
        budget = self.cap_usd - self.reserved_usd
        return (self.spent_usd + unit_price * units) <= budget + 1e-9

    def max_affordable_units(self, unit_price: float) -> int:
        """How many units of this price still fit under the cap.

        Lets a caller shrink a request to fit rather than abandoning it, which
        matters on a tight budget: scraping 60 posts is better than scraping 0
        because 100 did not fit.
        """
        if unit_price <= 0:
            return 0
        return max(0, int(self.remaining_usd / unit_price + 1e-9))

    def reserve(self, unit_price: float, units: int, label: str) -> None:
        """Assert affordability before a paid call. Raises BudgetExceeded."""
        if units < 0:
            raise ValueError("units must be non-negative")
        projected = unit_price * units
        if not self.can_afford(unit_price, units):
            raise BudgetExceeded(
                f"{label}: needs ${projected:.4f} but only "
                f"${self.remaining_usd:.4f} of the ${self.cap_usd:.2f} cap "
                f"remains (spent ${self.spent_usd:.4f}). Refusing to overspend."
            )

    def record(self, units: int, unit_price: float, label: str) -> float:
        """Book actual consumption after a call returns. Returns the amount."""
        if units < 0:
            raise ValueError("units must be non-negative")
        amount = unit_price * units
        self.spent_usd += amount
        self.entries.append({
            "label": label,
            "units": units,
            "unit_price": unit_price,
            "amount_usd": round(amount, 6),
            "cumulative_usd": round(self.spent_usd, 6),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        return amount

    def summary(self) -> str:
        pct = (self.spent_usd / self.cap_usd * 100) if self.cap_usd else 0.0
        lines = [
            f"Spend: ${self.spent_usd:.4f} of ${self.cap_usd:.2f} cap ({pct:.0f}%)",
        ]
        for entry in self.entries:
            lines.append(
                f"  {entry['label']:<38} {entry['units']:>5} × "
                f"${entry['unit_price']:.4f} = ${entry['amount_usd']:.4f}"
            )
        return "\n".join(lines)

    def write(self, path: Path) -> None:
        """Persist the ledger so each run's real cost is auditable."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "cap_usd": self.cap_usd,
                    "spent_usd": round(self.spent_usd, 6),
                    "entries": self.entries,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
