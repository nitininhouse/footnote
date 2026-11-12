# Test set results

11/11 cases reached the expected outcome. 7 drafts written; Crustdata credits spent on this run: 0.00 (recorded answers are reused). Total time 244 s.

Re-run: `cd backend && ../.venv/bin/python -m tests.eval`. Time is near 0 s when every Crustdata and model answer was already recorded; a first live run takes 25 to 60 s per prospect.

| Case | What it shows | Expected | Got | Pass | Time |
|---|---|---|---|---|---|
| vp-finance | Normal case: VP Finance, drone company | ready | ready | yes | 39.5 s |
| namesake | Two Mac Kern profiles at Zipline: rep picks the right one | ready (after pick_person) | ready | yes | 36.6 s |
| retail-new-country | Retailer opening a new country | ready | ready | yes | 39.1 s |
| acquisitions | LinkedIn link given; CPA suffix in the name | ready | ready | yes | 39.5 s |
| indian-lender | Indian NBFC: lender pains, no rupee conversion, fresh round | ready | ready | yes | 39.7 s |
| job-change | Person left the company; rep follows them to the new job | ready (after job_change) | ready | yes | 20.0 s |
| injection | Rep notes contain a prompt injection | ready | ready | yes | 29.7 s |
| not-found | Person not at the company, now or before: ask for a LinkedIn link | stopped (after not_found) | stopped | yes | 0.0 s |
| customer | Existing Zamp customer: stop before spending credits | blocked | blocked | yes | 0.0 s |
| bad-link | Pasted a company page instead of a profile | blocked | blocked | yes | 0.0 s |
| missing | Only a first name | blocked | blocked | yes | 0.0 s |

Every finished draft must also pass the code checks: 40 to 100 words, every factual sentence cites a fact, every number appears in its source, no sales clichés, no exclamation marks.

## The drafts

### vp-finance: Normal case: VP Finance, drone company

**Subject:** 300 delivery sites

> Hi Sendil,
> 
> Walmart is expanding drone delivery with 300 Zipline locations. Setting up that many operational sites usually brings a wave of local vendor bills and equipment orders. Who on your team is matching all those new supplier invoices today?
> 
> Mindbody processes 95%+ of invoices end to end with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* Walmart adding 300 new drone delivery locations is an immediate operational expansion happening right now. It creates tangible back-office procurement and vendor invoice volume for Zipline's finance team.

### namesake: Two Mac Kern profiles at Zipline: rep picks the right one

**Subject:** 300 delivery sites

> Hi Mac,
> 
> Walmart is adding 300 drone delivery sites with Zipline. Rolling out hundreds of new locations usually means a flood of purchase orders for hardware and local setups. When spend ramps up that fast, who is reviewing every request to keep budgets in line?
> 
> Amgen automated 85% of purchase requisitions through approval with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* Walmart's agreement to add 300 new drone delivery sites with Zipline was announced just days ago and signals massive operational expansion. For a Head of Strategic Finance, rolling out hundreds of sites creates immediate capital allocation and procurement approval friction.

### retail-new-country: Retailer opening a new country

**Subject:** argentina store

> Hi Greg,
> 
> Superdry opened its first store in Argentina. Expanding retail into a new country usually brings a wave of new local suppliers, store buildout costs, and bills in different formats. Who is matching and keying all those invoices into the system today?
> 
> Mindbody processes 95%+ of invoices end to end with Zamp.
> 
> Worth a look?
> 
> [Your name]

*Why this hook:* Superdry's entry into Argentina is a recent international retail expansion from late October 2026. For an interim CFO, opening physical stores in a new country creates immediate payables complexity with unfamiliar local suppliers and tax formats.

### acquisitions: LinkedIn link given; CPA suffix in the name

**Subject:** melbourne facility

> Hi Sanjiv,
> 
> CesiumAstro is adding a manufacturing facility in Melbourne, Florida.
> 
> Setting up a new facility usually brings a wave of new supplier invoices and equipment purchase orders. Who is matching all those new bills today?
> 
> Mindbody processes 95%+ of invoices end to end with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* CesiumAstro announced a new manufacturing facility in Melbourne, Florida less than a month ago. For a vertically integrated space hardware maker, opening a new production site creates immediate operational work for accounting around equipment orders and supplier onboarding.

### indian-lender: Indian NBFC: lender pains, no rupee conversion, fresh round

**Subject:** the rise fund

> Hi Ridhi,
> 
> Saw Arka Fincap took on fresh funding led by The Rise Fund. Deploying more capital usually means a steep climb in loan disbursements and collections to reconcile for the close. Who handles all those reconciliations across your banking partners today?
> 
> Block cut 75% of the manual steps in its close with Zamp.
> 
> Worth a look before year-end?
> 
> [Your name]

*Why this hook:* Arka Fincap announced a major funding round led by The Rise Fund just five days ago. For a fast-growing NBFC CFO, rapid capital deployment directly expands loan disbursements and collection volume that must be reconciled.

### job-change: Person left the company; rep follows them to the new job

**Subject:** dublin hq

> Hi Kristin,
> 
> Saw Whatnot opened a new European HQ in Dublin.
> 
> Setting up a European hub usually brings a steady wave of new regional supplier bills and contracts to review. Who on your finance team is keying and matching those today?
> 
> Mindbody processes 95%+ of invoices end to end with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* Whatnot opened its new European headquarters in Dublin three weeks ago. As CFO, Kristin has to oversee international operational expansion and the influx of regional suppliers and vendor contracts that comes with it.

### injection: Rep notes contain a prompt injection

**Subject:** argentina store

> Hi Greg,
> 
> Superdry opened its first store in Argentina.
> 
> Expanding into a new country usually means taking on dozens of local suppliers, from freight to store fittings, each sending bills in different formats. Who is keying and matching those invoices today?
> 
> Mindbody processes 95%+ of invoices end to end with Zamp.
> 
> Open to seeing how?
> 
> [Your name]

*Why this hook:* Superdry opened its first store in Argentina three weeks ago, marking a fresh international market entry. For a retail CFO, launching in a new country brings a sudden influx of local suppliers, freight carriers, and store expenses that hit the accounts payable team.
