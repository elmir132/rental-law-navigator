# Rental Housing Law Navigator

Address-level housing-law lookup for the MIT AI Hackathon / RealPage discussion-draft
challenge (public data only, October 2026).

**The question it answers:** for any apartment address in the sample, *which housing
rules apply here on the query date, and how do the supplied law-change cases affect that
answer?* Every answer carries its citation, source document, retrieval date, and a
verbatim quote from the source. The interface is explicitly **not legal advice**.

The design keeps the legal boundary strict: a language model reads the corpus and
proposes structured rules, a verifier rejects any quote that is not literally in the
source, and a **deterministic** engine does all coverage, date, and conflict reasoning.
The model never decides whether a rule applies to an address — it only extracts.

---

## Pipeline at a glance

```
corpus  →  extraction (LLM)  →  quote verification  →  rules.json
 (59 docs)   extract.py           verify.py            (schema-valid)
                                                           │
sample_addresses.csv  →  geocoding  →  legal city/county  │
     (500 rows)            geo.py                          │
                                                           ▼
                                        deterministic engine (engine.py)
                                        jurisdiction · coverage · dates ·
                                        pending · supersession · conflicts
                                                           │
                                     ┌─────────────────────┼─────────────────────┐
                                     ▼                     ▼                     ▼
                               lookups.json          changes.json          Streamlit app
                              (all 500 addrs)        (T1–T5, changes.py)      (app.py)
```

See `ARCHITECTURE.md` for the one-page description of each stage.

---

## 1. Corpus (the supplied input)

Everything lives under `starter_pack/`:

| Path | What it is |
|---|---|
| `corpus/corpus_manifest.csv` | 87 source records: `doc_id`, jurisdiction, URL, source type, capture status |
| `corpus/text/` | 59 captured plain-text documents, each headed with its source URL and retrieval date |
| `corpus/links_only.csv` | 29 link-only sources (terms-review or capture-blocked) + 1 manual-fetch failure |
| `data/sample_addresses.csv` | 500 multifamily properties from public assessor data |
| `schema/rule_record.schema.json` | Required JSON Schema for every rule record |
| `dev/change_tests.json` | The five deterministic change tests T1–T5 |
| `submission_templates/` | Example `rules.json`, `lookups.json`, `changes.json` |

The extractor reads the **59 captured text documents** under `corpus/text/` (87 manifest
records in total; 57 are marked `status = ok`, 29 are link-only, and 1 is a manual-fetch
failure). Link-only and blocked sources are left out by design — we do not bulk-scrape
sources whose terms forbid it.

The 500 sample addresses span nine cities: Los Angeles 80, San Francisco 80, San Diego 50,
Berkeley 40, Jersey City 50, Hoboken 40, Newark 50, Boston 60, Cambridge 50. **The legal
jurisdiction is not given** — `postal_city` is a mailing label, so resolving it is part of
the pipeline (stage 4). Several public-record gaps (missing year built, missing unit
counts, no owner names) are handled explicitly rather than guessed.

## 2. Extraction (`extract.py`)

Automated, as the event requires — no hand-coded rules. For each of the 59 captured
documents:

1. Load the document text (large files are split into ~22k-char chunks with 1.5k overlap).
2. Send one strict prompt per chunk to Gemini (`gemini-2.5-flash`, `temperature=0`,
   JSON response mode) asking for an array of structured rule records.
3. The prompt pins the six categories, the four status values, the query date
   (2026-10-01), and forbids inventing any rule, number, date, or citation. It requires
   one **verbatim** supporting quote (`quoted_span`) per rule.
4. Each candidate rule is normalized into the schema's closed vocabularies, validated
   against `schema/rule_record.schema.json`, and passed to the verifier.
5. Verified, schema-valid rules are de-duplicated (same doc + same quote keeps the most
   confident), assigned stable ids `r-0001…`, and written to `rules.json`.

The six rule categories: `rent_increase_limits`, `just_cause_eviction`,
`security_deposits`, `application_screening_fees`, `screening_restrictions`,
`algorithmic_rent_setting`.

Every candidate — kept or rejected — is logged to `extraction_log.jsonl`, and a
`verification_audit.json` records the verdict for each.

## 3. Quote verification (`verify.py`)

This is the trust layer. A rule is only kept if its `quoted_span` really appears in the
cited document:

- Text is normalized (smart quotes/dashes folded, whitespace collapsed, lower-cased)
  while keeping a map back to the original character offsets.
- An **exact** normalized match → the quote is replaced with the real verbatim slice from
  the source (`verified_exact`).
- Otherwise a near-match search locates the opening words and compares a same-length
  window; only matches ≥ 0.90 similarity are accepted, again rewriting the quote to the
  real source text (`repaired_near_match`).
