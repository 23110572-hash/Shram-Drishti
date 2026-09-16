<div align="center">

# Shram Drishti

### AI-Driven Smart Inspection System for Labour Code Compliance

**Hackathon:** Digital Shram Sankalp — Reimagining India's Labour Ecosystem with AI
**Problem Statement:** PS-5 — AI-Driven Smart Inspection System for Labour Code Compliance for Shram Suvidha Portal

[**Live Application**](https://shram-drishti.vercel.app/) · [**Source Code**](https://github.com/23110572-hash/Shram-Drishti)

**Login:** `admin@gmail.com` · **Password:** `12345`

</div>

---

## Demo

<video src="https://github.com/23110572-hash/Shram-Drishti/raw/main/Demo.mp4" controls width="100%"></video>

If the player does not load, [**watch the demo here**](https://github.com/23110572-hash/Shram-Drishti/raw/main/Demo.mp4).

---

## The Problem Statement

> How can AI-enabled technologies and automated document-reading tools be utilised to enable intelligent document (PDFs, Scanned pdf/ image, Images) analysis, interpret compliances requirements under new labour codes, automatically flags anomalies, discrepancies, missing fields or non-compliance etc. and send automated alerts to employers and inspectors-cum-facilitator. Solution should also be able to generate a risk-based compliance scorecard for establishments.

India consolidated twenty-nine labour laws into four Labour Codes: the **Code on Wages 2019**, the **Industrial Relations Code 2020**, the **Code on Social Security 2020**, and the **Occupational Safety, Health and Working Conditions Code 2020**. Together with their Central Rules, these govern how millions of establishments must pay, record and protect their workers.

Compliance is proven with paper. An employer files an employee register, a wage register, a muster roll, wage slips, EPF and ESIC returns, licences, appointment letters and accident records. Every document is filed separately, and read on its own, each one almost always looks correct.

**That is exactly where the real violation hides.**

<div align="center">

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 330" width="900" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">
  <rect width="900" height="330" rx="14" fill="#f4f9fd"/>
  <text x="450" y="38" text-anchor="middle" font-size="19" font-weight="700" fill="#0f172a">One establishment, one month, four documents</text>
  <text x="450" y="60" text-anchor="middle" font-size="13" fill="#475569">Each document is internally consistent. Nothing looks wrong until they are compared.</text>

  <g>
    <rect x="40" y="90" width="180" height="96" rx="10" fill="#ffffff" stroke="#bae6fd" stroke-width="2"/>
    <text x="130" y="118" text-anchor="middle" font-size="13" font-weight="700" fill="#0369a1">Employee Register</text>
    <text x="130" y="152" text-anchor="middle" font-size="30" font-weight="800" fill="#0f172a">24</text>
    <text x="130" y="172" text-anchor="middle" font-size="12" fill="#64748b">workers listed</text>
  </g>
  <g>
    <rect x="240" y="90" width="180" height="96" rx="10" fill="#ffffff" stroke="#bae6fd" stroke-width="2"/>
    <text x="330" y="118" text-anchor="middle" font-size="13" font-weight="700" fill="#0369a1">Wage Register</text>
    <text x="330" y="152" text-anchor="middle" font-size="30" font-weight="800" fill="#0f172a">24</text>
    <text x="330" y="172" text-anchor="middle" font-size="12" fill="#64748b">workers paid</text>
  </g>
  <g>
    <rect x="440" y="90" width="180" height="96" rx="10" fill="#ffffff" stroke="#fcd34d" stroke-width="2"/>
    <text x="530" y="118" text-anchor="middle" font-size="13" font-weight="700" fill="#b45309">Muster Roll</text>
    <text x="530" y="152" text-anchor="middle" font-size="30" font-weight="800" fill="#0f172a">25</text>
    <text x="530" y="172" text-anchor="middle" font-size="12" fill="#64748b">workers present</text>
  </g>
  <g>
    <rect x="640" y="90" width="180" height="96" rx="10" fill="#ffffff" stroke="#fca5a5" stroke-width="2"/>
    <text x="730" y="118" text-anchor="middle" font-size="13" font-weight="700" fill="#b91c1c">EPF Return</text>
    <text x="730" y="152" text-anchor="middle" font-size="30" font-weight="800" fill="#0f172a">22</text>
    <text x="730" y="172" text-anchor="middle" font-size="12" fill="#64748b">workers covered</text>
  </g>

  <path d="M130 186 L130 214 L730 214 L730 186" stroke="#dc2626" stroke-width="2" fill="none" stroke-dasharray="6 4"/>
  <rect x="150" y="232" width="600" height="72" rx="10" fill="#fef2f2" stroke="#dc2626" stroke-width="2"/>
  <text x="450" y="258" text-anchor="middle" font-size="14" font-weight="700" fill="#991b1b">Only the comparison reveals it</text>
  <text x="450" y="280" text-anchor="middle" font-size="12.5" fill="#7f1d1d">2 workers are missing from provident fund coverage</text>
  <text x="450" y="296" text-anchor="middle" font-size="12.5" fill="#7f1d1d">1 worker was recorded present but never paid</text>
</svg>

</div>

Today an inspector finds that only by opening every file, tracing the same worker across four different layouts, comparing figures by hand, recalling which threshold applies at which headcount, and writing it up. It does not scale, and it is easy to miss.

**So the real problem is not "read a PDF". It is these five things:**

| # | Challenge |
|---|---|
| 1 | Documents arrive as clean PDFs, scanned pages and phone photographs |
| 2 | The same worker is written differently in every document |
| 3 | Obligations depend on headcount, sector and hazard, so applicability must be settled before anything is judged |
| 4 | The serious violations exist only in the comparison between documents |
| 5 | An inspector's time is the scarcest resource, so the output must be evidence, not guesswork |

---

## What I Built

I built a system that treats every document uploaded for one establishment and one period as **one interconnected body of evidence**, never as separate files.

Upload four or five documents together and Shram Drishti:

1. **Reads every document twice**, independently, and reconciles the two readings
2. **Links the same worker** across all of them
3. **Applies deterministic Labour Code rules** that carry real statutory citations
4. **Reports only what it can prove**, in plain English an employer can act on
5. **Generates a risk-based compliance scorecard**
6. **Sends automated alerts** to the employer and the inspector-cum-facilitator

And it stays honest about its own limits. Every figure traces back to a page. Anything it could not verify is marked unverified instead of asserted.

---

## System Architecture

<div align="center">

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 760" width="980" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">
  <rect width="980" height="760" rx="14" fill="#f4f9fd"/>
  <text x="490" y="40" text-anchor="middle" font-size="20" font-weight="700" fill="#0f172a">Shram Drishti — Architecture</text>
  <text x="490" y="63" text-anchor="middle" font-size="13" fill="#475569">AI reads the documents. Deterministic Labour Code rules decide compliance.</text>

  <rect x="40" y="88" width="410" height="74" rx="11" fill="#ffffff" stroke="#bae6fd" stroke-width="2"/>
  <text x="60" y="115" font-size="14" font-weight="700" fill="#0369a1">EMPLOYER</text>
  <text x="60" y="137" font-size="12.5" fill="#334155">Selects one establishment and uploads its registers,</text>
  <text x="60" y="153" font-size="12.5" fill="#334155">returns, challans and records together</text>

  <rect x="530" y="88" width="410" height="74" rx="11" fill="#ffffff" stroke="#bae6fd" stroke-width="2"/>
  <text x="550" y="115" font-size="14" font-weight="700" fill="#0369a1">INSPECTOR-CUM-FACILITATOR</text>
  <text x="550" y="137" font-size="12.5" fill="#334155">Receives risk-ranked establishments, evidence-backed</text>
  <text x="550" y="153" font-size="12.5" fill="#334155">findings and automated alerts</text>

  <rect x="230" y="192" width="520" height="62" rx="11" fill="#0f172a"/>
  <text x="490" y="218" text-anchor="middle" font-size="14" font-weight="700" fill="#ffffff">ONE ESTABLISHMENT UPLOAD BATCH</text>
  <text x="490" y="239" text-anchor="middle" font-size="12" fill="#cbd5e1">Assessment waits until every document in the batch has been read</text>

  <rect x="60" y="288" width="390" height="112" rx="11" fill="#ffffff" stroke="#38bdf8" stroke-width="2"/>
  <text x="80" y="314" font-size="13.5" font-weight="700" fill="#0369a1">READING 1 — OCR ENGINE</text>
  <text x="80" y="338" font-size="12.5" fill="#334155">Reads PDFs, scanned pages and images</text>
  <text x="80" y="357" font-size="12.5" fill="#334155">Returns text plus the position of every word</text>
  <text x="80" y="376" font-size="12.5" fill="#334155">Word positions become evidence coordinates</text>
  <text x="80" y="393" font-size="12" font-style="italic" fill="#64748b">Independent of the model reading</text>

  <rect x="530" y="288" width="390" height="112" rx="11" fill="#ffffff" stroke="#38bdf8" stroke-width="2"/>
  <text x="550" y="314" font-size="13.5" font-weight="700" fill="#0369a1">READING 2 — GEMINI VISION</text>
  <text x="550" y="338" font-size="12.5" fill="#334155">Reads the original document directly</text>
  <text x="550" y="357" font-size="12.5" fill="#334155">Interprets layout, wide tables, column headings</text>
  <text x="550" y="376" font-size="12.5" fill="#334155">Handles handwriting and poor-quality scans</text>
  <text x="550" y="393" font-size="12" font-style="italic" fill="#64748b">Independent of the OCR reading</text>

  <rect x="150" y="432" width="680" height="78" rx="11" fill="#e0f2fe" stroke="#0284c7" stroke-width="2"/>
  <text x="490" y="459" text-anchor="middle" font-size="14" font-weight="700" fill="#075985">RECONCILIATION INTO ONE VERIFIED RECORD</text>
  <text x="490" y="480" text-anchor="middle" font-size="12" fill="#0c4a6e">Readings compared · duplicate, header and total rows removed · printed totals re-checked · disagreements recorded</text>
  <text x="490" y="499" text-anchor="middle" font-size="12" font-style="italic" fill="#0369a1">Counting and arithmetic happen in code, never in the model</text>

  <rect x="290" y="540" width="400" height="56" rx="11" fill="#ffffff" stroke="#818cf8" stroke-width="2"/>
  <text x="490" y="564" text-anchor="middle" font-size="13.5" font-weight="700" fill="#4338ca">WORKER IDENTITY LINKING</text>
  <text x="490" y="584" text-anchor="middle" font-size="12" fill="#334155">One person recognised across every document by UAN, ESIC number, code and name</text>

  <rect x="60" y="626" width="390" height="104" rx="11" fill="#ffffff" stroke="#16a34a" stroke-width="2"/>
  <text x="80" y="652" font-size="13.5" font-weight="700" fill="#15803d">RULE ENGINE — DECIDES COMPLIANCE</text>
  <text x="80" y="675" font-size="12.5" fill="#334155">44 deterministic rules with statutory citations</text>
  <text x="80" y="694" font-size="12.5" fill="#334155">Thresholds, arithmetic and cross-document checks</text>
  <text x="80" y="713" font-size="12.5" fill="#334155">Every finding cites document, page and cell</text>

  <rect x="530" y="626" width="390" height="104" rx="11" fill="#ffffff" stroke="#f59e0b" stroke-width="2"/>
  <text x="550" y="652" font-size="13.5" font-weight="700" fill="#b45309">AI REVIEW — ADVISES ONLY</text>
  <text x="550" y="675" font-size="12.5" fill="#334155">Explains contradictions in plain English</text>
  <text x="550" y="694" font-size="12.5" fill="#334155">Raises leads the rules were never written for</text>
  <text x="550" y="713" font-size="12.5" fill="#334155">Cannot create a violation or move the score</text>

  <g stroke="#0284c7" stroke-width="2.5" fill="none">
    <path d="M245 162 L245 178 L470 178 L470 192"/>
    <path d="M735 162 L735 178 L510 178 L510 192" stroke="#94a3b8" stroke-dasharray="6 5"/>
    <path d="M390 254 L390 272 L255 272 L255 288"/>
    <path d="M590 254 L590 272 L725 272 L725 288"/>
    <path d="M255 400 L255 416 L390 416 L390 432"/>
    <path d="M725 400 L725 416 L590 416 L590 432"/>
    <path d="M490 510 L490 540"/>
    <path d="M420 596 L420 612 L255 612 L255 626"/>
    <path d="M560 596 L560 612 L725 612 L725 626"/>
  </g>
  <g fill="#0284c7">
    <polygon points="470,198 464,186 476,186"/>
    <polygon points="255,294 249,282 261,282"/>
    <polygon points="725,294 719,282 731,282"/>
    <polygon points="390,438 384,426 396,426"/>
    <polygon points="590,438 584,426 596,426"/>
    <polygon points="490,546 484,534 496,534"/>
    <polygon points="255,632 249,620 261,620"/>
    <polygon points="725,632 719,620 731,620"/>
  </g>
  <polygon points="510,198 504,186 516,186" fill="#94a3b8"/>
</svg>

</div>

---

## How It Works

### 1. One upload becomes one assessment

When an employer selects an establishment and submits their documents, I create a single durable upload batch. Every file is attached to it, and the assessment holds at a barrier until **every** document in that batch has finished being read.

This matters more than it sounds. Without the barrier, the wage register finishes first, an assessment runs on it alone, and the employer is told two workers are missing from EPF before the EPF return has even been opened. One batch means one honest result.

The employer sees a single progress card for the establishment:

<div align="center">

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 130" width="900" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">
  <rect width="900" height="130" rx="12" fill="#f4f9fd"/>
  <line x1="70" y1="62" x2="830" y2="62" stroke="#cbd5e1" stroke-width="3"/>
  <g>
    <circle cx="70" cy="62" r="13" fill="#0ea5e9"/>
    <text x="70" y="102" text-anchor="middle" font-size="11.5" font-weight="600" fill="#0f172a">Uploading</text>
    <text x="70" y="117" text-anchor="middle" font-size="11.5" font-weight="600" fill="#0f172a">documents</text>
  </g>
  <g>
    <circle cx="260" cy="62" r="13" fill="#0ea5e9"/>
    <text x="260" y="102" text-anchor="middle" font-size="11.5" font-weight="600" fill="#0f172a">Reading</text>
    <text x="260" y="117" text-anchor="middle" font-size="11.5" font-weight="600" fill="#0f172a">documents</text>
  </g>
  <g>
    <circle cx="450" cy="62" r="13" fill="#0ea5e9"/>
    <text x="450" y="102" text-anchor="middle" font-size="11.5" font-weight="600" fill="#0f172a">Checking the</text>
    <text x="450" y="117" text-anchor="middle" font-size="11.5" font-weight="600" fill="#0f172a">information</text>
  </g>
  <g>
    <circle cx="640" cy="62" r="13" fill="#0ea5e9"/>
    <text x="640" y="102" text-anchor="middle" font-size="11.5" font-weight="600" fill="#0f172a">Checking all</text>
    <text x="640" y="117" text-anchor="middle" font-size="11.5" font-weight="600" fill="#0f172a">documents together</text>
  </g>
  <g>
    <circle cx="830" cy="62" r="15" fill="#16a34a"/>
    <path d="M823 62 l5 6 l10 -12" stroke="#ffffff" stroke-width="2.6" fill="none" stroke-linecap="round"/>
    <text x="830" y="102" text-anchor="middle" font-size="11.5" font-weight="700" fill="#15803d">Completed</text>
  </g>
  <text x="450" y="30" text-anchor="middle" font-size="13" font-weight="700" fill="#334155">One card for the establishment, not one per file</text>
</svg>

</div>

### 2. Every document is read twice

This is the part I care about most, because extraction accuracy decides everything downstream.

Each document is read by **two independent engines**, and a third pass reconciles them into one strict record while logging every disagreement.

Two readings catch what one cannot. A wage register with 24 workers can easily come back as 27 if a repeated column header, a totals line, or a worker split across a page break is counted as a person. Reading it twice makes that visible instead of silent.

<div align="center">

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 300" width="900" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">
  <rect width="900" height="300" rx="14" fill="#f4f9fd"/>
  <text x="450" y="34" text-anchor="middle" font-size="17" font-weight="700" fill="#0f172a">Catching a wrong worker count before it becomes a false accusation</text>

  <rect x="50" y="60" width="180" height="60" rx="9" fill="#ffffff" stroke="#fca5a5" stroke-width="2"/>
  <text x="140" y="84" text-anchor="middle" font-size="12.5" font-weight="700" fill="#b91c1c">OCR reading</text>
  <text x="140" y="106" text-anchor="middle" font-size="15" font-weight="800" fill="#0f172a">27 rows</text>

  <rect x="50" y="136" width="180" height="60" rx="9" fill="#ffffff" stroke="#86efac" stroke-width="2"/>
  <text x="140" y="160" text-anchor="middle" font-size="12.5" font-weight="700" fill="#15803d">Gemini reading</text>
  <text x="140" y="182" text-anchor="middle" font-size="15" font-weight="800" fill="#0f172a">24 rows</text>

  <rect x="50" y="212" width="180" height="60" rx="9" fill="#ffffff" stroke="#93c5fd" stroke-width="2"/>
  <text x="140" y="236" text-anchor="middle" font-size="12.5" font-weight="700" fill="#1d4ed8">Printed on document</text>
  <text x="140" y="258" text-anchor="middle" font-size="15" font-weight="800" fill="#0f172a">24 workers</text>

  <rect x="300" y="106" width="250" height="120" rx="10" fill="#e0f2fe" stroke="#0284c7" stroke-width="2"/>
  <text x="425" y="132" text-anchor="middle" font-size="12.5" font-weight="700" fill="#075985">Deterministic checks</text>
  <text x="425" y="156" text-anchor="middle" font-size="11.5" fill="#0c4a6e">Unique employee codes and UANs</text>
  <text x="425" y="175" text-anchor="middle" font-size="11.5" fill="#0c4a6e">Repeated headers removed</text>
  <text x="425" y="194" text-anchor="middle" font-size="11.5" fill="#0c4a6e">Total rows removed</text>
  <text x="425" y="213" text-anchor="middle" font-size="11.5" fill="#0c4a6e">Compared to the printed total</text>

  <rect x="610" y="106" width="240" height="120" rx="10" fill="#f0fdf4" stroke="#16a34a" stroke-width="2"/>
  <text x="730" y="134" text-anchor="middle" font-size="12.5" font-weight="700" fill="#15803d">Verified result</text>
  <text x="730" y="166" text-anchor="middle" font-size="26" font-weight="800" fill="#0f172a">24</text>
  <text x="730" y="190" text-anchor="middle" font-size="11.5" fill="#166534">3 rows identified as duplicates</text>
  <text x="730" y="208" text-anchor="middle" font-size="11.5" fill="#166534">or non-worker lines</text>

  <g stroke="#0284c7" stroke-width="2.5" fill="none">
    <path d="M230 90 L265 90 L265 166 L300 166"/>
    <path d="M230 166 L300 166"/>
    <path d="M230 242 L265 242 L265 166 L300 166"/>
    <path d="M550 166 L610 166"/>
  </g>
  <polygon points="606,166 594,160 594,172" fill="#0284c7"/>
  <polygon points="296,166 284,160 284,172" fill="#0284c7"/>
</svg>

</div>

If the two readings still disagree, the value is **not** guessed. It is recorded as needing confirmation and kept out of legal judgement.

I deliberately refused one shortcut here. An earlier version took the highest worker count it saw across all sources, which meant one noisy scan could permanently raise an establishment's headcount and switch on obligations that did not apply to it. Now observed counts are reported beside the result, and the employer's declared profile is never silently overwritten.

### 3. Documents are linked into one picture

Workers are matched across documents using employee code, UAN, ESIC number and name, so the same person appearing in four different layouts becomes one worker.

That linking is what makes the real checks possible:

- Is everyone in payroll present in the EPF return?
- Do the paid days match the days recorded as present?
- Were overtime hours recorded but never paid?
- Is the contribution wage base lower than the wages in the register?
- Do the headcounts across registers and returns agree?

### 4. The law decides compliance, not the AI

Every legal conclusion comes from a deterministic rule pack, which I wrote directly from the official Code and Central Rules text.

There are **44 executable rules** across the four Codes. Each one carries:

- The exact section or rule it comes from
- Who it applies to, including headcount thresholds
- The evidence it needs before it may run at all
- A reproducible test
- A plain English explanation
- Passing and failing fixtures, so a rule written backwards cannot ship

Every rule is validated automatically. **44 rules · 100 fixtures · zero errors.**

I also removed rules instead of keeping them when the official text did not support them:

| Removed or corrected | Why |
|---|---|
| Works Committee triggered purely on headcount | The Code makes it follow a government order |
| A thirty-day grievance deadline | The provision says the committee *may* complete proceedings in that time |
| A twelve-hour daily cap | Replaced with the eight-hour normal working day the Rules actually state |
| Six separate appointment-letter findings | Consolidated into one, because six near-identical rows is noise, not insight |
| Minimum wage enforcement | Kept advisory, because operative rates come from state notifications |

A rule that accuses a compliant employer is worse than no rule at all.

### 5. What the AI is trusted with, and what it is not

I use AI aggressively, but never as the judge.

<div align="center">

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 250" width="900" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">
  <rect width="900" height="250" rx="14" fill="#f4f9fd"/>

  <rect x="40" y="30" width="390" height="190" rx="11" fill="#ffffff" stroke="#16a34a" stroke-width="2"/>
  <text x="235" y="60" text-anchor="middle" font-size="14" font-weight="700" fill="#15803d">AI DOES THIS</text>
  <text x="66" y="92" font-size="12.5" fill="#334155">Read PDFs, scans and photographs</text>
  <text x="66" y="115" font-size="12.5" fill="#334155">Understand messy headings and rebuild tables</text>
  <text x="66" y="138" font-size="12.5" fill="#334155">Map differently named columns onto one schema</text>
  <text x="66" y="161" font-size="12.5" fill="#334155">Explain contradictions in simple English</text>
  <text x="66" y="184" font-size="12.5" fill="#334155">Point out patterns rules were never written for</text>
  <text x="66" y="207" font-size="12.5" fill="#334155">Summarise all the documents together</text>

  <rect x="470" y="30" width="390" height="190" rx="11" fill="#ffffff" stroke="#dc2626" stroke-width="2"/>
  <text x="665" y="60" text-anchor="middle" font-size="14" font-weight="700" fill="#b91c1c">AI NEVER DOES THIS</text>
  <text x="496" y="92" font-size="12.5" fill="#334155">Decide whether the law was broken</text>
  <text x="496" y="115" font-size="12.5" fill="#334155">Count the final number of workers</text>
  <text x="496" y="138" font-size="12.5" fill="#334155">Do the arithmetic</text>
  <text x="496" y="161" font-size="12.5" fill="#334155">Choose a statutory threshold</text>
  <text x="496" y="184" font-size="12.5" fill="#334155">Change a severity or move the score</text>
  <text x="496" y="207" font-size="12.5" fill="#334155">Overwrite an establishment's declared profile</text>
</svg>

</div>

Model observations appear as advisory notes and are structurally excluded from scoring. A compliance finding needs a citation and a repeatable test, and an opinion has neither.

### 6. Findings an employer can actually act on

Every finding records the document, the page and the exact cell it came from, along with the figures compared and the provision relied on. Problems are shown as a simple numbered list in ordinary language, so an employer who has never read a Labour Code still understands what was found.

### 7. The risk-based compliance scorecard

The score answers one question: **based on the records actually submitted, how much risk is visible here?**

<div align="center">

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 330" width="900" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">
  <rect width="900" height="330" rx="14" fill="#f4f9fd"/>
  <text x="450" y="36" text-anchor="middle" font-size="17" font-weight="700" fill="#0f172a">How the score is decided</text>

  <rect x="50" y="62" width="360" height="132" rx="10" fill="#f0fdf4" stroke="#16a34a" stroke-width="2"/>
  <text x="230" y="88" text-anchor="middle" font-size="13" font-weight="700" fill="#15803d">COUNTS TOWARDS THE SCORE</text>
  <text x="74" y="116" font-size="12" fill="#334155">Rules that could truly be checked on the uploads</text>
  <text x="74" y="138" font-size="12" fill="#334155">Severity of each proven breach</text>
  <text x="74" y="160" font-size="12" fill="#334155">How many workers are affected</text>
  <text x="74" y="182" font-size="12" fill="#334155">Confidence in how the figure was read</text>

  <rect x="490" y="62" width="360" height="132" rx="10" fill="#fef2f2" stroke="#dc2626" stroke-width="2"/>
  <text x="670" y="88" text-anchor="middle" font-size="13" font-weight="700" fill="#b91c1c">NEVER COUNTS</text>
  <text x="514" y="116" font-size="12" fill="#334155">Documents the employer chose not to upload</text>
  <text x="514" y="138" font-size="12" fill="#334155">Codes with nothing available to test</text>
  <text x="514" y="160" font-size="12" fill="#334155">AI observations and statistical signals</text>
  <text x="514" y="182" font-size="12" fill="#334155">Values the two readings disagreed on</text>

  <rect x="180" y="222" width="540" height="80" rx="10" fill="#0f172a"/>
  <text x="450" y="250" text-anchor="middle" font-size="13.5" font-weight="700" fill="#ffffff">RISK-BASED COMPLIANCE SCORECARD</text>
  <text x="450" y="272" text-anchor="middle" font-size="12" fill="#cbd5e1">Score · risk band · inspection priority · suggested inspection interval</text>
  <text x="450" y="291" text-anchor="middle" font-size="11.5" font-style="italic" fill="#94a3b8">A critical breach caps the score, so it can never be averaged away</text>
</svg>

</div>

The scorecard is clearly labelled as covering the uploaded records, and it is never presented as a clean bill of health for the whole establishment. It also produces an inspection priority and interval, so a compliant employer is left alone while an officer's time goes where the risk actually is.

Scorecards are immutable, so an establishment's trajectory over time is real history rather than a number quietly restated.

### 8. Automated alerts

Once an assessment completes, the employer receives a notice describing what was found and what it rests on, and the inspector-cum-facilitator receives the risk picture and priority. Only findings that contributed to the current result are used, so nobody is chased over something stale.

---

## Design Principles I Held To

| Principle | What it means in practice |
|---|---|
| **Deterministic core, AI at the edges** | Reading and explaining is AI. Judgement and arithmetic are code. |
| **Evidence or nothing** | A value that cannot be traced to a page cannot support a finding. |
| **Batch-level assessment** | Documents for one establishment and period are judged together, never one at a time. |
| **Absence is not guilt** | A document never uploaded means a check could not run, not that a law was broken. |
| **Nothing is quietly overwritten** | Uncertain readings are surfaced, not merged into an employer's profile. |
| **Everything is logged** | Access to worker records is recorded with a purpose, and the audit trail is tamper-evident. |

---

## What You Will See in the Application

| Screen | What it does |
|---|---|
| **Upload** | Choose or register an establishment, drop the documents in, watch one progress card |
| **Result** | Plain-language verdict, document types checked, rules checked, workers found, numbered list of problems |
| **AI notes** | What the model noticed across the documents, in simple sentences, clearly marked as observations |
| **Rules** | All 44 rules with citations, thresholds and plain English explanations, so nothing about the judgement is hidden |
| **Worklist** | Establishments ranked by risk and inspection priority, for the inspector-cum-facilitator |

---

## Built With

**Frontend** React · TypeScript · Tailwind CSS
**Backend** Python · FastAPI · PostgreSQL
**Document reading** OCR engine · Gemini vision through OpenRouter
**Storage** Private object storage for uploaded documents
**Reliability** A durable job queue, so work survives a restart instead of being lost

---

## Honest Limitations

I would rather state these than have them discovered.

- Some obligations still wait on **state notifications**, such as current minimum wage rates and certain contribution figures. Those rules stay advisory instead of being enforced on guessed numbers.
- The rules cover what the uploaded document types can prove. Areas such as trade union processes, industrial disputes and maternity benefit need more document schemas before they can be judged fairly.
- No document-reading system is perfect. The goal is not zero error, it is **failing safely**: uncertain values are flagged, never asserted.
- The output supports an inspection. It does not replace an inspector, an authority or legal advice.

## What I Would Build Next

- Bring in state notifications so wage-floor checks can move from advisory to enforceable
- Extend document schemas to unlock the remaining chapters of the Codes
- Worker-level trend analysis across periods, not only within one period
- Inspector feedback on findings, feeding back into rule precision

---

<div align="center">

**Shram Drishti** · Built for **Digital Shram Sankalp** · Problem Statement **PS-5**

[Live Application](https://shram-drishti.vercel.app/) · [Source Code](https://github.com/23110572-hash/Shram-Drishti)

</div>
