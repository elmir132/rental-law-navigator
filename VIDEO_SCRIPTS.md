# Video scripts — Rental Housing Law Navigator

Three 1-minute scripts (~150 words each ≈ 60s at a natural pace). Build numbers are filled
in from the finished run (123 verified rules, 59 documents, 118 exact / 8 repaired quotes,
500/500 lookups, T1=250 CA addresses). Commands to re-pull each number if the build changes
are listed under every script.

---

## 1. Team / problem (1 min)

> RealPage put algorithmic rent-setting on the map — and cities and states answered with a
> patchwork of new laws. If you manage apartments, one question is suddenly hard: for *this*
> building, on *this* date, which rules actually apply?
>
> The answer changes by jurisdiction, by building age, by unit count — and the law keeps
> moving. Pending bills, future effective dates, a ballot question that got struck down.
> Getting it wrong is a compliance risk; guessing is worse.
>
> So we built the Rental Housing Law Navigator. Point it at an address, pick a date, and it
> tells you which housing rules apply — rent caps, just-cause eviction, deposits, screening,
> algorithmic-pricing bans — each with the exact law and a quote from the source.
>
> And when the data can't decide, it says *unknown* instead of pretending. No legal advice,
> no guessing — just sourced answers.

*Numbers to confirm: none required (all framing). Keep the city/category framing accurate —
nine cities across CA, NJ, MA; six rule categories.*

---

## 2. Demo (1 min)

> Here's the app. I pick a starter address. Behind it, we resolved the real legal city — the
> mailing label can say a neighborhood like "Dorchester," but that's legally the City of
> Boston, and the jurisdiction stack shows the resolved city, not the label.
>
> As of October first, these are the rules that apply — rent-increase limits, just-cause
> eviction — each with a result, a plain-language explanation, the citation, and the exact
> quote from the source document. I can open the source link to check it myself.
>
> Watch this one: it comes back *unknown*. The rule depends on the certificate-of-occupancy
> date, and that's not in the public data — so we don't guess.
>
> Now flip to a change case. California's AB 325: on December 31st it's not-yet-effective; on
> January 2nd it applies — 250 California addresses affected. The struck Massachusetts ballot
> question? Affected set empty, exactly as it should be.

*Numbers (filled from the finished build):*
- T1 affects **250** CA addresses. (Re-pull: `jq '.T1.affected_address_ids | length' changes.json`)
- Suggested on-camera `unknown` click: `A0008` Jersey City (owner type not in the data), per `DEMO_CHECKLIST.md`.

---

## 3. Tech (1 min)

> The core design choice: the language model reads law, but it never decides. Extraction and
> reasoning are completely separate.
>
> First, extraction. We feed the official corpus — 59 documents — to Gemini at temperature
> zero and get back structured rule records: jurisdiction, category, status, effective date,
> citation. Every record must carry a verbatim quote.
>
> Then the trust layer: we check each quote actually appears in its source. 118 matched the
> source exactly, 8 we snapped to the real text, and the invented ones were rejected — so
> every quote we show is a true slice of an official document. After de-duplication, that
> left 123 verified rules.
>
> Reasoning is pure deterministic code: Census geocoding resolves the legal jurisdiction,
> then the engine checks coverage, dates, supersession, and conflicts across all 500
> addresses — defaulting to *unknown* when a fact is missing. Same inputs, same outputs,
> every time. Fully auditable.

*Numbers (filled from the finished build):* 59 documents · 118 exact + 8 repaired quotes ·
123 verified rules after de-duplication · all 500 addresses have lookups. Note: 118 + 8 is
the count of quotes *checked* (before de-duplication and including rejects), which is a
different denominator from the 123 final rules — the script wording avoids implying they add
up. Re-pull commands:
- `jq '.rules | length' rules.json` (verified rules)
- `jq '[.[].verdict] | group_by(.) | map({(.[0]): length}) | add' verification_audit.json` (verdict split)
- `jq '[.lookups[][].result] | group_by(.) | map({(.[0]): length}) | add' lookups.json` (applies vs unknown, optional closing stat)

---

### Filled values (from the finished build)
| Figure | Value | Re-pull command |
|---|---|---|
| Verified rules | 123 | `jq '.rules \| length' rules.json` |
| Documents | 59 | (reported by the extract run summary) |
| Quotes: exact / repaired | 118 / 8 | `jq '[.[].verdict] \| group_by(.) \| map({(.[0]): length}) \| add' verification_audit.json` |
| T1 affected (CA) | 250 | `jq '.T1.affected_address_ids \| length' changes.json` |
| Lookups coverage | 500 / 500 | `jq '.lookups \| length' lookups.json` |

Other change-test figures available if you want them in a longer cut: T2 affects 90
(Hoboken/Jersey City bounded, Newark excluded), T3 covers 140 NJ addresses with 90 conflict
flags, T4 covers 110, T5 is empty.

Timing tip: each script is ~150 words. If you speak faster, add one concrete example (a real
address or a specific law name); if slower, cut the parenthetical clauses first.
