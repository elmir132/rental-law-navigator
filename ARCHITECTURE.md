# Architecture — Rental Housing Law Navigator (one page)

**Goal.** For any address in the sample, answer *which housing rules apply on the query
date, and how do the supplied change cases move that answer* — with a citation and a
verbatim source quote behind every result. The guiding principle is a hard split between
**extraction** (a language model reads law) and **reasoning** (deterministic code decides
coverage). The model never decides whether a rule applies; it only turns prose into
structured, quote-backed records.

```
┌────────────┐   ┌─────────────┐   ┌──────────────┐   ┌───────────┐
│ 1. Corpus  │ → │ 2. Extract  │ → │ 3. Verify    │ → │ rules.json│
│ 54 docs    │   │ LLM → JSON  │   │ quote ∈ src? │   │ schema ✓  │
└────────────┘   └─────────────┘   └──────────────┘   └─────┬─────┘
┌────────────┐   ┌─────────────┐                            │
│ 500 addrs  │ → │ 4. Geocode  │ ──── legal city/county ────┤
│ CSV        │   │ Census+alias│                            │
└────────────┘   └─────────────┘                            ▼
                                            ┌───────────────────────────┐
                                            │ 5. Deterministic engine   │
                                            │ jurisdiction · coverage ·  │
                                            │ dates · pending ·          │
                                            │ supersession · conflicts   │
                                            └──────┬─────────────┬───────┘
                                                   ▼             ▼
                                      lookups.json + changes.json   6. Streamlit app
```

### 1. Corpus — the supplied input
87 manifest records; **54 captured text documents** (`status = ok`) are the only inputs
read. 32 are link-only (terms-review / capture-blocked) and 1 is a manual-fetch failure —
excluded by design, no bulk scraping. 500 sample addresses across nine CA/NJ/MA cities;
legal jurisdiction is deliberately *not* supplied.

### 2. Extraction (`extract.py`) — prose → structured rules
Each document is chunked (~22k chars, 1.5k overlap) and sent to Gemini
(`gemini-2.5-flash`, `temperature=0`, JSON mode) with a strict prompt that fixes the six
categories and four status values, forbids invented rules/numbers/dates/citations, and
demands one **verbatim** quote per rule. Output is normalized into the schema's closed
vocabularies and validated against `rule_record.schema.json`. Every candidate is logged.

### 3. Verification (`verify.py`) — the trust layer
A rule survives only if its `quoted_span` is literally in the cited source. Normalized
exact match → quote rewritten to the real slice (`verified_exact`); else a near-match
window must score ≥ 0.90 (`repaired_near_match`); otherwise `rejected`. Verdicts land in
`verification_audit.json`. Net effect: every quote in `rules.json` is a true slice of an
official document.

### 4. Geocoding (`geo.py`) — address → legal jurisdiction
US Census Geocoder (batch for the 500 rows, single-address for typed input) returns
incorporated place, county, and coordinates. `normalize_legal_city` folds mailing
neighborhoods into their legal city (Dorchester → Boston, Van Nuys → Los Angeles, …).
Results cache to `geo_cache.json` keyed by an input hash; `--offline` resolves cities from
the alias table for a fully deterministic run.

### 5. Engine (`engine.py`) — deterministic coverage & conflict reasoning
Per rule × address × date: match jurisdiction; test coverage conditions (year-built /
CoO cutoffs, unit counts, owner type) and return **`unknown` with a reason** when a
required fact is missing or ambiguous (cutoff year, no owner names); apply status/date
logic (`failed` dropped, `pending` separated, future effective date → `not_yet_effective`);
downgrade overridden rules to `superseded`; surface `conflict_flag` for human review.
`lookup_all` → `lookups.json` (all 500). `changes.py` runs **T1–T5** → `changes.json`
(effective-date flips, city-boundary bans, FAIR-Act preemption conflict, pending bills,
and a struck ballot question that must yield an empty affected set).

### 6. Interface (`app.py`) — Streamlit demo
Starter or typed address → jurisdiction stack, "as of" date, pending-laws toggle, and per
rule: result, plain-language explanation, citation, source doc, retrieval date, and the
quoted source text with a link. Banner: **not legal advice**.

### Result vocabulary
`applies` · `unknown` · `superseded` · `not_yet_effective` · `pending` — non-matching
rules are omitted.

### Why this shape
Extraction is where an LLM is strong (reading messy legal prose) and reasoning is where it
is risky (silently guessing coverage). Isolating the two, gating every quote against its
source, and defaulting to `unknown` keeps the system auditable end-to-end and honest about
what the public data cannot answer.