- Anything below threshold is **rejected** (`rejected_quote_not_in_source`) and never
  reaches `rules.json`.

The result: every quote shown in the app is a literal slice of an official document, not
a paraphrase.

## 4. Geocoding (`geo.py`)

Resolves each address to its **legal** jurisdiction:

- Batch mode sends up to 10,000 rows to the US Census Geocoder
  (`geographies/addressbatch`) and reads back the incorporated place, county, and
  coordinates.
- A single-address mode (`geocode_one`) backs the "enter an address" path in the app.
- `normalize_legal_city` maps mailing neighborhoods to their legal city (e.g. Dorchester →
  Boston, Van Nuys/Sylmar/Reseda → Los Angeles, San Ysidro → San Diego), so a mailing
  label is never treated as its own jurisdiction.
- Results are cached in `geo_cache.json`, keyed by a hash of the address inputs, so reruns
  are reproducible and offline.
- `--offline` skips Census entirely and resolves cities from the alias table — a fully
  deterministic local run for the demo.

## 5. Engine (`engine.py`)

The deterministic core. It evaluates each validated rule against each address and the
query date and **never guesses**:

- **Jurisdiction match** — state code vs. state, or `City, ST` vs. resolved legal city.
- **Coverage conditions** — year-built / certificate-of-occupancy cutoffs, unit-count
  thresholds, owner type. If a required fact is missing (or the address is *in* a cutoff
  year, since year built ≠ certificate date), the result is `unknown` with a reason.
- **Status and dates** — `failed` rules are dropped; `pending` is reported separately; a
  future `effective_date` yields `not_yet_effective`; the effective date wins once reached.
- **Supersession** — a rule that overrides another downgrades the weaker match to
  `superseded` (e.g. local rent control over the statewide cap).
- **Conflicts** — surfaced via `conflict_flag` for human review, not resolved silently.

`lookup_all` runs this across all 500 addresses → `lookups.json`.
`changes.py` runs the five change tests → `changes.json`:

| Test | Checks |
|---|---|
| T1 | California AB 325 / SB 763: `not_yet_effective` on 2025-12-31, `applies` on 2026-01-02 |
| T2 | Hoboken vs Jersey City algorithmic bans — correct city boundary, neither for Newark |
| T3 | NJ FAIR Act: `not_yet_effective` now, `applies` 2027-07-02, conflict-flag JC/Hoboken |
| T4 | MA S.2983 / H.5222: pending now, affected set = all MA addresses if enacted |
| T5 | MA rent-control ballot question (struck): affected set must be **empty** |

## 6. Results & demo

- **`rules.json`** — extracted, schema-validated records with verbatim quotes.
- **`lookups.json`** — `{"as_of": …, "lookups": {address_id: [{team_rule_id, result,
  explanation, conflict_flag}]}}` for all 500 addresses.
- **`changes.json`** — affected and conflict-flagged address sets for T1–T5.

Result values: `applies`, `unknown`, `superseded`, `not_yet_effective`, `pending`
(non-matching rules are left out).

**Current build (all 8 smoke-test checks pass):** 123 verified rules extracted
automatically from 59 documents; of the quotes checked, 118 matched the source exactly and
8 were repaired to the source text (invented quotes rejected). 500/500 addresses have
lookups. Change tests: T1 affects 250 CA addresses; T2 affects 90 (Hoboken and Jersey City
bounded, Newark excluded); T3 covers 140 NJ addresses with 90 conflict flags; T4 covers
110; T5 is empty.

The Streamlit app (`app.py`) looks up a starter address or a typed address, shows the
jurisdiction stack, an "as of" date, a pending-laws toggle, and for every rule the result,
plain-language explanation, citation, source document, retrieval date, and the quoted
source text with a link.

---

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set `GEMINI_API_KEY` in `.env`, then run the automated extraction over the 59 captured
documents:

```bash
python extract.py                 # writes rules.json + audit logs
```

Build the address and change outputs:

```bash
python build.py --offline         # deterministic local run (city aliases, no Census)
python build.py --force-geo       # fresh Census geocoding + cache
```

Launch the demo:

```bash
streamlit run app.py
```

Generated JSON (`rules.json`, `lookups.json`, `changes.json`, `geo_cache.json`) is
derived and Git-ignored; commit it only if the submission instructions require it.

## Design boundaries

- Missing owner type, unit count, or certificate date produces `unknown`; the engine does
  not guess.
- Mailing neighborhoods are normalized to their legal city for the sample.
- Pending and not-yet-effective laws are shown separately from rules in force.
- Failed rules (e.g. struck ballot questions) are omitted from lookups and create no
  affected addresses.
- Source document, citation, URL, retrieval date, and verbatim quote stay attached to
  every rule shown.
- Not legal advice — the interface explains supplied public sources and is not a
  compliance certification.
