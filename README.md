# Shram Drishti

An inspection assistant for India's four Labour Codes. It reads the registers and
returns an employer files, checks them against the law, and shows an inspector
exactly which cell on which page proves every problem it finds.

---

## The problem, in plain words

India has around half a billion workers. Most of them are in small workplaces —
a textile unit with forty people, a construction site, a warehouse. The law says
their employer must pay at least the minimum wage, pay double for overtime, deposit
provident fund contributions, keep a wage register, keep an attendance record, and
so on.

Somebody has to check that any of this actually happens.

That job belongs to a Labour Inspector, now called an Inspector-cum-Facilitator.
There are a few thousand of them. There are millions of workplaces. Do the
arithmetic and you get the real problem: **an inspector can physically visit only a
tiny fraction of the establishments they are responsible for.** So which ones do
they visit? Today, largely at random, or wherever a complaint happens to come from.

Meanwhile the paperwork keeps arriving. An employer submits a wage register, a
muster roll, a provident fund challan. Someone is supposed to read them. Reading
one month of filings for one factory properly takes an hour or more, because the
problems are rarely visible in any single document.

That last point is the heart of it. Consider a real pattern:

- The **wage register** lists 40 workers and is arithmetically perfect.
- The **provident fund filing** lists 34 workers and is also perfect.

Neither document is wrong on its own. But six workers are being paid without
provident fund contributions — money taken out of their retirement savings — and
you can only see it by holding the two documents side by side and matching names
that are spelled differently in each.

Or this one:

- The register shows a worker earning ₹18,000 a month.
- The provident fund filing declares that same worker's wages as ₹11,000.

Contributions are being calculated on a smaller number than the worker actually
earns. Again, invisible in either document alone.

These are not exotic cases. They are the ordinary shape of wage theft, and they are
exactly what a human reader misses at 3pm on a Friday with sixty more files to get
through.

**So there are two problems, not one:**

1. Reading the documents is slow, and the errors that matter are the ones a tired
   human reader is least likely to catch.
2. Inspectors have no reliable way to know which employer deserves a visit.

---

## What this system does

You upload the documents. It reads them, checks them against the Codes, and
produces a risk score. Employers get told what is wrong and how to fix it.
Inspectors get a list of establishments ranked by who most needs a visit.

Three things about how it works are worth explaining, because they are the
difference between something useful and something that merely looks impressive.

### It reads each page three ways, and checks them against each other

A scanned register is a photograph of numbers. Getting those numbers wrong is not a
small error — it decides whether an employer is accused of underpaying someone.

So every page is read three times over:

1. **The PDF's own text layer**, if it has one. This is exact — the actual
   characters the document was created with, not a guess. It also carries the
   position of every word on the page.
2. **OCR**, which recognises text from the page image. This is the only option for
   a scan or a phone photograph, and it gives the position of every word it reads.
3. **A vision model**, which is shown the page image *along with* both text
   readings above.

Why all three? Because each catches what the others miss. OCR misreads an 8 as a 3.
The model can see the page and correct it. But the model, left alone with no text to
check against, will occasionally produce a figure that looks entirely plausible and
is simply not on the page — not lying, just completing a pattern. Every number it
returns is therefore searched for among the words OCR and the text layer actually
found. **A figure that cannot be located on the page it was attributed to is not
used.** It is held for a person to look at.

This also produces something valuable as a side effect: because we know where each
word sits on the page, every finding can point at the exact cell it came from.

### The law is applied by rules, not by the model

This is the design decision that matters most, and it goes against the instinct to
use AI for everything.

The model does all the reading and all the judgement about messy reality — which
printed column is which, whether "R. Kumar" and "RAJESH KUMAR S/O RAM LAL" are the
same man, what an appointment letter written in prose actually says. Those questions
have no fixed answer and no threshold to look up. That is exactly what a model is
for.

But whether an employer has broken the law is decided by plain arithmetic against a
number written in an Act:

> Section 18(3) of the Code on Wages: total deductions **shall not exceed fifty per
> cent** of wages.

That is one number. Fifty. There is nothing for a model to figure out, and two good
reasons not to let it:

- **The same documents must give the same answer every time.** An employer who
  disputes a finding will have it re-checked. If the answer changes between runs,
  the finding cannot be enforced.
- **The reason must be something the employer can look up.** "Section 18(3) caps
  deductions at fifty per cent, this row shows seventy, here is the arithmetic, and
  here is the cell it came from" is defensible. "The model considered this
  non-compliant" is not — however accurate the model happens to be.

So the rules live in plain YAML files, one per Code, each carrying the section it
comes from, the source it was read from, and worked examples that must pass and must
fail. A lawyer can read them without reading any code. Where a threshold comes from
the Rules rather than the Act itself and we have not yet confirmed it, the rule says
so openly and its findings are marked accordingly.

The model does get a second pass, after the rules have run. It reviews each finding
against the evidence and can flag one as probably wrong. It can also raise problems
no rule anticipated — a fixed list of rules only ever finds what someone thought to
look for. But everything it raises that way is marked advisory: it carries no
statutory citation and never affects a score. It tells an inspector where to look.
It does not make legal conclusions.

### Submitting nothing does not count as compliance

The easiest way to break a compliance system is to give it nothing to check. No
documents, no violations found, perfect score.

So evidence completeness is measured and reported **separately** from the score, and
never folded into it. An establishment that submitted nothing is reported as
high-risk-with-no-evidence — and its inspection priority goes *up*, not down. An
unknown record is not a clean one.

---

## How the pieces fit together

```
Employer uploads a document
        │
        ▼
  Validate it        reject encrypted PDFs, files lying about their type,
                     and page-count bombs before spending anything on them
        │
        ▼
  Read the page      text layer + OCR + vision model, together
        │
        ▼
  Verify it          every figure must be findable on the page
                     the arithmetic must hold (gross = basic + DA + allowances,
                     net = gross + overtime − deductions)
                     identifiers must be the right shape
        │
        ▼
  Work out who       match each printed name to a real person across documents
                     "P. Nair" = "Prakash Nair S/O Devi Das" = "PRAKASH NAIR DEVI DAS"
        │
        ▼
  Apply the Codes    deterministic rules, each citing its section
        │
        ▼
  Score the risk     weighted per Code, with completeness reported separately
        │
        ▼
  Tell people        employer gets a notice saying what to fix and by when
                     inspector gets a ranked worklist
```

A row that failed verification is **excluded** from the legal check rather than
merely flagged. This matters more than it sounds: if two columns get read the wrong
way round, a deduction of fifty-five per cent reads as forty-five — inside the legal
limit — and a real breach silently disappears. Judging an employer compliant on a
row we know we misread is worse than declining to judge it.

---

## What it looks for

Roughly forty checks across the four Codes. A sample of the ones that actually
catch things:

**Code on Wages, 2019**
- Wages below the applicable state minimum for the worker's skill category
- Overtime paid at less than twice the ordinary rate (s.14)
- Deductions above fifty per cent of wages (s.18(3))
- Monthly wages paid after the seventh of the following month (s.17(1)(iv))
- Final settlement not paid within two working days of exit (s.17(2))
- Allowances inflated past half of total pay to shrink the base for contributions
  and gratuity (s.2(y) proviso)
- No day of rest in any period of seven days (s.13(1)(b))

**Code on Social Security, 2020**
- Workers in the wage register who are absent from the provident fund filing
- Contributions calculated on a wage base lower than the register shows
- Headcount that does not reconcile across register, filing and annual return

**Industrial Relations Code, 2020**
- No Works Committee at 100 or more workers (s.3(1))
- No Grievance Redressal Committee at 20 or more (s.4(1))
- Women's representation on that committee below their share of the workforce
  (s.4(4) proviso)
