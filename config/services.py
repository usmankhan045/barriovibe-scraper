"""BarrioVibe service catalogue, extracted verbatim from barriovibe.com/services.

Descriptions are the site's own wording, not a paraphrase. The DM writer reads
these, so drift between this file and the live site becomes drift between the
DM and what BarrioVibe actually sells.

`OFFERABLE` is the subset a lead in an allowlisted country can actually buy.
Pakistan-jurisdiction services (FBR, SECP, PSEB, IPO Pakistan, WeBOC, provincial
revenue authorities) are deliberately excluded: offering FBR tax filing to a
founder in Texas is worse than sending nothing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    slug: str
    name: str
    practice: str
    description: str
    offerable: bool  # deliverable to a lead in an allowlisted country


CATALOGUE: tuple[Service, ...] = (
    # ---- Software & AI (all globally deliverable) ----
    Service(
        "web-development", "Full-Stack Web Development", "Software & AI",
        "Marketing sites and full-stack web applications, front end and back end, built to load fast.",
        True),
    Service(
        "app-development", "App Development", "Software & AI",
        "iOS and Android apps built from a single codebase, taken through store review.",
        True),
    Service(
        "agentic-ai-development", "Agentic AI Development", "Software & AI",
        "AI agents that take an objective and work through the steps across your own tools and data.",
        True),
    Service(
        "rag-development", "RAG Systems Development", "Software & AI",
        "An AI that answers from your own documents and cites the passage it used.",
        True),
    Service(
        "digital-fte", "Digital FTE Development", "Software & AI",
        "A named AI built around one specific person, trained on their judgement and voice.",
        True),
    Service(
        "workflow-automation", "Workflow Automation", "Software & AI",
        "The manual work that happens between your tools, the copying and chasing and re-keying.",
        True),
    Service(
        "chatbot-development", "Chatbot Development", "Software & AI",
        "Support and sales chatbots for WhatsApp, your website and Instagram that answer from your own content.",
        True),
    Service(
        "ai-prompt-engineering", "AI Prompt Engineering", "Software & AI",
        "Prompt libraries, system prompts and written guidelines that make your team's AI output consistent.",
        True),

    # ---- Growth & Marketing (all globally deliverable) ----
    Service(
        "social-media-management", "Social Media Management", "Growth & Marketing",
        "Content planned, produced and published on the platforms you are actually on.",
        True),
    Service(
        "social-presence-management", "Social Media Presence Management", "Growth & Marketing",
        "Every account you have anywhere, run as one presence: the networks, the forums, the video platforms.",
        True),
    Service(
        "performance-marketing", "Performance Marketing", "Growth & Marketing",
        "Paid campaigns on Meta, Google, TikTok and LinkedIn, managed against cost per acquisition.",
        True),
    Service(
        "platform-monetization", "Platform Monetization", "Growth & Marketing",
        "Getting YouTube, TikTok and Facebook channels to the payout threshold.",
        True),

    # ---- E-commerce & Marketplaces (all globally deliverable) ----
    Service(
        "shopify-store-development", "Shopify Store Development", "E-commerce & Marketplaces",
        "A Shopify store built, launched and maintained, with the theme, catalogue, payments and shipping.",
        True),
    Service(
        "ecommerce-management", "E-commerce Management", "E-commerce & Marketplaces",
        "Day-to-day running of your online store and marketplace channels: listings, inventory, orders, returns.",
        True),

    # ---- International Expansion: US/UK/UAE-facing, offerable ----
    Service(
        "us-company-formation", "US Company Formation", "International Expansion",
        "A US LLC or C-Corporation registered in your name, with the EIN.",
        True),
    Service(
        "us-tax-filing", "US Federal & State Tax Filing", "International Expansion",
        "Federal and state returns for your US company and its owners, including the Form 5472 filing.",
        True),
    Service(
        "itin-application", "ITIN Application", "International Expansion",
        "An IRS Individual Taxpayer Identification Number for someone not eligible for a Social Security Number.",
        True),
    Service(
        "us-bookkeeping-payroll", "US Bookkeeping & Payroll", "International Expansion",
        "Books kept in US dollars to the standard a US return is filed from, plus payroll.",
        True),
    Service(
        "us-trademark-registration", "US Trademark Registration", "International Expansion",
        "Your brand registered with the USPTO.",
        True),
    Service(
        "uk-company-formation", "UK Company Formation & Companies House Compliance", "International Expansion",
        "A private limited company incorporated with Companies House, registered for Corporation Tax.",
        True),
    Service(
        "uk-bookkeeping", "UK Outsourced Bookkeeping", "International Expansion",
        "Monthly bookkeeping in Xero or QuickBooks Online, reconciled to your UK bank feeds.",
        True),
    Service(
        "uk-vat-corporation-tax", "UK VAT & Corporation Tax", "International Expansion",
        "VAT registration and quarterly Making Tax Digital returns, plus Corporation Tax registration.",
        True),
    Service(
        "uk-finance-department", "Outsourced Finance Department for UK SMEs", "International Expansion",
        "A monthly finance function covering bookkeeping, management accounts, cash flow and board reporting.",
        True),
    Service(
        "uk-payroll", "UK Payroll Services", "International Expansion",
        "PAYE payroll run to HMRC's Real Time Information rules.",
        True),
    Service(
        "uae-tax-bookkeeping", "UAE Taxation & Bookkeeping", "International Expansion",
        "Corporate tax and VAT registration and filing with the UAE Federal Tax Authority.",
        True),
    Service(
        "saudi-business-setup", "Saudi Arabia Business Setup", "International Expansion",
        "A business registered and licensed to operate in Saudi Arabia.",
        True),

    # ---- Pakistan-jurisdiction only: NEVER offered to allowlisted-country leads ----
    Service("financial-accounting", "Financial Accounting", "Finance & Tax",
            "Monthly management accounts and year-end financial statements under IFRS.", False),
    Service("bookkeeping", "Bookkeeping", "Finance & Tax",
            "Every sale, expense and bank transaction recorded and reconciled weekly.", False),
    Service("income-tax-filing", "Income Tax", "Finance & Tax",
            "NTN registration, annual income tax returns and wealth statements filed through FBR IRIS.", False),
    Service("sales-tax-registration-filing", "Sales Tax", "Finance & Tax",
            "Sales tax registration and monthly returns for FBR and the provincial revenue authorities.", False),
    Service("withholding-tax-statements", "Withholding Tax Statements", "Finance & Tax",
            "Quarterly and annual withholding statements filed under section 165.", False),
    Service("tax-advisory", "Tax Advisory", "Finance & Tax",
            "Planning, written opinions and representation.", False),
    Service("audit-assurance", "Audit & Assurance", "Finance & Tax",
            "Statutory audit support, internal audit, and agreed-upon procedures.", False),
    Service("financial-advisory", "Financial Advisory", "Finance & Tax",
            "Feasibility studies, cost and profitability analysis, internal controls and written SOPs.", False),
    Service("company-registration", "Company Registration", "Corporate & Legal",
            "Business registered in the right legal form: private limited, single member, LLP.", False),
    Service("corporate-secretarial-compliance", "Corporate Compliance", "Corporate & Legal",
            "Every SECP filing after incorporation, run on a calendar.", False),
    Service("npo-registration", "Non-Profit Registration", "Corporate & Legal",
            "A not-for-profit licensed under Section 42 and incorporated with SECP.", False),
    Service("pseb-registration", "PSEB Registration", "Corporate & Legal",
            "Registration with the Pakistan Software Export Board.", False),
    Service("trade-body-registration", "Chamber & Trade Body Membership", "Corporate & Legal",
            "Membership of your Chamber of Commerce and Industry.", False),
    Service("import-export-license", "Import & Export License", "Corporate & Legal",
            "WeBOC and PSW registration for import and export from Pakistan.", False),
    Service("contract-drafting", "Contract & Agreement Drafting", "Corporate & Legal",
            "Supply, employment, IP and shareholder agreements drafted to your facts.", False),
    Service("trademark-registration", "Trademark Registration", "Intellectual Property",
            "Your brand name and logo searched, filed and registered with IPO Pakistan.", False),
    Service("copyright-registration", "Copyright Registration", "Intellectual Property",
            "Your software, content or creative work registered with IPO Pakistan's Copyright Office.", False),
    Service("patent-registration", "Patent Registration", "Intellectual Property",
            "Your invention filed, examined and carried through to grant with IPO Pakistan.", False),
)

OFFERABLE: tuple[Service, ...] = tuple(s for s in CATALOGUE if s.offerable)
OFFERABLE_SLUGS: frozenset[str] = frozenset(s.slug for s in OFFERABLE)
BY_SLUG: dict[str, Service] = {s.slug: s for s in CATALOGUE}

assert len(CATALOGUE) == 44, f"expected 44 services, found {len(CATALOGUE)}"
assert len(OFFERABLE) == 26, f"expected 26 offerable services, found {len(OFFERABLE)}"


def catalogue_for_prompt() -> str:
    """Render the offerable services for an LLM prompt.

    Only offerable services appear: the model cannot recommend what it never sees,
    which is the structural guarantee that no Pakistan-only service is ever
    offered to an allowlisted-country lead.
    """
    lines: list[str] = []
    practice = None
    for svc in OFFERABLE:
        if svc.practice != practice:
            practice = svc.practice
            lines.append(f"\n## {practice}")
        lines.append(f"- [{svc.slug}] {svc.name}: {svc.description}")
    return "\n".join(lines).strip()
