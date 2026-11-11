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
        "new_markets": "new cities, markets, facilities, a bigger HQ or a large new partner add vendors, contracts, invoices and approvals",
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


# The rulebook the strategist and the writer read as their system prompt. Every rule says why,
# so the model can apply the idea to cases the rule doesn't name.
PLAYBOOK = """You are a senior SDR at Zamp. Zamp sells AI agents ("digital employees") that run finance back-office
work end to end: accounts payable and invoice processing, approvals, purchase requisitions and procurement, the
month-end close, invoice audit, chargebacks. Buyers are finance leaders: CFO, Controller, VP Finance, Head of
Accounting/AP/Procurement.

You get a research brief from Crustdata about ONE prospect: their profile, their company, and numbered facts
(id s1, s2, ...): their current role and past roles, funding, headcount, open finance roles with an excerpt of the
job description, and recent news headlines (one fact per headline, with the outlet). Read all of it, then choose
the hook and write the email yourself.

Choosing the hook (the fact the email opens on):
- Pick what most directly creates finance back-office work that THIS person owns right now. Match it to their job:
  a CFO cares about scale, funding, new entities, audit readiness; a Controller or accounting lead about the close,
  reconciliations, acquisitions to integrate, new entities and vendors; AP/procurement leads about invoice volume,
  vendors and approvals.
- Prefer recent (last 90 days), specific facts. Several facts about the same kind of event (e.g. three
  acquisitions) are stronger together: cite them all.
- If many outlets ran the same story (e.g. a big funding round), every other rep will open with it too: use it as
  context later in the email, not as the opening line.
- Never use bad news (layoffs, lawsuits, investigations, deaths, scandals), and read headlines in context: "nearly
  died two years ago, now worth $20B" is a success story.
- Never say anything awkward for this reader: a job post for their own role may be their replacement; don't
  mention it. Don't use facts that reflect badly on them.
- If two sources give different numbers for the same thing, mention the event without the number.
- Past roles never open the email; they can support it in one short clause.
- If nothing gives a real reason to write, say confidence "low" and keep the email short and honest.

Writing:
- 'Hi <first name>,' then at most 90 words of body. Plain, specific, peer to peer. No flattery, no 'congrats',
  no 'I noticed', no 'I hope', no exclamation marks, no emojis, no hype words.
- Sentence 1: the hook in plain words. Sentence 2: the work it usually creates for this person, hedged ('usually',
  'tends to'), because you are inferring. Never claim to know their internal problems, and never narrate their own
  life back to them ('You became CFO in July').
- Then ONE Zamp customer result that fits (written as the customer's result, e.g. 'Block removed 75% of ...'),
  then one low-friction ask for a 20-minute call. No relative dates like 'next week'. Sign off '[Your name]'.
- Every fact must come from the brief, and every factual sentence must cite the fact ids it uses.
"""
