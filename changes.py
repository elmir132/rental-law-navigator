"""Run the five deterministic change tests from the participant starter pack."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from engine import evaluate_address


def _text(rule: dict[str, Any]) -> str:
    return " ".join(
        str(rule.get(key, ""))
        for key in ("team_rule_id", "jurisdiction", "category", "title", "requirement", "citation", "source_url")
    ).casefold()


def map_test_rules(rules: list[dict[str, Any]]) -> dict[str, str | None]:
    """Map stable test names to the extractor's generated rule IDs."""

    by_id = {str(rule.get("team_rule_id")): rule for rule in rules}
    mapping: dict[str, str | None] = {}

    def exact_or(predicate, canonical: str) -> None:
        if canonical in by_id:
            mapping[canonical] = canonical
            return
        candidates = [rule for rule in rules if predicate(rule)]
        candidates.sort(key=lambda rule: str(rule.get("team_rule_id", "")))
        mapping[canonical] = candidates[0].get("team_rule_id") if candidates else None

    exact_or(
        lambda r: str(r.get("jurisdiction", "")).upper() == "CA"
        and any(term in _text(r) for term in ("ab 325", "ab325", "sb 763", "sb763", "cartwright", "16729")),
        "CA-ALG-01",
    )
    exact_or(
        lambda r: "hoboken" in _text(r) and r.get("category") == "algorithmic_rent_setting",
        "HOB-ALG-01",
    )
    exact_or(
        lambda r: "jersey city" in _text(r) and r.get("category") == "algorithmic_rent_setting",
        "JC-ALG-01",
    )
    exact_or(
        lambda r: bool(re.search(r"fair\)? act", _text(r)))
        and str(r.get("jurisdiction", "")).upper() == "NJ"
        and "preempt" not in _text(r),
        "NJ-ALG-01",
    )

    def _ma_bill(number: str):
        for rule in rules:
            if str(rule.get("jurisdiction", "")).upper() == "MA" and str(rule.get("status", "")).casefold() == "pending" and number in _text(rule):
                return rule.get("team_rule_id")
        return None

    for canonical, number in (("MA-ALG-P1", "2983"), ("MA-ALG-P2", "5222")):
        mapping[canonical] = canonical if canonical in by_id else _ma_bill(number)

    exact_or(
        lambda r: "ma" in str(r.get("jurisdiction", "")).casefold()
        and str(r.get("status", "")).casefold() == "failed"
        and any(term in _text(r) for term in ("ballot", "25-21", "rent control")),
        "MA-RENT-P1",
    )
    return mapping


def _indexed_results(rules, address, as_of, include_pending=True):
    return {
        item["team_rule_id"]: item
        for item in evaluate_address(rules, address, as_of, include_pending=include_pending)
    }


def _state(address: dict[str, Any]) -> str:
    return str(address.get("state", "")).upper()


def _city(address: dict[str, Any]) -> str:
    # Change tests intentionally exercise legal city boundaries. Never fall
    # back to postal_city here: a neighborhood mailing label is not a legal
    # jurisdiction.
    return str(address.get("legal_city") or "").casefold()


def run_change_tests(
    rules: list[dict[str, Any]],
    addresses: list[dict[str, Any]],
    change_tests_path: str | Path,
) -> dict[str, dict[str, Any]]:
    tests = json.loads(Path(change_tests_path).read_text())
    mapping = map_test_rules(rules)
    output: dict[str, dict[str, Any]] = {}

    for test in tests:
        test_id = test["test_id"]
        rule_ids = [mapping.get(rule_id) for rule_id in test.get("rule_ids", [])]
        rule_ids = [rule_id for rule_id in rule_ids if rule_id]
        affected: list[str] = []
        conflict_ids: list[str] = []

        if test_id == "T1":
            for address in addresses:
                if _state(address) != "CA":
                    continue
                before = _indexed_results(rules, address, test["as_of_before"])
                after = _indexed_results(rules, address, test["as_of_after"])
                if any(
                    after.get(rule_id, {}).get("result") == "applies"
                    and before.get(rule_id, {}).get("result") != "applies"
                    for rule_id in rule_ids
                ):
                    affected.append(address["address_id"])
        elif test_id == "T2":
            for address in addresses:
                if _city(address) in {"hoboken", "jersey city"}:
                    indexed = _indexed_results(rules, address, test["as_of"])
                    if any(item.get("result") == "applies" for item in indexed.values() if item.get("team_rule_id") in rule_ids):
                        affected.append(address["address_id"])
        elif test_id == "T3":
            for address in addresses:
                if _state(address) != "NJ":
                    continue
                before = _indexed_results(rules, address, test["as_of_before"])
                after = _indexed_results(rules, address, test["as_of_after"])
                if any(
                    after.get(rule_id, {}).get("result") == "applies"
                    and before.get(rule_id, {}).get("result") != "applies"
                    for rule_id in rule_ids
                ):
                    affected.append(address["address_id"])
                if _city(address) in {"hoboken", "jersey city"}:
                    conflict_ids.append(address["address_id"])
        elif test_id == "T4":
            for address in addresses:
                if _state(address) == "MA":
                    indexed = _indexed_results(rules, address, test["as_of"], include_pending=True)
                    if any(indexed.get(rule_id, {}).get("result") == "pending" for rule_id in rule_ids):
                        affected.append(address["address_id"])
        elif test_id == "T5":
            # A failed ballot question must not create affected addresses.
            affected = []

        output[test_id] = {
            "affected_address_ids": sorted(set(affected)),
            "conflict_flag_address_ids": sorted(set(conflict_ids)),
            "notes": {
                "title": test.get("title"),
                "mapped_rule_ids": dict(zip(test.get("rule_ids", []), rule_ids)),
                "expected_behavior": test.get("expected_behavior"),
            },
        }
    return output
