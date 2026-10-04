# Submission text — HackOS / Google Form

Copy-paste blocks for the submission forms. Pick the length that fits each field.

---

## Project name

**Rental Housing Law Navigator**

(Short tagline, if a field asks for one: *Address-level rental-law lookup with verified
citations.*)

---

## 2–3 sentence description (primary)

> Rental Housing Law Navigator answers, for any apartment address and date, which housing
> rules apply — rent caps, just-cause eviction, deposits, screening, and algorithmic
> rent-setting — each with its citation and a verbatim quote from the official source. A
> language model extracts the rules from the corpus with no hand-coding, and every quote is
> automatically verified against the source document before it can be shown. A deterministic
> engine resolves each address to its legal jurisdiction and decides coverage, effective
> dates, and conflicts, saying "unknown" instead of guessing when the public data is
> insufficient.

## Shorter variant (if the field is tight)

> An address-level rental-law navigator: it extracts housing rules from official text with
> no hand-coding, verifies every quote against its source, and uses deterministic logic to
> decide which rules apply to each address on a given date — citing the source for every
> answer and saying "unknown" rather than guessing.

## One-liner (if the field is a single line)

> Extracts rental-housing rules from official text with no hand-coding, verifies every quote
> against its source, and tells you which rules apply to an address — with citations, not
> guesses.

---

## Free-text field answers

**What problem does it solve?**
> After the RealPage algorithmic-pricing scrutiny, states and cities passed a fast-moving
> patchwork of rental-housing laws. For any given building, it is now genuinely hard to say
> which rules apply on a given date — the answer depends on jurisdiction, building age, unit
> count, effective dates, and pending or struck legislation. Our tool turns that question
> into a sourced, auditable answer.

**How does it work? / Technical approach**
> Two strictly separated layers. (1) Extraction: a language model reads the supplied corpus
> of official state and city law and returns structured rule records — jurisdiction,
> category, status, effective date, citation, and one verbatim supporting quote. Nothing is
> hand-coded. (2) Verification and reasoning: every quote is checked against its source
> document and rejected if it is not literally there, so each citation is trustworthy. A
> deterministic engine then resolves each address to its legal city via Census geocoding and
> evaluates coverage conditions, effective dates, supersession, and conflicts. When a
> required fact is missing from the public data, it returns "unknown" rather than guessing.

**What makes it trustworthy / responsible?**
> Every rule shown carries its citation, source document, retrieval date, and a verbatim
> quote — and that quote is machine-verified against the source. Enacted law is kept separate
> from pending and not-yet-effective law. Failed or struck laws create no results. The
> interface states it is not legal advice, and the model never decides whether a rule
> applies — only deterministic code does, which keeps the whole pipeline auditable and
> reproducible.

**What's extracted (categories), if asked:**
> Rent-increase limits, just-cause eviction, security deposits, application/screening fees,
> tenant-screening restrictions, and algorithmic rent-setting.

**Tech stack, if asked:**
> Python, Gemini for extraction (temperature 0, JSON output), JSON Schema validation, a
> custom quote-verification layer, the US Census Geocoder for jurisdiction resolution, and a
> Streamlit demo.

**Known limitations / honesty, if asked:**
> Coverage depends on public assessor data, which omits owner names and some construction
> dates and unit counts; those cases return "unknown" by design. The system reads only the
> supplied corpus and does not bulk-scrape blocked sources. It is a prototype, not legal
> advice.

---

*Reminder: the two-sentence pitch to keep consistent everywhere — "extracts rules from
official text with no hand-coding, and verifies every quote against its source."*
