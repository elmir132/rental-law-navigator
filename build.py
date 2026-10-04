"""Build the three submission JSON files from extracted rules and starter data."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import changes
import engine
import geo


ROOT = Path(__file__).resolve().parent
STARTER = ROOT / "starter_pack"


def _load_addresses(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def build_outputs(
    *,
    rules_path: Path = ROOT / "rules.json",
    as_of: str = "2026-10-01",
    offline: bool = False,
    force_geo: bool = False,
) -> None:
    if not rules_path.exists():
        raise FileNotFoundError(
            f"{rules_path} does not exist. Run the extraction assistant first, then rerun build.py."
        )
    rules = engine.load_rules(rules_path)
    addresses = _load_addresses(STARTER / "data" / "sample_addresses.csv")
    geo_records = geo.geocode_csv(
        STARTER / "data" / "sample_addresses.csv",
        ROOT / "geo_cache.json",
        force=force_geo,
        offline=offline,
    )
    # Preserve parcel facts from the supplied CSV while adding geocoder output.
    by_id = {row["address_id"]: row for row in addresses}
    for record in geo_records:
        original = by_id.get(record.get("address_id"), {})
        record.update({key: value for key, value in original.items() if value not in (None, "")})
    lookups = engine.lookup_all(rules, geo_records, as_of)
    changes_result = changes.run_change_tests(rules, geo_records, STARTER / "dev" / "change_tests.json")
    _write_json(ROOT / "lookups.json", lookups)
    _write_json(ROOT / "changes.json", changes_result)
    print(f"Built {len(rules)} rules, {len(lookups['lookups'])} address lookups, and {len(changes_result)} change tests.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", type=Path, default=ROOT / "rules.json")
    parser.add_argument("--as-of", default="2026-10-01")
    parser.add_argument("--offline", action="store_true", help="Use city aliases instead of calling Census")
    parser.add_argument("--force-geo", action="store_true")
    args = parser.parse_args()
    build_outputs(rules_path=args.rules, as_of=args.as_of, offline=args.offline, force_geo=args.force_geo)


if __name__ == "__main__":
    main()

