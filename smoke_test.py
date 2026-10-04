"""Final submission safety checks for the generated JSON artifacts.

Run from the repository root with:

    python smoke_test.py

This deliberately uses the offline legal-city normalization so the final check
does not depend on a network call or an ignored geo_cache.json file.
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

import changes
import geo


ROOT = Path(__file__).resolve().parent
ALLOWED_RESULTS = {"applies", "unknown", "superseded", "not_yet_effective", "pending"}
EXPECTED_TESTS = {"T1", "T2", "T3", "T4", "T5"}


def fail(message: str) -> None:
    raise AssertionError(message)


def read_json(path: Path) -> Any:
    if not path.exists():
        fail(f"Missing required generated file: {path.name}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON in {path.name}: {exc}")


def load_rules() -> list[dict[str, Any]]:
    payload = read_json(ROOT / "rules.json")
    rules = payload.get("rules") if isinstance(payload, dict) else payload
    if not isinstance(rules, list) or not rules:
        fail("rules.json must contain a non-empty list of rules")
    schema = read_json(ROOT / "starter_pack" / "schema" / "rule_record.schema.json")
    validator = Draft202012Validator(schema)
    errors = []
    for index, rule in enumerate(rules):
        errors.extend((index, error) for error in validator.iter_errors(rule))
    if errors:
        details = "; ".join(f"rule[{index}]: {error.message}" for index, error in errors[:5])
        fail(f"rules.json failed schema validation ({len(errors)} errors): {details}")
    ids = [rule.get("team_rule_id") for rule in rules]
    if any(not rule_id for rule_id in ids):
        fail("Every rule must have team_rule_id")
    if len(ids) != len(set(ids)):
        fail("rules.json contains duplicate team_rule_id values")
    return rules


def load_address_ids() -> list[str]:
    path = ROOT / "starter_pack" / "data" / "sample_addresses.csv"
    with path.open(newline="") as handle:
        ids = [row["address_id"] for row in csv.DictReader(handle)]
    if len(ids) != 500:
        fail(f"Expected 500 sample addresses, found {len(ids)}")
    if len(ids) != len(set(ids)):
        fail("sample_addresses.csv contains duplicate address_id values")
    return ids


def check_lookups(address_ids: list[str]) -> dict[str, Any]:
    payload = read_json(ROOT / "lookups.json")
    if not isinstance(payload, dict) or not isinstance(payload.get("lookups"), dict):
        fail("lookups.json must contain an object with a 'lookups' object")
    lookups = payload["lookups"]
    if set(lookups) != set(address_ids):
        missing = sorted(set(address_ids) - set(lookups))
        extra = sorted(set(lookups) - set(address_ids))
        fail(f"lookups.json address coverage mismatch; missing={missing[:5]}, extra={extra[:5]}")
    for address_id, entries in lookups.items():
        if not isinstance(entries, list):
            fail(f"lookups[{address_id}] must be a list")
        for entry in entries:
            if entry.get("result") not in ALLOWED_RESULTS:
                fail(f"lookups[{address_id}] has invalid result: {entry.get('result')!r}")
    return payload


def check_changes() -> dict[str, Any]:
    payload = read_json(ROOT / "changes.json")
    if not isinstance(payload, dict) or set(payload) != EXPECTED_TESTS:
        fail(f"changes.json must contain exactly T1-T5; found {sorted(payload) if isinstance(payload, dict) else type(payload).__name__}")
    for test_id in sorted(EXPECTED_TESTS):
        entry = payload[test_id]
        if not isinstance(entry, dict):
            fail(f"changes[{test_id}] must be an object")
        for field in ("affected_address_ids", "conflict_flag_address_ids"):
            if not isinstance(entry.get(field), list):
                fail(f"changes[{test_id}] missing list field {field}")
    return payload


def recomputed_changes(rules: list[dict[str, Any]]) -> dict[str, Any]:
    addresses = geo.load_addresses(ROOT / "starter_pack" / "data" / "sample_addresses.csv")
    # The same offline fallback used by the app when geo_cache.json is absent.
    for address in addresses:
        address["legal_city"] = geo.normalize_legal_city(address.get("postal_city"), address.get("state"))
    return changes.run_change_tests(rules, addresses, ROOT / "starter_pack" / "dev" / "change_tests.json")


def main() -> int:
    rules = load_rules()
    address_ids = load_address_ids()
    submitted_lookups = check_lookups(address_ids)
    submitted_changes = check_changes()
    expected_changes = recomputed_changes(rules)

    for test_id in sorted(EXPECTED_TESTS):
        for field in ("affected_address_ids", "conflict_flag_address_ids"):
            submitted = sorted(submitted_changes[test_id][field])
            expected = sorted(expected_changes[test_id][field])
            if submitted != expected:
                fail(
                    f"changes[{test_id}].{field} does not match a fresh T1-T5 run "
                    f"(submitted={len(submitted)}, expected={len(expected)}; "
                    f"mapping={expected_changes[test_id]['notes'].get('mapped_rule_ids', {})})"
                )

    for test_id in ("T1", "T2", "T3", "T4"):
        if not expected_changes[test_id]["affected_address_ids"]:
            fail(f"{test_id} produced an empty affected set; review rule-ID mapping and extraction")
    if expected_changes["T5"]["affected_address_ids"]:
        fail("T5 must have an empty affected set")
    if not expected_changes["T3"]["conflict_flag_address_ids"]:
        fail("T3 produced no conflict flags for Hoboken/Jersey City")

    print(f"PASS: {len(rules)} schema-valid rules")
    print(f"PASS: {len(submitted_lookups['lookups'])}/500 address lookups")
    print("PASS: lookups.json uses only allowed result values")
    for test_id in ("T1", "T2", "T3", "T4", "T5"):
        entry = expected_changes[test_id]
        print(
            f"PASS: {test_id} affected={len(entry['affected_address_ids'])} "
            f"conflicts={len(entry['conflict_flag_address_ids'])}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
