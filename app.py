"""Streamlit demo for address-level housing-law lookups."""

from __future__ import annotations

import csv
import html
import os
from datetime import date
from pathlib import Path

import engine
import geo


ROOT = Path(__file__).resolve().parent


def _optional_gemini_key(st) -> str | None:
    """Read the optional key without requiring local or Streamlit secrets."""

    try:
        secret = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        secret = None
    return secret or os.getenv("GEMINI_API_KEY")


def _read_addresses() -> list[dict]:
    with (ROOT / "starter_pack" / "data" / "sample_addresses.csv").open(newline="") as handle:
        return list(csv.DictReader(handle))


def _read_retrieval_dates() -> dict[str, str]:
    corpus = ROOT / "starter_pack" / "corpus"
    dates: dict[str, str] = {}
    with (corpus / "corpus_manifest.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            doc_id = row.get("doc_id")
            if not doc_id:
                continue
            if row.get("retrieved_at"):
                dates[doc_id] = row["retrieved_at"]
                continue
            # Fall back to the RETRIEVED header of a saved text copy, if there is one.
            text_file = corpus / "text" / f"{doc_id}.txt"
            if text_file.exists():
                for line in text_file.read_text(errors="ignore").splitlines()[:4]:
                    if line.startswith("RETRIEVED:"):
                        dates[doc_id] = line.split(":", 1)[1].strip()
                        break
    return dates


def _run() -> None:
    import streamlit as st

    st.set_page_config(page_title="Rental Housing Law Navigator", page_icon="🏠", layout="wide")
    st.title("Rental Housing Law Navigator")
    st.caption("Address-level rule lookup with citations and an explicit uncertainty boundary.")
    st.warning("Not legal advice. This prototype explains supplied public sources and is not a compliance certification.")
    if _optional_gemini_key(st):
        st.sidebar.caption("Optional Gemini key detected in Streamlit secrets.")
    else:
        st.sidebar.caption("Deterministic cited lookup. No API key required.")

    rules_path = ROOT / "rules.json"
    if not rules_path.exists():
        st.error("rules.json is not available yet. Run the automated extraction pipeline first.")
        st.stop()
    rules = engine.load_rules(rules_path)
    addresses = _read_addresses()
    retrieval_dates = _read_retrieval_dates()
    address_by_id = {row["address_id"]: row for row in addresses}

    with st.sidebar:
        st.header("Lookup")
        mode = st.radio("Address source", ["Starter address", "Enter an address"], index=0)
        as_of = st.date_input("As of date", value=date(2026, 10, 1))
        include_pending = st.toggle("Show pending laws", value=True)
        topic_labels = {
            "algorithmic_rent_setting": "Algorithmic rent setting (e.g. RealPage)",
            "application_screening_fees": "Application and screening fees",
            "just_cause_eviction": "Eviction and just cause",
            "rent_increase_limits": "Rent increases and rent control",
            "screening_restrictions": "Tenant screening (criminal history, income, credit)",
            "security_deposits": "Security deposits",
        }
        category = st.selectbox(
            "Topic",
            ["All topics"] + sorted({str(rule.get("category", "")) for rule in rules}),
            format_func=lambda value: topic_labels.get(value, value.replace("_", " ").capitalize()),
        )
        st.caption("Unknown means the supplied data is insufficient to decide coverage; the app does not guess.")

    if mode == "Starter address":
        chosen = st.selectbox(
            "Sample address",
            list(address_by_id),
            format_func=lambda key: f"{key} · {address_by_id[key].get('street_address')} · {address_by_id[key].get('postal_city')}",
        )
        address = dict(address_by_id[chosen])
        address["legal_city"] = geo.normalize_legal_city(address.get("postal_city"), address.get("state"))
        cached = ROOT / "geo_cache.json"
        if cached.exists():
            try:
                records = __import__("json").loads(cached.read_text()).get("records", [])
                address.update(next((item for item in records if item.get("address_id") == chosen), {}))
            except (OSError, ValueError):
                pass
    else:
        street = st.text_input("Street address", placeholder="4600 Silver Hill Rd")
        city = st.text_input("City", placeholder="Washington")
        state = st.text_input("State", value="CA", max_chars=2)
        zip_code = st.text_input("ZIP code")
        if not street or not city or not state:
            st.info("Enter a street, city, and state to run a lookup.")
            st.stop()
        try:
            address = geo.geocode_one(street, city, state.upper(), zip_code)
        except Exception as exc:  # UI should display a useful error, not a traceback.
            # The demo must still run from a clean Streamlit checkout without
            # geo_cache.json or a live Census response.
            st.info(f"Census geocoding unavailable; using the offline city fallback ({exc}).")
            address = {
                "street_address": street,
                "postal_city": city,
                "state": state.upper(),
                "zip": zip_code,
                "legal_city": geo.normalize_legal_city(city, state.upper()),
                "year_built": None,
                "units": None,
                "geocode_source": "offline_city_fallback",
            }

    street_line = html.escape(str(address.get("street_address") or "Address not entered"))
    place_line = html.escape(
        " ".join(
            part
            for part in (
                f"{address.get('postal_city') or ''},".strip(","),
                str(address.get("state") or ""),
                str(address.get("zip") or ""),
            )
            if part
        )
    )
    facts = []
    if address.get("year_built"):
        facts.append(f"built {html.escape(str(address['year_built']))}")
    if address.get("units"):
        facts.append(f"{html.escape(str(address['units']))} units")
    facts_line = " · ".join(facts) if facts else "year built and unit count not in the supplied data"
    st.markdown(
        f"""
        <div style="padding:14px 18px;border-radius:10px;background:#e8f0fe;border-left:6px solid #1a56db;margin:10px 0 6px 0;">
          <div style="font-size:0.75rem;letter-spacing:0.06em;color:#3b4a66;font-weight:600;">SELECTED ADDRESS</div>
          <div style="font-size:1.5rem;font-weight:700;color:#0b1b3a;line-height:1.25;">{street_line}</div>
          <div style="font-size:1rem;color:#1f2d4d;">{place_line} · {facts_line}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write(
        f"**Jurisdiction stack:** {address.get('state', 'unknown')}"
        f" → {address.get('legal_city') or 'unknown legal city'}"
    )
    st.caption(f"Lookup as of {as_of.isoformat()} · address facts are from the supplied public sample where available.")
    results = engine.evaluate_address(rules, address, as_of, include_pending=include_pending)
    if category != "All topics":
        results = [item for item in results if item.get("category") == category]
    if not results:
        st.info("No supplied rule matched this jurisdiction and topic on the selected date.")
        return

    counts: dict[str, int] = {}
    for item in results:
        counts[item["result"]] = counts.get(item["result"], 0) + 1
    chips = [
        ("applies", "Applies", True),
        ("unknown", "Unknown", True),
        ("superseded", "Superseded", True),
        ("pending", "Pending", True),
        ("not_yet_effective", "Not yet effective", False),
    ]
    labels = {f"{label}: {counts.get(key, 0)}": key for key, label, always in chips if always or counts.get(key)}
    st.caption("Click a result type to filter. Click several to combine them, click again to remove one.")
    picked = st.pills(
        "Filter by result",
        list(labels),
        selection_mode="multi",
        default=None,
        label_visibility="collapsed",
        key="result_filter",
    )
    wanted = {labels[label] for label in (picked or []) if label in labels}
    # Counts change with the address, so labels change; drop any stale selection safely.
    shown = [item for item in results if not wanted or item["result"] in wanted]
    st.markdown(
        f'<div style="color:#64748b;font-size:0.9rem;margin:2px 0 8px 0;">{len(shown)} of {len(results)} rules shown. '
        f"Expand a card to read the quoted source text.</div>",
        unsafe_allow_html=True,
    )
    results = shown
    if not results:
        st.info("No rules of that type for this address.")
        return

    for position, item in enumerate(results):
        status = item["result"].replace("_", " ").title()
        with st.container(border=True):
            st.subheader(item.get("title") or item["team_rule_id"])
            st.markdown(f"**Result:** `{status}`")
            if item["result"] == "unknown":
                st.info("Unknown: a required coverage fact is missing from the supplied data.")
            if item.get("conflict_flag"):
                st.warning("Conflict flag: possible overlap with another law. Needs human review.")
            st.write(item["explanation"])
            retrieved_at = item.get("retrieved_at") or retrieval_dates.get(item.get("source_doc_id"))
            st.caption(
                f"Citation: {item.get('citation') or 'not supplied'} · "
                f"Source document: {item.get('source_doc_id') or 'not supplied'} · "
                f"Retrieved: {retrieved_at or 'not supplied'}"
            )
            with st.expander("Quoted source text", expanded=(position == 0)):
                st.write(item.get("quoted_span") or "No quoted span was supplied.")
                if item.get("source_url"):
                    st.markdown(f"[Open source]({item['source_url']})")


if __name__ == "__main__":
    _run()
