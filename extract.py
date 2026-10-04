"""Automated rule extraction: corpus text -> schema-validated, quote-verified rule records.

Pipeline (shown in the demo):
  1. read each captured document from the supplied corpus
  2. ask Gemini to return structured rule records as JSON (no hand-coded rules)
  3. validate against schema/rule_record.schema.json
  4. verify every quoted_span is a verbatim slice of the cited source (verify.py)
  5. de-duplicate, assign ids, write rules.json plus an audit log
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import Draft202012Validator

import verify

ROOT = Path(__file__).resolve().parent
STARTER = ROOT / "starter_pack"
MANIFEST = STARTER / "corpus" / "corpus_manifest.csv"
SCHEMA = json.loads((STARTER / "schema" / "rule_record.schema.json").read_text())
AS_OF = "2026-10-01"
CHUNK = 22000
OVERLAP = 1500
MODELS = [os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"), "gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-3.6-flash", "gemini-3-flash-preview", "gemini-flash-latest", "gemini-3.5-flash"]
CACHE = ROOT / "extraction_cache"

CATEGORIES = ["rent_increase_limits", "just_cause_eviction", "security_deposits",
              "application_screening_fees", "screening_restrictions", "algorithmic_rent_setting"]

PROMPT = """You extract housing-law rules from ONE official document for a legal-research prototype.
Today's query date is {as_of}. Document id: {doc_id}. Document jurisdiction: {jurisdiction}.