- No standing orders at 300 or more (s.28(1))
- Lay-off or retrenchment without prior government permission (Chapter X)

**Occupational Safety, Health and Working Conditions Code, 2020**
- Establishment registration missing or lapsed
- Appointment letters not issued to every employee (s.6)
- Daily and weekly working hours over the limit (s.25)
- Contract labour engaged through an unlicensed or lapsed contractor
- Accidents in the register that were never notified (s.10)
- Days paid fewer than days the muster roll shows present

Alongside these are statistical checks — Benford's law over the digit distribution
of wage figures, robust outlier detection, identical amounts repeated across workers
whose day counts differ. These catch records that were *written* rather than
calculated. They are advisory and never scored: an unusual number is not an illegal
one.

---

## How we know it works

Guessing is not good enough for something that accuses employers of underpaying
workers, so the system is tested against documents whose correct answers are known
in advance.

A generator produces a full month of filings for a fictional textile unit — employee
register, wage register, muster roll, provident fund challan, appointment letter —
with specific violations planted in specific rows, and writes an answer key
alongside. The documents are internally consistent and arithmetically correct, so
nothing is caught by accident. Names deliberately vary between documents the way
they really do.

Running the pipeline over it gives real numbers: which planted violations were
found, which were missed, and anything raised that was not planted.

Latest results:

| Input | Violations found |
|---|---|
| Digital PDFs | **13 of 13** |
| Scanned, image-only (no text layer, OCR only) | **12 of 13** |

The scanned run is the one that counts, because it is what employers actually
upload. Every figure traced back to a cell on the page, and findings carried
coordinates pointing at those cells.

An image-only version of each document is generated too, so the OCR-only path is
tested rather than assumed. A compliant version of the whole set can also be
generated, to measure false positives — because a system that finds a violation
everywhere is as useless as one that finds none.

The rule packs have their own gate. Every rule must carry a statutory citation, a
note of where that citation was read from, and worked examples that must pass and
must fail. That last requirement exists to catch one specific bug: an inverted
comparison, `<=` where `>=` belongs, which turns compliant employers into violators
silently and with a confident citation attached. Currently 40 rules, 87 worked
examples, zero errors.

---

## Being honest about what is not finished

This is a prototype, and pretending otherwise would be the wrong way to present it.

**Seventeen of the forty rules have thresholds we have not confirmed against
primary statutory text.** Not because we did not look — because the number lives in
the Central or State Rules rather than in the Act, and we do not have those Rules
yet. Those rules still run, but they are flagged in the interface, weighted lightly
in scoring, and the notice sent to an employer says plainly that the threshold comes
from a secondary source. They should not be enforced as they stand.

**The minimum wage figures come from a general reference table, not official state
notifications.** Every wage-floor finding carries that provenance, so nobody
mistakes it for the notified rate.

**Identity matching is good, not perfect.** It resolved 24 workers correctly across
four documents in the last run, but a register's totals row is still occasionally
transcribed as a person. The self-checks catch it every time — the row sums do not
match the printed total — but detection is not prevention.

**Uploaded files are stored on local disk.** Fine for a prototype, behind an
interface so it can be swapped for object storage, and a note in the deployment
configuration explains why that matters on an ephemeral filesystem.

**Alerts are recorded, not delivered.** Notices are composed and written to the
audit log with their dispatch time, so a cure period is provable. Actually sending
them needs credentials that belong to the Ministry, not to this codebase.

**Cloud OCR is a real privacy trade-off, and the code says so.** To find an Aadhaar
number on a page you must first read the page, so the page leaves your control
before anything can be redacted. That is acceptable against test documents and not
acceptable against real worker records, so the application refuses to start in
production unless someone explicitly acknowledges it.

---

## Some things that were built carefully, and why

**Money is stored as whole paise, never as a decimal number.** `0.1 + 0.2` does not
equal `0.3` in binary floating point. A finding that rests on a rounding artefact is
indefensible, so amounts are integers throughout and divided only for display.

