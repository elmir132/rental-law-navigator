# Video scripts — Rental Housing Law Navigator

Three 1-minute scripts (~150 words each ≈ 60s at a natural pace). `{{DOUBLE_BRACES}}` are
placeholders — fill them in from the finished build (`rules.json`,
`verification_audit.json`, `lookups.json`, `changes.json`). Suggested commands to pull each
number are listed under every script.

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

> Here's the app. I pick a starter address in Los Angeles. Behind it, we resolved the real
> legal city — the mailing label said "Van Nuys," but that's inside the City of Los Angeles,
> and the jurisdiction stack shows it.
>
> As of October first, these are the rules that apply — rent-increase limits, just-cause
> eviction — each with a result, a plain-language explanation, the citation, and the exact
> quote from the source document. I can open the source link to check it myself.
>
> Watch this one: it comes back *unknown*. The rule depends on the certificate-of-occupancy
> date, and that's not in the public data — so we don't guess.
>
> Now flip to a change case. California's AB 325: on December 31st it's not-yet-effective; on
> January 2nd it applies — {{T1_AFTER_COUNT}} California addresses affected. The struck
> Massachusetts ballot question? Affected set empty, exactly as it should be.

*Numbers to confirm:*
- `T1_AFTER_COUNT` — affected CA addresses in T1:
  `jq '.T1.affected_address_ids | length' changes.json`
- Optionally name a real starter `address_id` that returns `unknown` for the on-camera click.

---

## 3. Tech (1 min)

> The core design choice: the language model reads law, but it never decides. Extraction and
> reasoning are completely separate.
>
> First, extraction. We feed {{DOC_COUNT}} captured documents to Gemini at temperature zero
> and get back structured rule records — jurisdiction, category, status, effective date,
> citation. Every record must carry a verbatim quote.
>
> Then the trust layer: we check each quote actually appears in its source. {{VERIFIED_EXACT}}
> matched exactly, {{REPAIRED}} were snapped to the real text, and the rest were rejected —
> so every quote in our output is a true slice of an official document. That left
> {{RULE_COUNT}} verified rules.
>
> Reasoning is pure deterministic code: Census geocoding resolves the legal jurisdiction,
> then the engine checks coverage, dates, supersession, and conflicts across all 500
> addresses — defaulting to *unknown* when a fact is missing. Same inputs, same outputs,
> every time. Fully auditable.

*Numbers to confirm:*
- `DOC_COUNT` — captured docs read (54 unless the run scope changed):
  `ls starter_pack/corpus/text/*.txt | wc -l`
- `VERIFIED_EXACT` / `REPAIRED` — verification verdicts:
  `jq '[.[].verdict] | group_by(.) | map({(.[0]): length}) | add' verification_audit.json`
- `RULE_COUNT` — verified rules written:
  `jq '.rules | length' rules.json`
- (Optional) `applies` vs `unknown` totals for a stronger closing line:
  `jq '[.lookups[][].result] | group_by(.) | map({(.[0]): length}) | add' lookups.json`

---

### Fill-in checklist (after the build finishes)
| Placeholder | Source | Command |
|---|---|---|
| `RULE_COUNT` | `rules.json` | `jq '.rules \| length' rules.json` |
| `DOC_COUNT` | corpus | `ls starter_pack/corpus/text/*.txt \| wc -l` |
| `VERIFIED_EXACT`, `REPAIRED` | `verification_audit.json` | see script 3 |
| `T1_AFTER_COUNT` | `changes.json` | `jq '.T1.affected_address_ids \| length' changes.json` |

Timing tip: each script is ~150 words. If you speak faster, add one concrete example (a real
address or a specific law name); if slower, cut the parenthetical clauses first.
