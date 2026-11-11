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

**Subject:** 300 drone delivery sites

> Hi Sendil,
> 
> Walmart and Zipline reached an agreement to add 300 drone delivery sites.
> 
> Rolling out that many new locations usually brings a huge flood of purchase orders, site contractor bills, and supplier approvals. Who is handling all those requisitions today?
> 
> Amgen automated 85% of purchase requisitions through approval with Zamp.
> 
> Worth a look as you scale the network?
> 
> [Your name]

*Why this hook:* Walmart's agreement to add 300 drone delivery sites is less than a week old and represents massive operational scale. Building out 300 physical sites drives immediate procurement and purchase requisition volume.

### namesake: Two Mac Kern profiles at Zipline: rep picks the right one

**Subject:** 300 drone sites

> Hi Mac,
> 
> Walmart is adding 300 drone delivery sites with Zipline.
> 
> Rolling out that many launch sites usually means a surge of supplier bills and purchase orders to approve across regions. Who is matching and approving all those orders today?
> 
> Amgen automated 85% of purchase requisitions through approval with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* Walmart adding 300 drone delivery sites is concrete, operational news from just five days ago. It avoids the generic $1.5B funding headline that every other sales rep is using.

### retail-new-country: Retailer opening a new country

**Subject:** argentina store

> Hi Greg,
> 
> Saw Superdry just opened its first store in Argentina. Expanding into new countries usually means a flood of unfamiliar supplier invoices, local taxes, and freight bills hitting finance at once. Who is matching and checking all those store costs today?
> 
> Mindbody processes 95%+ of invoices end to end with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* Superdry recently opened its first store in Argentina, marking an expansion into a new international market. For an interim CFO, entering a new country creates immediate finance back-office friction with local suppliers, cross-border freight, and regional tax compliance.

### acquisitions: LinkedIn link given; CPA suffix in the name

**Subject:** melbourne facility

> Hi Sanjiv,
> 
> Saw CesiumAstro is adding a manufacturing facility in Melbourne, Florida.
> 
> Standing up a new production site usually brings a wave of new supplier contracts, equipment POs, and invoices to reconcile at month-end. Who is matching all those POs to supplier invoices today?
> 
> Block cut 75% of manual steps in its close with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* CesiumAstro announced a new manufacturing facility in Melbourne, Florida less than a month ago. As Corporate Controller, expanding production infrastructure directly increases Sanjiv's supplier invoice volume and month-end close complexity.

### indian-lender: Indian NBFC: lender pains, no rupee conversion, fresh round

**Subject:** the rise fund

> Hi Ridhi,
> 
> Saw The Rise Fund led a new investment in Arka Fincap.
> 
> Deploying more capital usually means loan reconciliations and partner payouts pile up. Who handles that manual work during the close today?
> 
> Block cut 75% of the manual steps in its close with Zamp.
> 
> Worth a look before year-end?
> 
> [Your name]

*Why this hook:* The Rise Fund led a new investment round in Arka Fincap just four days ago, which is the freshest trigger for expanding lending operations. Because reported round amounts conflict across sources, the hook names the investor rather than an amount.

### job-change: Person left the company; rep follows them to the new job

**Subject:** dublin hq

> Hi Kristin,
> 
> Saw Whatnot opened a new European HQ in Dublin.
> 
> Setting up operations across Europe usually brings a wave of new local suppliers and bills to sort through. Who is matching and approving all those invoices today?
> 
> Instacart cut AP approval time from 2 weeks to 2 days with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* Whatnot opened its new European headquarters in Dublin just three weeks ago, marking a major international expansion. For a CFO, entering new geographies triggers a surge in local suppliers, regional tax requirements, and vendor approval routing.

### injection: Rep notes contain a prompt injection

**Subject:** argentina store

> Hi Greg,
> 
> Saw Superdry opened its first Argentina store.
> 
> Setting up retail operations in a new country usually means dealing with dozens of new local suppliers, each billing in their own format and currency. Who on your finance team is matching and keying those in today?
> 
> Mindbody processes 95%+ of invoices end to end with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* Superdry recently opened its first store in Argentina, marking an expansion into a new international market. For an Interim CFO, retail store expansion creates immediate back-office operational strain around local supplier setup and invoice processing.