**A missing value never becomes zero.** A wage register with no deduction recorded
produces "not known", not "zero". They are different findings, and a rule whose
inputs are unknown declines to judge rather than passing the employer. Absent data
is reported through completeness, not silently treated as compliance.

**Statistical anomalies can never affect a score.** A statistical outlier is not a
breach of law, and a score that moved on one would collapse the moment an employer
asked which section they had broken. This is enforced in the data model, not left to
discipline.

**The audit log is a hash chain.** Each entry stores the hash of the one before it,
so altering or deleting any historical record breaks every hash after it. If an
employer disputes a finding, the chain shows who created it, when, from which
version of which rule pack, and whether anyone has touched it since.

**Access denials return "not found", not "forbidden".** Telling an inspector for
Gujarat that a Maharashtra establishment exists but is off-limits leaks the
existence of establishments outside their jurisdiction. And an account with no
jurisdiction assigned gets no access at all, rather than all access — the failure
mode of a half-provisioned account should be seeing nothing, not seeing everything.

**Re-uploading a document replaces the old one.** An employer filing a corrected
March register expects it to supersede the original. Without that, both sets of rows
survive, 24 workers become 48, and the system reports a headcount discrepancy it
invented itself.

---

## Built with

React and TypeScript on the front, FastAPI and Python on the back, PostgreSQL for
storage. Documents are read by OCR.space and a vision model reached through
OpenRouter. The rule engine evaluates YAML expressions through a restricted
interpreter — parsed to a syntax tree and walked against an allow-list, never
`eval()`, because a rule pack is data and data must not become code execution.

No Docker, no message broker, no background worker fleet. A job table and background
tasks cover this workload, and infrastructure that has to be operated for no gain is
not worth carrying at this size.

---

## Running it locally

You need Python 3.12, Node 20, and a PostgreSQL database. Neon's free tier works.

Create a `.env` file in the project root:

```ini
DATABASE_URL=postgresql://user:password@host.neon.tech/db?sslmode=require
JWT_SECRET=any-random-string-of-48-characters-or-more
OPENROUTER_API_KEY=sk-or-v1-...
OCR_SPACE_API_KEY=your-ocr-space-key

# Must accept image input and support structured outputs. Avoid any model whose
# name ends in "-contributor": those are cheap because the provider may train on
# what you send, and page images of workers' pay records are not a reasonable
# thing to hand over for training.
LLM_MODEL=google/gemini-2.5-flash-lite
```

Then:

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

.venv\Scripts\python -m app.cli init-db        # create the tables
.venv\Scripts\python -m app.cli load-wages     # load the state wage table
.venv\Scripts\python -m app.cli create-admin   # create your first account
.venv\Scripts\python -m app.cli check-rules    # validate the rule packs

.venv\Scripts\uvicorn app.main:app --reload

# Frontend, in a second terminal
cd frontend
npm install
npm run dev
```

To see it do something, generate the test corpus and upload it:

```bash
cd backend
.venv\Scripts\python -m app.cli build-corpus --scanned
```

That writes five documents plus an answer key to `corpus/`, and image-only copies to
`corpus/scanned/`. Upload them through the Documents screen, run an assessment for
March 2026, and compare the findings against `ground_truth.json`.

---

## Repository layout

```
backend/
  app/
    api/          HTTP endpoints
    models/       database tables
    rules/        the rule engine: safe evaluator, schema, loader, checker
    services/     the pipeline — reading, verifying, matching, scoring, alerting
    cli.py        init-db, load-wages, create-admin, check-rules, build-corpus
  tests/
frontend/
  src/
    components/   layout, evidence viewer, upload panel
    pages/        the screens
    lib/          API client, auth, formatting
rule_packs/       the law, as data — one YAML file per Code
corpus/           generated test documents and their answer key
```

The four Labour Codes and the state wage table are kept as source text in
`storage/`. Every rule cites the file and provision it was read from, so a reviewer
can check any threshold against the text it came from.
