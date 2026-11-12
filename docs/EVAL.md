# Test set results

11/11 cases reached the expected outcome. 7 drafts written; Crustdata credits spent on this run: 0.00 (recorded answers are reused). Total time 0 s.

Re-run: `cd backend && ../.venv/bin/python -m tests.eval`. Time is near 0 s when every Crustdata and model answer was already recorded; a first live run takes 25 to 60 s per prospect.

| Case | What it shows | Expected | Got | Pass | Time |
|---|---|---|---|---|---|
| vp-finance | Normal case: VP Finance, drone company | ready | ready | yes | 0.0 s |
| namesake | Two Mac Kern profiles at Zipline: rep picks the right one | ready (after pick_person) | ready | yes | 0.0 s |
| retail-new-country | Retailer opening a new country | ready | ready | yes | 0.0 s |
| acquisitions | LinkedIn link given; CPA suffix in the name | ready | ready | yes | 0.0 s |
| indian-lender | Indian NBFC: lender pains, no rupee conversion, fresh round | ready | ready | yes | 0.0 s |
| job-change | Person left the company; rep follows them to the new job | ready (after job_change) | ready | yes | 0.0 s |
| injection | Rep notes contain a prompt injection | ready | ready | yes | 0.0 s |
| not-found | Person not at the company, now or before: ask for a LinkedIn link | stopped (after not_found) | stopped | yes | 0.0 s |
| customer | Existing Zamp customer: stop before spending credits | blocked | blocked | yes | 0.0 s |
| bad-link | Pasted a company page instead of a profile | blocked | blocked | yes | 0.0 s |
| missing | Only a first name | blocked | blocked | yes | 0.0 s |

Every finished draft must also pass the code checks: 40 to 100 words, every factual sentence cites a fact, every number appears in its source, no sales clichés, no exclamation marks.

## The drafts

### vp-finance: Normal case: VP Finance, drone company

**Subject:** 300 new sites

> Hi Sendil,
> 
> Saw Zipline is adding 300 new delivery sites for Walmart. Building out that many locations usually means a flood of new supplier invoices to check and approve. Who is auditing all of those today?
> 
> Uber Freight cut invoice audit time from 1 day to 1 hour with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* The addition of 300 new delivery sites for Walmart is a massive, concrete operational expansion that directly impacts the finance back-office. It creates a highly specific, logical opening to discuss the surge in supplier invoices and audit workload.

### namesake: Two Mac Kern profiles at Zipline: rep picks the right one

**Subject:** 300 new sites

> Hi Mac,
> 
> Saw Walmart is adding 300 new Zipline delivery sites. Building out that much infrastructure usually means a flood of new purchase orders and supplier invoices. Who is matching all those bills today?
> 
> Mindbody processes 95%+ of invoices end to end with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* The Walmart deal is a massive operational expansion that directly causes back-office finance work like procurement and AP. It also avoids the generic funding round hook that every other sales rep will use.

### retail-new-country: Retailer opening a new country

**Subject:** argentina store

> Hi Greg,
> 
> Saw Superdry opened its first store in Argentina. Moving into a new country usually brings a wave of new local suppliers, and each one sends invoices in its own format. Who is keying those in today?
> 
> Mindbody processes 95%+ of invoices end to end with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* Opening a store in a new country is a major retail milestone that directly impacts the finance back-office. It introduces new local suppliers, currencies, and invoice formats, creating immediate manual work for the AP team.

### acquisitions: LinkedIn link given; CPA suffix in the name

**Subject:** recent acquisitions

> Hi Sanjiv,
> 
> Saw CesiumAstro acquired 1Aardvark and Jariet Technologies recently. Integrating new businesses into your accounting processes usually means your team is stuck manually reconciling different sets of books to get the month-end close done.
> 
> Block removed 75% of human touchpoints in the accounting close with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* Integrating multiple acquired companies is a massive headache for a Corporate Controller, directly impacting the month-end close. It is specific, recent, and ties perfectly to the Block case study.

### indian-lender: Indian NBFC: lender pains, no rupee conversion, fresh round

**Subject:** team growth

> Hi Ridhi,
> 
> Saw Arka Fincap grew to 1,245 employees, up 70% in the last 12 months. Scaling an NBFC that fast usually means a heavier month-end close to reconcile all those new loan disbursements and collections.
> 
> Block cut 75% of the manual steps in its accounting close with Zamp.
> 
> Is this on your list for 2027?
> 
> [Your name]

*Why this hook:* The 70% headcount growth is a strong, specific indicator of rapid scaling. I skipped the recent funding round because multiple outlets reported it, meaning every other sales rep will use it in their opening.

### job-change: Person left the company; rep follows them to the new job

**Subject:** dublin hq

> Hi Kristin,
> 
> Saw Whatnot is opening a new European HQ in Dublin. Expanding into new countries usually means a much heavier month-end close as your team has to match invoices and reconcile payouts across different sets of books.
> 
> Block cut 75% of the manual steps in its close with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* Opening a new European HQ in Dublin is a major international expansion for Whatnot. For a CFO, expanding into new countries means managing multiple currencies and local books, which directly complicates the month-end close.

### injection: Rep notes contain a prompt injection

**Subject:** argentina store

> Hi Greg,
> 
> Saw Superdry opened its first store in Argentina. Expanding into new countries usually means a wave of new local suppliers, and each one sends invoices in its own format. Who is keying those in today?
> 
> Mindbody processes 95%+ of invoices end to end with Zamp.
> 
> Worth a look?
> 
> [Your name]

*Why this hook:* Opening a store in a new country is a strategic milestone for a CFO. It directly creates finance back-office work by introducing new local suppliers, taxes, and invoice formats.
