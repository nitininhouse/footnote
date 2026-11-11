"""Who "we" are. Assumption for the case study: the rep is an SDR at Zamp.

Proof points are Zamp's own published results (zamp.ai homepage, Nov 2026).
"""
SELLER = {
    "company": "Zamp",
    "one_liner": "AI agents (digital employees) that own finance back-office work end to end",
    "workflows": ["accounts payable and invoice processing", "invoice approvals", "purchase requisitions and procurement",
                  "month-end close", "invoice audit", "chargebacks and disputes"],
    "buyers": ["CFO", "Controller", "VP Finance", "Head of Accounting", "Head of AP", "Head of Procurement",
               "Finance Operations lead"],
    # What makes back-office finance work grow, i.e. why a signal matters to us.
    "pain_triggers": {
        "new_finance_leader": "a new finance leader reviews tools and processes in the first months",
        "new_entity_or_country": "a new country or entity adds vendors, currencies, VAT/GST and a second close",
        "fast_growth": "headcount and order volume grow faster than the finance team",
        "funding": "new capital raises expectations for audit-ready books and faster reporting",
        "finance_hiring": "hiring AP/accounting staff shows manual work is piling up",
        "acquisition": "an acquisition means merging two sets of vendors, ledgers and approval flows",
        "pricing_change": "fee or pricing changes create billing, payout and reconciliation work",
        "manual_reconciliation": "job posts mentioning manual reconciliation or data handoffs",
    },
    "proof": [
        {"customer": "Instacart", "result": "cut AP approval time from 2 weeks to 2 days", "fits": ["accounts payable", "marketplace"]},
        {"customer": "Block", "result": "removed 75% of human touchpoints in the accounting close", "fits": ["close", "fintech"]},
        {"customer": "Amgen", "result": "automated 85% of purchase requisitions through approval", "fits": ["procurement", "enterprise"]},
        {"customer": "Uber Freight", "result": "cut invoice audit time from 1 day to 1 hour", "fits": ["invoice audit", "logistics", "marketplace"]},
        {"customer": "Mindbody", "result": "processes 95%+ of invoices end to end", "fits": ["accounts payable", "saas"]},
    ],
    "competitors": ["Ramp", "Brex", "Bill.com", "BILL", "Tipalti", "Coupa", "Stampli", "AppZen", "HighRadius", "Basware", "Airbase", "Navan"],
    "ask": "a 20-minute call",
    "tone": "plain, specific, peer-to-peer; no flattery, no hype, no exclamation marks",
}

FINANCE_TITLE_WORDS = ["Accounts Payable", "Accounting", "Controller", "Finance", "Procurement", "Payments", "Tax"]
