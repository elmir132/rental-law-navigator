"""Verify that every extracted quote really appears in its source document.

A rule whose quoted_span cannot be found (exactly, or almost exactly) in the
cited corpus text is rejected. Near matches are replaced by the real text from
the document, so every quote in rules.json is a verbatim slice of the source.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

TEXT_DIR = Path(__file__).resolve().parent / "starter_pack" / "corpus" / "text"
MIN_RATIO = 0.90

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def _norm_with_map(text: str) -> tuple[str, list[int]]:
    """Lowercase, collapse whitespace, and map each normalized char to its original index."""
    out: list[str] = []
    index: list[int] = []
    previous_space = True
    for i, ch in enumerate(text.translate(_QUOTES)):
        if ch.isspace():
            if previous_space:
                continue
            out.append(" ")
            index.append(i)
            previous_space = True
        else:
            out.append(ch.lower())
            index.append(i)
            previous_space = False
    return "".join(out).strip(), index


def load_doc(doc_id: str) -> str:
    path = TEXT_DIR / f"{doc_id}.txt"
    return path.read_text(errors="ignore") if path.exists() else ""


def find_span(quote: str, doc_text: str) -> tuple[str | None, float]:
    """Return (verbatim slice of doc_text, similarity) or (None, 0.0)."""
    if not quote or not doc_text:
        return None, 0.0
    norm_doc, mapping = _norm_with_map(doc_text)
    norm_quote, _ = _norm_with_map(quote)
    if len(norm_quote) < 12:
        return None, 0.0

    pos = norm_doc.find(norm_quote)
    if pos >= 0:
        start, end = mapping[pos], mapping[min(pos + len(norm_quote), len(mapping)) - 1] + 1
        return re.sub(r"\s+", " ", doc_text[start:end]).strip(), 1.0

    # Near match: locate the quote's opening words, then compare a same-length window.
    probe = norm_quote[: min(40, len(norm_quote))]
    best: tuple[float, int] = (0.0, -1)
    start_at = 0
    while True:
        hit = norm_doc.find(probe, start_at)
        if hit < 0:
            break
        window = norm_doc[hit : hit + len(norm_quote) + 20]
        ratio = difflib.SequenceMatcher(None, norm_quote, window[: len(norm_quote)], autojunk=False).ratio()
        if ratio > best[0]:
            best = (ratio, hit)
        start_at = hit + 1
    if best[1] >= 0 and best[0] >= MIN_RATIO:
        hit = best[1]
        end_norm = min(hit + len(norm_quote), len(mapping)) - 1
        start, end = mapping[hit], mapping[end_norm] + 1
        return re.sub(r"\s+", " ", doc_text[start:end]).strip(), best[0]
    return None, best[0]


def verify_rule(rule: dict) -> tuple[bool, dict]:
    """Check one rule against its source doc. Returns (kept, audit_entry)."""
    doc_id = str(rule.get("source_doc_id", ""))
    verbatim, ratio = find_span(str(rule.get("quoted_span", "")), load_doc(doc_id))
    entry = {
        "team_rule_id": rule.get("team_rule_id"),
        "source_doc_id": doc_id,
        "match_ratio": round(ratio, 3),
        "verdict": "verified_exact" if ratio == 1.0 else ("repaired_near_match" if verbatim else "rejected_quote_not_in_source"),
    }
    if verbatim:
        rule["quoted_span"] = verbatim
        return True, entry
    return False, entry
