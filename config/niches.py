"""Niche definitions and per-niche budget allocation.

Two of the six niches in the original brief are disabled after research:

  LOGISTICS  -- measured ~3% usable posts across ~30 sampled. Operators post
                pain as competence ("I found it, fixed it myself") rather than
                help-seeking, which is structural to the vertical rather than a
                query problem. The best-fit category (automated check calls) is
                owned by funded specialists. Good service fit, bad channel fit.

  REAL_ESTATE -- the worst pain-post density of any vertical examined. The
                 coaching segment deliberately writes synthetic pain content in
                 exactly the target vocabulary, so false positives are
                 adversarially similar to true positives. Also the loudest
                 voices are employees without budget.

Both are retained here, disabled, so they can be re-enabled without rebuilding.

A note carried from the real-estate research that applies to EVERY niche:
customer-facing AI (chatbots handling tenants, clients, buyers) is negatively
positioned -- communities have been pre-burned by it. Back-office automation
(reporting, document extraction, reconciliation) is received well. The DM
writer is constrained accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config import industries


@dataclass(frozen=True)
class Niche:
    key: str
    label: str
    enabled: bool
    # Share of the daily budget. Shares of enabled niches are normalised, so
    # disabling one redistributes its budget rather than losing it.
    weight: float
    industry_ids: list[int]
    # VERIFIED BY LIVE TEST: this must be a SINGLE keyword. A comma-separated
    # list ("Founder, CEO, CTO") silently matches nothing and returns zero
    # posts, which is how a whole run can cost money and produce no leads.
    author_keywords: str
    # Services this niche's leads can plausibly buy, by slug. Narrows what the
    # DM writer may offer so it never reaches for an irrelevant service.
    service_slugs: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


NICHES: tuple[Niche, ...] = (
    Niche(
        key="saas",
        label="B2B SaaS",
        enabled=True,
        weight=1.0,
        industry_ids=industries.B2B_SAAS,
        author_keywords="Founder",
        service_slugs=(
            "web-development", "app-development", "agentic-ai-development",
            "rag-development", "workflow-automation", "ai-prompt-engineering",
            "digital-fte", "us-company-formation", "uk-company-formation",
            "us-tax-filing", "itin-application",
        ),
        notes=(
            "Strongest cluster is hiring FRUSTRATION, not hiring itself: a role "
            "open for months with budget approved and no candidate. Second is "
            "agency/offshore failure -- they are in replacement mode. Plain "
            "'we're hiring a senior dev' is noise; every agency DMs those."
        ),
    ),
    Niche(
        key="agencies",
        label="Digital agencies (white-label)",
        enabled=True,
        weight=1.0,
        industry_ids=industries.DIGITAL_AGENCIES,
        author_keywords="Founder",
        service_slugs=(
            "web-development", "app-development", "shopify-store-development",
            "agentic-ai-development", "rag-development", "workflow-automation",
            "chatbot-development", "ai-prompt-engineering",
        ),
        notes=(
            "Highest noise: agency owners are professional content marketers, "
            "and the best-looking phrases were written by COMPETITORS doing ICP "
            "research. Directionality is essential -- most 'white label' posts "
            "are vendors offering, not agencies seeking. 'Ghosted' on an agency "
            "account usually means the PROSPECT ghosted them, not a developer."
        ),
    ),
    Niche(
        key="ecommerce",
        label="E-commerce / DTC",
        enabled=True,
        weight=1.0,
        industry_ids=industries.ECOMMERCE,
        author_keywords="Founder",
        service_slugs=(
            "shopify-store-development", "ecommerce-management",
            "workflow-automation", "web-development", "performance-marketing",
            "agentic-ai-development", "rag-development",
            "social-media-management",
        ),
        notes=(
            "Best wedge is operational: the manual work between Shopify, the "
            "3PL, the CRM and the spreadsheet. Marketing pain (CAC/ROAS) is the "
            "most agency-polluted category -- do not lead with it. 3PL switching "
            "language is the highest-intent signal found in this niche."
        ),
    ),
    Niche(
        key="professional",
        label="Professional services",
        enabled=True,
        weight=1.0,
        industry_ids=industries.PROFESSIONAL_SERVICES_SET,
        author_keywords="Founder",
        service_slugs=(
            "workflow-automation", "rag-development", "agentic-ai-development",
            "digital-fte", "ai-prompt-engineering", "web-development",
            "us-company-formation", "uk-company-formation", "uk-bookkeeping",
            "uk-payroll", "uk-finance-department",
        ),
        notes=(
            "Best fit for the AI/automation offer: these firms run on repetitive "
            "information work. Document extraction and report assembly are the "
            "safest pitches -- invisible back-office work that never touches the "
            "client relationship."
        ),
    ),

    Niche(
        key="referral",
        label="Referral requests (all niches)",
        enabled=True,
        weight=1.5,  # highest-yielding query type in live testing
        industry_ids=[],  # deliberately unrestricted: referral asks come from
                          # every industry and the construction self-filters
        author_keywords="",
        service_slugs=(
            "web-development", "app-development", "shopify-store-development",
            "workflow-automation", "agentic-ai-development", "rag-development",
            "ecommerce-management", "performance-marketing",
            "us-company-formation", "uk-company-formation", "uk-bookkeeping",
        ),
        notes=(
            "LIVE TEST: 'can anyone recommend' + service noun was the highest "
            "yielding construction, 4/5 passing all filters. Asking peers for a "
            "referral is the one form of buying intent people still express "
            "publicly, because it reads as community participation rather than "
            "admitting a problem."
        ),
    ),

    # ---- Disabled after research -------------------------------------------
    Niche(
        key="logistics",
        label="Logistics & transportation",
        enabled=False,
        weight=1.0,
        industry_ids=industries.LOGISTICS_SET,
        author_keywords="Founder",
        service_slugs=(
            "workflow-automation", "web-development", "app-development",
            "agentic-ai-development", "rag-development",
        ),
        notes=(
            "DISABLED. ~3% usable across ~30 sampled posts. Operators post pain "
            "as competence, not help-seeking. Rare good leads are swarmed by "
            "agencies within hours. Re-enable only to test, never as a funded bet."
        ),
    ),
    Niche(
        key="realestate",
        label="Real estate",
        enabled=False,
        weight=1.0,
        industry_ids=industries.REAL_ESTATE_SET,
        author_keywords="Founder",
        service_slugs=(
            "workflow-automation", "rag-development", "agentic-ai-development",
            "web-development", "performance-marketing",
        ),
        notes=(
            "DISABLED. Worst pain-post density examined. Coaches deliberately "
            "write synthetic pain in the target vocabulary, so false positives "
            "are adversarially similar to true positives. Loudest voices are "
            "employees without budget. If revisited, fund ONLY owner-reporting "
            "and document-extraction pain, which reaches actual budget holders."
        ),
    ),
)

ENABLED: tuple[Niche, ...] = tuple(n for n in NICHES if n.enabled)
BY_KEY: dict[str, Niche] = {n.key: n for n in NICHES}


def budget_shares() -> dict[str, float]:
    """Normalised budget share per enabled niche. Disabling one redistributes
    its share rather than shrinking total spend."""
    total = sum(n.weight for n in ENABLED)
    if total <= 0:
        return {}
    return {n.key: n.weight / total for n in ENABLED}
