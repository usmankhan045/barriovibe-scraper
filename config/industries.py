"""LinkedIn industry IDs (taxonomy V2).

Source: HarvestAPI's own linkedin-industry-codes-v2 CSV, the file the actor's
input schema points at, cross-checked against an independent published V2 list.
Both agree on every value below.

Why this file matters more than clever query wording: `authorsIndustryId`
filters SERVER-SIDE. Posts from outside these industries are never returned and
never charged. It costs nothing, and it does not consume any of the ~5 boolean
operators LinkedIn allows per query -- so all 5 can be spent on intent phrases
instead of trying to express "is a software company" in boolean.

Two semantics to keep in mind:
  1. The taxonomy is hierarchical and parents do NOT appear to roll up to
     children. Where a branch matters, both parent and child IDs are listed.
  2. It filters on the AUTHOR'S COMPANY industry, so authors with no resolvable
     current employer may be excluded. That is a real recall cost for solo
     operators, which is why the niches most likely to be solo use a wider set.
"""

from __future__ import annotations

# --- Technology -------------------------------------------------------------
SOFTWARE_DEVELOPMENT = 4
TECHNOLOGY_INFORMATION_INTERNET = 6
IT_SERVICES = 96
COMPUTER_NETWORK_SECURITY = 118
DATA_INFRASTRUCTURE_ANALYTICS = 2458
INFORMATION_SERVICES = 84
MOBILE_COMPUTING_SOFTWARE = 3100
INTERNET_PUBLISHING = 3132
TELECOMMUNICATIONS = 8

# --- Marketing / agencies ---------------------------------------------------
ADVERTISING_SERVICES = 80
MARKETING_SERVICES = 1862
PUBLIC_RELATIONS = 98
DESIGN_SERVICES = 99
MARKET_RESEARCH = 97
MEDIA_PRODUCTION = 126

# --- Retail / e-commerce ----------------------------------------------------
# There is no "E-commerce" industry in V2; online sellers sit under Retail.
RETAIL = 27
RETAIL_APPAREL_FASHION = 19
WHOLESALE = 133
CONSUMER_SERVICES = 91
PERSONAL_CARE_SERVICES = 2259
WELLNESS_FITNESS = 124

# --- Professional services --------------------------------------------------
PROFESSIONAL_SERVICES = 1810           # top-level parent
ACCOUNTING = 47
LEGAL_SERVICES = 10                    # parent of LAW_PRACTICE
LAW_PRACTICE = 9
BUSINESS_CONSULTING = 11               # "Management Consulting" folded in here
HUMAN_RESOURCES_SERVICES = 137
STAFFING_RECRUITING = 104

# --- Financial --------------------------------------------------------------
FINANCIAL_SERVICES = 43
BANKING = 41
INSURANCE = 42
INVESTMENT_MANAGEMENT = 46

# --- Real estate ------------------------------------------------------------
REAL_ESTATE = 44

# --- Logistics (retained for completeness; niche currently disabled) ---------
TRANSPORTATION_LOGISTICS = 116
TRUCK_TRANSPORTATION = 92
FREIGHT_PACKAGE_TRANSPORTATION = 87
WAREHOUSING_STORAGE = 93


# --- Per-niche industry sets ------------------------------------------------
# Deliberately not exhaustive. A wider set means more posts retrieved and more
# money spent, so each set is the narrowest that still covers the niche.

B2B_SAAS = [
    SOFTWARE_DEVELOPMENT,
    TECHNOLOGY_INFORMATION_INTERNET,
    IT_SERVICES,
    DATA_INFRASTRUCTURE_ANALYTICS,
    MOBILE_COMPUTING_SOFTWARE,
    COMPUTER_NETWORK_SECURITY,
]

DIGITAL_AGENCIES = [
    ADVERTISING_SERVICES,
    MARKETING_SERVICES,
    DESIGN_SERVICES,
    PUBLIC_RELATIONS,
]

ECOMMERCE = [
    RETAIL,
    RETAIL_APPAREL_FASHION,
    CONSUMER_SERVICES,
    PERSONAL_CARE_SERVICES,
    WELLNESS_FITNESS,
    WHOLESALE,
]

PROFESSIONAL_SERVICES_SET = [
    ACCOUNTING,
    LEGAL_SERVICES,
    LAW_PRACTICE,
    BUSINESS_CONSULTING,
    PROFESSIONAL_SERVICES,
    FINANCIAL_SERVICES,
    INSURANCE,
    HUMAN_RESOURCES_SERVICES,
    STAFFING_RECRUITING,
]

REAL_ESTATE_SET = [
    REAL_ESTATE,
]

LOGISTICS_SET = [
    TRANSPORTATION_LOGISTICS,
    TRUCK_TRANSPORTATION,
    FREIGHT_PACKAGE_TRANSPORTATION,
    WAREHOUSING_STORAGE,
]
