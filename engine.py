"""Deterministic rule coverage engine.

The extractor supplies the legal content. This module only evaluates the
validated records against address facts and dates, and returns conservative
``unknown`` results when a required fact is absent.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any


RESULTS = {"applies", "unknown", "superseded", "not_yet_effective", "pending"}


def load_rules(path: str | Path) -> list[dict[str, Any]]:
    payload = __import__("json").loads(Path(path).read_text())
    if isinstance(payload, dict):
        payload = payload.get("rules", [])
    if not isinstance(payload, list):
        raise ValueError("rules.json must contain a list or an object with a 'rules' list")
    return payload


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    match = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$", str(value).strip())
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    day = int(match.group(3) or 1)
    return date(year, month, day)


def _value(address: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = address.get(name)
        if value not in (None, ""):
            return value
    return None


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _jurisdiction_matches(rule: dict[str, Any], address: dict[str, Any]) -> bool:
    jurisdiction = str(rule.get("jurisdiction", "")).strip()
    state = str(_value(address, "state", "state_code") or "").strip().upper()
    legal_city = str(_value(address, "legal_city", "city") or "").strip().casefold()
    if re.fullmatch(r"[A-Za-z]{2}", jurisdiction):
        return state == jurisdiction.upper()
    if "," in jurisdiction:
        city, rule_state = [part.strip() for part in jurisdiction.split(",", 1)]
        return state == rule_state.upper() and legal_city == city.casefold()
    return legal_city == jurisdiction.casefold()


def _compare(value: float | None, operator: str, target: float) -> bool | None:
    if value is None:
        return None
    return {
        "<": value < target,
        "<=": value <= target,
        ">": value > target,
        ">=": value >= target,
        "=": value == target,
    }[operator]


def _condition_string(text: str, address: dict[str, Any]) -> tuple[bool | None, str | None]:
    lowered = text.casefold()
    year = _number(_value(address, "year_built"))
    units = _number(_value(address, "units", "unit_count"))

    # Year-built facts are only a proxy for certificate dates. Treat the
    # cutoff year itself as unknown, as required by the participant guide.
    year_cutoff = re.search(
        r"(?:built|construction|certificate(?: of occupancy)?)?[^\d]{0,45}"
        r"(?:on or before|before|by|<=)\s*(19\d{2}|20\d{2})",
        lowered,
    )
    if year_cutoff:
        cutoff = float(year_cutoff.group(1))
        if year is None:
            return None, "year built or certificate date is missing"
        if year == cutoff:
            return None, "the record is in the cutoff year and certificate date is unavailable"
        return year < cutoff, None

    unit_condition = re.search(
        r"(?:at least|more than|over|minimum of|>=)\s*(\d+(?:\.\d+)?)\s*units?",
        lowered,
    )
    if unit_condition:
        result = _compare(units, ">=" if "at least" in unit_condition.group(0) or "minimum" in unit_condition.group(0) else ">", float(unit_condition.group(1)))
        return result, "unit count is missing" if result is None else None
    unit_condition = re.search(
        r"(?:fewer than|less than|under|no more than|<=)\s*(\d+(?:\.\d+)?)\s*units?",
        lowered,
    )
    if unit_condition:
        result = _compare(units, "<=" if "no more" in unit_condition.group(0) else "<", float(unit_condition.group(1)))
        return result, "unit count is missing" if result is None else None

    if any(term in lowered for term in ("owner-occupied", "owner occupied", "owner type", "small landlord", "owner-owned")):
        if _value(address, "owner_type") is None:
            return None, "owner type is not in the supplied data"

    if "certificate of occupancy" in lowered and year is None:
        return None, "certificate date is not in the supplied data"

    # Unparsed exemptions/coverage conditions are not silently treated as
    # universal. This keeps extraction mistakes visible in the demo.
    if any(term in lowered for term in ("unless", "exempt", "covered", "only if", "applies to")):
        return None, "coverage condition requires review against unavailable facts"
    return True, None


def _condition_object(value: Any, address: dict[str, Any]) -> tuple[bool | None, str | None]:
    if value is None or value == "":
        return True, None
    if isinstance(value, str):
        return _condition_string(value, address)
    if isinstance(value, list):
        states = [_condition_object(item, address) for item in value]
        if any(state is False for state, _ in states):
            return False, None
        if any(state is None for state, _ in states):
            return None, next(note for state, note in states if state is None and note)
        return True, None
    if not isinstance(value, dict):
        return True, None

    if "all" in value:
        return _condition_object(value["all"], address)
    if "any" in value:
        states = [_condition_object(item, address) for item in value["any"]]
        if any(state is True for state, _ in states):
            return True, None
        if any(state is None for state, _ in states):
            return None, "one of the alternative coverage conditions is unknown"
        return False, None

    checks: list[tuple[bool | None, str | None]] = []
    for key, expected in value.items():
        normalized = key.casefold()
        if normalized in {"description", "notes", "text", "requires"}:
            checks.append(_condition_object(expected, address))
            continue
        if normalized in {"year_built_before", "year_before", "built_before"}:
            actual = _number(_value(address, "year_built"))
            checks.append((_compare(actual, "<", float(expected)), "year built is missing" if actual is None else None))
        elif normalized in {"year_built_on_or_before", "built_on_or_before"}:
            actual = _number(_value(address, "year_built"))
            if actual is None or actual == float(expected):
                checks.append((None, "year built or certificate date is unavailable"))
            else:
                checks.append((actual < float(expected), None))
        elif normalized in {"min_units", "units_min", "minimum_units"}:
            actual = _number(_value(address, "units", "unit_count"))
            checks.append((_compare(actual, ">=", float(expected)), "unit count is missing" if actual is None else None))
        elif normalized in {"max_units", "units_max", "maximum_units"}:
            actual = _number(_value(address, "units", "unit_count"))
            checks.append((_compare(actual, "<=", float(expected)), "unit count is missing" if actual is None else None))
        elif normalized in {"owner_type", "owner_types"}:
            actual = _value(address, "owner_type")
            checks.append((None, "owner type is not in the supplied data") if actual is None else (str(actual) in expected if isinstance(expected, list) else str(actual) == str(expected), None))
        else:
            checks.append(_condition_string(f"{key}: {expected}", address))
    if any(state is False for state, _ in checks):
        return False, None
    if any(state is None for state, _ in checks):
        return None, next(note for state, note in checks if state is None and note)
    return True, None


def _status_result(rule: dict[str, Any], as_of: date, include_pending: bool) -> str | None:
    status = str(rule.get("status", "in_force")).strip().casefold()
    if status == "failed":
        return None
    if status == "pending":
        return "pending" if include_pending else None
    effective = _as_date(rule.get("effective_date"))
    # A rule record may describe its status at the default date, while a
    # change test asks for a later date. Its effective date wins once reached.
    if (effective and effective > as_of) or (status == "not_yet_effective" and effective is None):
        return "not_yet_effective"
    return "in_force"


def evaluate_rule(
    rule: dict[str, Any],
    address: dict[str, Any],
    as_of: str | date = date(2026, 10, 1),
    *,
    include_pending: bool = True,
) -> dict[str, Any] | None:
    query_date = _as_date(as_of) if not isinstance(as_of, date) else as_of
    if query_date is None or not _jurisdiction_matches(rule, address):
        return None
    status = _status_result(rule, query_date, include_pending)
    if status is None:
        return None
    condition, note = _condition_object(rule.get("coverage_conditions"), address)
    if condition is False:
        return None
    result = status if status != "in_force" else ("unknown" if condition is None else "applies")
    requirement = str(rule.get("requirement", "")).strip()
    explanation = requirement or str(rule.get("title", "Rule"))
    if condition is None and note:
        explanation = f"Unknown: {note}. {explanation}"
    if status == "not_yet_effective":
        explanation = f"Not yet effective as of {query_date.isoformat()}. {explanation}"
    if status == "pending":
        explanation = f"Pending, not in force as of {query_date.isoformat()}. {explanation}"
    return {
        "team_rule_id": rule.get("team_rule_id"),
        "result": result,
        "explanation": explanation,
        "conflict_flag": bool(rule.get("conflict_flag", False)),
        "conflict_note": rule.get("conflict_note"),
        "category": rule.get("category"),
        "title": rule.get("title"),
        "citation": rule.get("citation"),
        "source_doc_id": rule.get("source_doc_id"),
        "source_url": rule.get("source_url"),
        "quoted_span": rule.get("quoted_span"),
        "retrieved_at": rule.get("retrieved_at"),
    }


def evaluate_address(
    rules: list[dict[str, Any]],
    address: dict[str, Any],
    as_of: str | date = date(2026, 10, 1),
    *,
    include_pending: bool = True,
) -> list[dict[str, Any]]:
    results = [
        evaluated
        for rule in rules
        if (evaluated := evaluate_rule(rule, address, as_of, include_pending=include_pending))
    ]
    result_by_id = {item["team_rule_id"]: item for item in results}
    for rule in rules:
        rule_id = rule.get("team_rule_id")
        if rule_id not in result_by_id:
            continue
        for overridden_id in rule.get("overrides") or []:
            overridden = result_by_id.get(overridden_id)
            if overridden and overridden["result"] == "applies":
                overridden["result"] = "superseded"
                overridden["explanation"] = f"Superseded by {rule_id}. {overridden['explanation']}"
    return results


def lookup_all(
    rules: list[dict[str, Any]],
    addresses: list[dict[str, Any]],
    as_of: str = "2026-10-01",
    *,
    include_pending: bool = True,
) -> dict[str, Any]:
    output: dict[str, list[dict[str, Any]]] = {}
    for address in addresses:
        address_id = address.get("address_id")
        output[address_id] = [
            {
                "team_rule_id": item["team_rule_id"],
                "result": item["result"],
                "explanation": item["explanation"],
                "conflict_flag": item["conflict_flag"],
            }
            for item in evaluate_address(rules, address, as_of, include_pending=include_pending)
        ]
    return {"as_of": as_of, "lookups": output}