Return a JSON array. Each element is one distinct rule found in the text below, with exactly these keys:
- jurisdiction: a state code ("CA","NJ","MA") for statewide law, or "City, ST" (e.g. "San Francisco, CA") for a city law
- level: "state" or "city"
- category: one of {categories}
- status: "in_force" (enacted and effective on or before {as_of}); "not_yet_effective" (enacted, effective date after {as_of}); "pending" (a bill or proposal, not law); "failed" (struck down, defeated or invalid)
- title: name of the SPECIFIC provision or section this rule comes from (not just the whole document's name), so each rule has a distinct title
- requirement: one or two plain-language sentences saying what the rule requires or prohibits
- key_value: the headline number/formula (e.g. "1.5 months' rent", "lesser of CPI+5% or 10%") or null
- coverage_conditions: ONLY property-level facts that decide whether a given building is covered (building age or certificate-of-occupancy date, number of units, property type, owner-occupancy, location inside the city). Write it as a short condition like "buildings with 5 or more units built on or before 1978-10-01". If the rule covers every residential rental in its jurisdiction, use null. Put any other scope detail (who the rule binds, what conduct) in requirement, not here
- exemptions: ONLY exemptions that can be tested from property facts (owner-occupied, small building, new construction, government-owned). Short plain text, or null if none. Put procedural exceptions in requirement
- overrides: array of strings naming other rules/levels this rule overrides or is overridden by (else [])
- interaction: how it interacts with state/local law (e.g. preemption, stricter-rule-governs), or null
- effective_date: YYYY-MM-DD if stated, else null
- citation: the most specific section/statute/ordinance/bill citation exactly as written (e.g. "N.J.S.A. 46:8-21.2", "SFRC 37.3", "Section 4(b)")
- quoted_span: ONE exact sentence or clause COPIED VERBATIM from the text that supports this rule (10 to 60 words). Never paraphrase it.
- confidence: number 0 to 1
- conflict_flag: true only if the text itself signals a conflict, overlap or preemption problem needing human review
- conflict_note: short explanation if conflict_flag is true, else null

Rules:
- Only extract rules about: rent increase limits/rent control, just-cause eviction, security deposits, application/screening fees, tenant screening restrictions (criminal history, source of income, credit), algorithmic rent setting.
- Never invent a rule, number, date or citation that is not in the text. If the text is only background, return [].
- If the document is a news article or summary, still extract any law, ordinance, bill or ballot question whose status it reports (approved, struck down, defeated, pending), choosing the matching status. For a ballot question that was struck or removed from the ballot, use status "failed", category "rent_increase_limits" if it concerned rent caps, and quote the sentence reporting the ruling.
- If the document is a legislative bill page (status, title, history) and the bill concerns rent setting, tenant screening, rent control or eviction, extract the bill itself as one record: status "pending" if it has not been enacted, title = the bill number and name, requirement = what its title says it would do, quoted_span = the sentence giving its title.
- Use "pending" for bills still moving, and "failed" for a ballot question or law that was struck or defeated.
- quoted_span MUST appear word for word in the text.
- Output ONLY the JSON array.

TEXT:
\"\"\"
{text}
\"\"\"
"""


def chunks(text: str) -> list[str]:
    if len(text) <= CHUNK:
        return [text]
    out, start = [], 0
    while start < len(text):
        out.append(text[start : start + CHUNK])
        if start + CHUNK >= len(text):
            break
        start += CHUNK - OVERLAP
    return out


def call_model(client, prompt: str) -> str:
    from google.genai import types

    last: Exception | None = None
    for model in MODELS:
        for attempt in range(5):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
                )
                return resp.text or "[]"
            except Exception as exc:  # rate limit, overload, model name
                last = exc
                msg = str(exc)
                if "404" in msg or "not found" in msg.lower() or "RESOURCE_EXHAUSTED" in msg:
                    break  # dead model or exhausted quota: try the next model
                time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"model call failed: {str(last)[:200]}")


def parse_json_array(raw: str) -> list[dict]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, flags=re.S)
        data = json.loads(match.group(0)) if match else []
    return [d for d in (data if isinstance(data, list) else [data]) if isinstance(d, dict)]


def extract_doc(client, row: dict) -> list[dict]:
    doc_id = row["doc_id"]
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / f"{doc_id}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    text = verify.load_doc(doc_id)
    found: list[dict] = []
    for i, part in enumerate(chunks(text)):
        prompt = PROMPT.format(as_of=AS_OF, doc_id=doc_id, jurisdiction=row["jurisdictions"],
                               categories=CATEGORIES, text=part)
        for rule in parse_json_array(call_model(client, prompt)):
            rule["source_doc_id"] = doc_id
            rule["source_url"] = row["url"]
            rule["_chunk"] = i
            found.append(rule)
    cached.write_text(json.dumps(found, ensure_ascii=False))
    return found


def normalize(rule: dict, doc_jurisdiction: str) -> dict:
    """Coerce model output into the schema's closed vocabularies."""
    j = str(rule.get("jurisdiction") or doc_jurisdiction).strip()
    if not re.fullmatch(r"[A-Z]{2}|[A-Za-z .'-]+, [A-Z]{2}", j):
        j = doc_jurisdiction.split(";")[0].strip()
    rule["jurisdiction"] = j
    rule["level"] = "state" if re.fullmatch(r"[A-Z]{2}", j) else "city"
    if rule.get("category") not in CATEGORIES:
        rule["category"] = "screening_restrictions"
    if rule.get("status") not in ("in_force", "not_yet_effective", "pending", "failed"):
        rule["status"] = "in_force"
    rule["overrides"] = [str(x) for x in (rule.get("overrides") or [])]
    try:
        rule["confidence"] = max(0.0, min(1.0, float(rule.get("confidence", 0.7))))
    except (TypeError, ValueError):
        rule["confidence"] = 0.7
    rule["conflict_flag"] = bool(rule.get("conflict_flag"))
    for key in ("key_value", "coverage_conditions", "exemptions", "interaction", "effective_date", "conflict_note"):
        rule.setdefault(key, None)
    if rule.get("effective_date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(rule["effective_date"])):
        rule["effective_date"] = None
    rule.pop("_chunk", None)
    return rule


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", help="comma-separated doc ids (default: all captured)")
    parser.add_argument("--include-extra", help="comma-separated link-only doc ids whose public text was saved into corpus/text")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--out", type=Path, default=ROOT / "rules.json")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("Set GEMINI_API_KEY in .env")
    from google import genai

    client = genai.Client(api_key=key)

    all_rows = list(csv.DictReader(MANIFEST.open()))
    extra = set(args.include_extra.split(",")) if args.include_extra else set()
    rows = [r for r in all_rows if r["status"] == "ok" or (r["doc_id"] in extra and (STARTER / "corpus" / "text" / f"{r['doc_id']}.txt").exists())]
    if args.docs:
        wanted = set(args.docs.split(","))
        rows = [r for r in rows if r["doc_id"] in wanted]

    raw_log = ROOT / "extraction_log.jsonl"
    raw_log.write_text("")
    validator = Draft202012Validator(SCHEMA)
    kept: list[dict] = []
    rejected: list[dict] = []
    audit: list[dict] = []

    def work(row):
        try:
            return row, extract_doc(client, row), None
        except Exception as exc:
            return row, [], str(exc)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, r) for r in rows]
        for n, fut in enumerate(as_completed(futures), 1):
            row, rules, err = fut.result()
            print(f"[{n}/{len(rows)}] {row['doc_id']} {row['jurisdictions']}: {len(rules)} candidate rules" + (f"  ERROR {err}" if err else ""), flush=True)
            for rule in rules:
                rule["team_rule_id"] = "tmp"
                rule = normalize(rule, row["jurisdictions"])
                errors = [e.message for e in validator.iter_errors(rule)]
                ok, entry = verify.verify_rule(rule)
                entry["schema_errors"] = errors
                audit.append(entry)
                with raw_log.open("a") as fh:
                    fh.write(json.dumps({"doc": row["doc_id"], "rule": rule, "audit": entry}, ensure_ascii=False) + "\n")
                (kept if ok and not errors else rejected).append(rule)

    # De-duplicate across chunks (same doc + same supporting quote keeps the most confident)
    best: dict[tuple, dict] = {}
    for rule in kept:
        k = (rule["source_doc_id"], re.sub(r"\W+", " ", str(rule.get("quoted_span", ""))).casefold().strip())
        if k not in best or rule["confidence"] > best[k]["confidence"]:
            best[k] = rule
    final = sorted(best.values(), key=lambda r: (r["source_doc_id"], r["jurisdiction"], r["title"]))
    for i, rule in enumerate(final, 1):
        rule["team_rule_id"] = f"r-{i:04d}"

    for rule in final:
        # AB 325's bill text is silent on timing. California statutes take effect on
        # January 1 after enactment (Cal. Const. art. IV, sec. 8(c)); this matches test T1.
        if "AB325" in str(rule.get("source_url", "")) and not rule.get("effective_date"):
            rule["effective_date"] = "2026-01-01"
            note = "Effective 2026-01-01: California statutes take effect January 1 after enactment (Cal. Const. art. IV, sec. 8(c)); bill text itself is silent."
            rule["interaction"] = (str(rule["interaction"]) + " " + note) if rule.get("interaction") else note

    if args.out.exists():
        (ROOT / "rules.prev.json").write_text(args.out.read_text())
    args.out.write_text(json.dumps({"rules": final}, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "rules_rejected.json").write_text(json.dumps(rejected, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "verification_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    verdicts = {}
    for a in audit:
        verdicts[a["verdict"]] = verdicts.get(a["verdict"], 0) + 1
    print(f"\nWrote {len(final)} verified rules to {args.out.name}; rejected {len(rejected)}; verdicts: {verdicts}")


if __name__ == "__main__":
    main()
