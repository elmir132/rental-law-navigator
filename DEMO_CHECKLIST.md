# 60-second demo checklist

A tight three-address run that shows coverage, honesty (`unknown`), and the T3 conflict
flag. All address IDs below are real rows from `starter_pack/data/sample_addresses.csv`.

> **Verify before recording:** the build must be finished (`rules.json` present) and the app
> running (`streamlit run app.py`). Click through these three once and confirm each shows the
> result described below — the exact rules depend on the finished extraction. If an address
> doesn't show the intended result, swap in another row of the same city (candidates listed
> under each step).

## Setup (before you hit record)
- `streamlit run app.py`, "As of" date = **2026-10-01**, "Show pending laws" = **on**.
- Have the three IDs ready to select from the starter-address dropdown (fastest), or type
  the street + city if you're demoing the typed-address path.

---

## Beat 1 (~0:00–0:20) — a clear "applies" + citations
**Address: `A0016` — 3515 Fillmore St, San Francisco, CA** (built 1926, 21 units).

- Point at the **jurisdiction stack**: resolved to San Francisco, CA.
- Point at a rule that comes back **`applies`** (rent increase limits / just-cause).
- Say the line: *"Every answer has the result, a plain-language explanation, the citation,
  and the exact quote from the source."* Expand **Quoted source text** and point at it.
- *Backup SF rows if needed: `A0021` (22 Precita Av), `A0027` (3918 Fulton St).*

## Beat 2 (~0:20-0:38) - honesty: "unknown"
**Address: `A0008` - 1065 Summit Ave, Jersey City, NJ** (verified: 4 `unknown` results).

- Scroll to **C.46:8-55 Application process** (`Unknown`, "owner type is not in the supplied data").
- Say the line: *"This one is unknown. The rule depends on who owns the building, and that
  is not in the public data. We don't guess, we say what's missing."*
- Stay on this address for beat 3.

## Beat 3 (~0:38–0:60) — the T3 conflict flag
**Address: `A0008` — 1065 Summit Ave, Jersey City, NJ** (and/or Hoboken `A0002`).

- Note the NJ FAIR Act: as of 2026-10-01 it shows **`not_yet_effective`** (effective
  2027-07-01).
- Point at the **conflict flag** on this Jersey City address — the FAIR Act may preempt the
  local Jersey City / Hoboken algorithmic ban, so it's flagged for human review, not resolved
  silently.
- (Optional, if time) bump the "As of" date to **2027-07-02** and show the same rule flip to
  **`applies`**.
- Close: *"Enacted, pending, and conflicting laws are all handled separately — sourced, not
  guessed. Not legal advice."*
- *Backup NJ rows: Jersey City `A0012`, `A0017`; Hoboken `A0040`, `A0049`.*

---

## Order & timing summary
| Beat | Address | Shows | ~Time |
|---|---|---|---|
| 1 | `A0016` San Francisco | `applies` + citation + verbatim quote | 20s |
| 2 | `A0008` Jersey City | `unknown` (owner type not in data) | 18s |
| 3 | `A0008` Jersey City | T3 FAIR Act `not_yet_effective` + conflict flag | 22s |

**If you only have time for two:** keep Beat 2 (`unknown`) and Beat 3 (conflict flag) — they
show the judgment that sets this apart. **One extra flourish if you have a spare 5s:** mention
that mailing neighborhoods resolve to their legal city (e.g. Dorchester → Boston), which is
why jurisdiction is computed, not read off the label.
