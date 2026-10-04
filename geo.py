"""Census geocoding and legal-city normalization for the starter address set."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any, Iterable

import requests


CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/geographies/addressbatch"
CENSUS_SINGLE_URL = "https://geocoding.geo.census.gov/geocoder/geographies/address"
DEFAULT_BENCHMARK = "Public_AR_Current"
DEFAULT_VINTAGE = "Current_Current"

# The sample deliberately uses mailing neighborhoods in a few rows. These are
# legal-city aliases, not new jurisdictions.
CITY_ALIASES = {
    "dorchester": "Boston",
    "roxbury": "Boston",
    "east boston": "Boston",
    "brighton": "Boston",
    "allston": "Boston",
    "jamaica plain": "Boston",
    "hyde park": "Boston",
    "mattapan": "Boston",
    "south boston": "Boston",
    "san ysidro": "San Diego",
    "van nuys": "Los Angeles",
    "sylmar": "Los Angeles",
    "canoga park": "Los Angeles",
    "north hollywood": "Los Angeles",
    "panorama city": "Los Angeles",
    "reseda": "Los Angeles",
    "winnetka": "Los Angeles",
    "woodland hills": "Los Angeles",
}

KNOWN_CITIES = {
    "los angeles",
    "san francisco",
    "san diego",
    "berkeley",
    "santa ana",
    "jersey city",
    "hoboken",
    "newark",
    "boston",
    "cambridge",
}


def normalize_legal_city(postal_city: str | None, state: str | None = None) -> str | None:
    """Return a legal city when the mailing city is a known neighborhood alias."""

    if not postal_city:
        return None
    key = re.sub(r"\s+", " ", postal_city.strip().casefold())
    if key in CITY_ALIASES:
        return CITY_ALIASES[key]
    if key in KNOWN_CITIES:
        return " ".join(word.capitalize() for word in key.split())
    # Preserve an already-canonical city even if it is outside today's scope;
    # the rule engine will decide whether any rule matches it.
    if state and len(state.strip()) == 2:
        return postal_city.strip().title()
    return postal_city.strip().title()


def _source_hash(records: Iterable[dict[str, str]]) -> str:
    payload = [
        {
            "address_id": row.get("address_id", ""),
            "street_address": row.get("street_address", ""),
            "postal_city": row.get("postal_city", ""),
            "state": row.get("state", ""),
            "zip": row.get("zip", ""),
        }
        for row in records
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _coordinates(value: str) -> tuple[float | None, float | None]:
    if not value:
        return None, None
    parts = [part.strip() for part in value.split(",")]
    try:
        if len(parts) >= 2:
            # Census batch output uses longitude,latitude in its Coordinates
            # field. Keep the output explicit as latitude/longitude.
            return float(parts[1]), float(parts[0])
    except ValueError:
        pass
    return None, None


def _place_name(geographies: dict[str, Any]) -> str | None:
    for key in ("Incorporated Places", "Places", "Census Places"):
        values = geographies.get(key) or []
        if values:
            return values[0].get("NAME") or values[0].get("BASENAME")
    return None


def _base_result(row: dict[str, str]) -> dict[str, Any]:
    result = dict(row)
    result.update(
        {
            "legal_city": normalize_legal_city(row.get("postal_city"), row.get("state")),
            "county": None,
            "matched_address": None,
            "match": "fallback",
            "latitude": None,
            "longitude": None,
            "geocode_source": "postal_city_normalization",
            "geocode_error": None,
        }
    )
    return result


def _batch_rows(response_text: str) -> dict[str, dict[str, Any]]:
    parsed: dict[str, dict[str, Any]] = {}
    for row in csv.reader(io.StringIO(response_text)):
        if not row:
            continue
        address_id = row[0].strip()
        if not address_id or address_id.casefold() in {"id", "unique id"}:
            continue
        match = row[2].strip() if len(row) > 2 else ""
        matched_address = row[4].strip() if len(row) > 4 else ""
        latitude, longitude = _coordinates(row[5].strip() if len(row) > 5 else "")
        parsed[address_id] = {
            "matched_address": matched_address,
            "match": match or "unknown",
            "latitude": latitude,
            "longitude": longitude,
            "geocode_source": "census_batch",
        }
    return parsed


def batch_geocode(records: list[dict[str, str]], timeout: int = 90) -> list[dict[str, Any]]:
    """Geocode up to 10,000 rows through the Census batch endpoint."""

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    for row in records:
        writer.writerow(
            [
                row.get("address_id", ""),
                row.get("street_address", ""),
                row.get("postal_city", ""),
                row.get("state", ""),
                row.get("zip", ""),
            ]
        )
    response = requests.post(
        CENSUS_BATCH_URL,
        files={"addressFile": ("addresses.csv", buffer.getvalue().encode(), "text/csv")},
        data={"benchmark": DEFAULT_BENCHMARK, "vintage": DEFAULT_VINTAGE},
        timeout=timeout,
    )
    response.raise_for_status()
    parsed = _batch_rows(response.text)

    output = []
    for row in records:
        result = _base_result(row)
        result.update(parsed.get(row.get("address_id", ""), {}))
        result["legal_city"] = normalize_legal_city(row.get("postal_city"), row.get("state"))
        output.append(result)
    return output


def geocode_one(
    street_address: str,
    city: str,
    state: str,
    zip_code: str = "",
    timeout: int = 30,
) -> dict[str, Any]:
    """Resolve one user-entered address, including incorporated place when available."""

    params = {
        "street": street_address,
        "city": city,
        "state": state,
        "zip": zip_code,
        "benchmark": DEFAULT_BENCHMARK,
        "vintage": DEFAULT_VINTAGE,
        "format": "json",
    }
    response = requests.get(CENSUS_SINGLE_URL, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    matches = payload.get("result", {}).get("addressMatches", [])
    result = {
        "street_address": street_address,
        "postal_city": city,
        "state": state,
        "zip": zip_code,
        "year_built": None,
        "units": None,
        "legal_city": normalize_legal_city(city, state),
        "county": None,
        "matched_address": None,
        "match": "no_match",
        "latitude": None,
        "longitude": None,
        "geocode_source": "census_single",
        "geocode_error": None,
    }
    if not matches:
        result["geocode_error"] = "No Census match"
        return result
    match = matches[0]
    address_components = match.get("addressComponents", {})
    coordinates = match.get("coordinates", {})
    geographies = match.get("geographies", {})
    result.update(
        {
            "matched_address": match.get("matchedAddress"),
            "match": "match",
            "latitude": coordinates.get("y"),
            "longitude": coordinates.get("x"),
            "legal_city": _place_name(geographies)
            or normalize_legal_city(city, state)
            or address_components.get("city"),
        }
    )
    counties = geographies.get("Counties") or []
    if counties:
        result["county"] = counties[0].get("NAME")
    return result


def load_addresses(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="") as handle:
        return list(csv.DictReader(handle))


def geocode_csv(
    address_csv: str | Path,
    cache_path: str | Path,
    *,
    force: bool = False,
    offline: bool = False,
) -> list[dict[str, Any]]:
    """Return cached Census results, falling back to deterministic city aliases offline."""

    records = load_addresses(address_csv)
    digest = _source_hash(records)
    cache = Path(cache_path)
    if cache.exists() and not force:
        try:
            payload = json.loads(cache.read_text())
            if payload.get("source_hash") == digest:
                return payload.get("records", [])
        except (OSError, json.JSONDecodeError):
            pass

    if offline:
        results = [_base_result(row) for row in records]
    else:
        try:
            results = batch_geocode(records)
        except requests.RequestException as exc:
            results = [_base_result(row) for row in records]
            for result in results:
                result["geocode_error"] = f"Census batch failed: {exc}"

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"source_hash": digest, "records": results}, indent=2))
    return results

