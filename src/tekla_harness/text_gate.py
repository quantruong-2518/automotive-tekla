"""text_gate: may a reader take meaning from one text-index entry? (legacy-font gate, EVAL-1 fix 2).

Text whose encoding is not known is kept as stored (extract_text.py): a TCVN3 or VNI string then reads as
mojibake, and an approved knowledge row is the only way to decode it (ADR-0006 layer 2). Until the
engineer approves that row, nothing may be concluded from such text: no sheet class, no note value, no
question wording that paraphrases it. Quoting it verbatim, with its entry id, stays allowed.

Rule, on one full text-index entry (schemas/text-index.schema.json `entry`):

  * flag `legacy_ascii_suspect` -> "legacy_ascii_suspect" (tool wave 2, fix 2b): extract_text sets it on a
    pure-ASCII entry of a legacy-font style whose text has a shape legacy Vietnamese takes when written in
    ASCII ('4/g14', 'chi tiESt'); see `extract_text.looks_legacy_ascii`.
  * otherwise `raw_text` is pure ASCII -> allowed. Legacy Vietnamese encodings keep ASCII as ASCII (capital
    fonts may change letter case: `decode.case_uncertain` says so, and callers compare case-insensitively).
    `%%c`, `%%d`, `%%p` are ASCII in `raw_text`, so `%%c16` passes.
  * otherwise blocked when any of these holds, first match is the reason:
      - flag `knowledge_conflict`            -> "knowledge_conflict"
      - flag `proposed_knowledge_row`        -> "encoding_proposed"
      - flag `unicode_evidence_contradicts_font` -> "encoding_contradiction"
      - `decode.encoding_used` is `unknown`, or `mixed` with an `unknown` run -> "encoding_unknown", unless
        the flag `unicode_by_font_evidence` is set (tool wave 4, V2): extract_text sets it when every
        unknown run sits in a TrueType file that another entry proved Unicode by its code points, and the
        unknown runs hold only ASCII and Latin-1 Vietnamese letters; the font, not the string, is the evidence
  * else allowed (Unicode, or TCVN3/VNI decided by font name, code-point evidence or an approved row).

The reason strings are part of the reader tools' output contract (sheet-text, reader-findings, marks).
"""

from __future__ import annotations

from typing import Any

BLOCK_REASONS = (
    "knowledge_conflict",
    "encoding_proposed",
    "encoding_contradiction",
    "encoding_unknown",
    "legacy_ascii_suspect",
)
_FLAG_REASONS = (
    ("knowledge_conflict", "knowledge_conflict"),
    ("proposed_knowledge_row", "encoding_proposed"),
    ("unicode_evidence_contradicts_font", "encoding_contradiction"),
)


def meaning_block_reason(entry: dict[str, Any]) -> str | None:
    """None when meaning may be taken from the entry, else one of BLOCK_REASONS."""
    flags = set(entry.get("flags") or ())
    if "legacy_ascii_suspect" in flags:
        return "legacy_ascii_suspect"
    if str(entry.get("raw_text", "")).isascii():
        return None
    for flag, reason in _FLAG_REASONS:
        if flag in flags:
            return reason
    decode = entry.get("decode") or {}
    encoding = decode.get("encoding_used")
    unknown = encoding == "unknown" or (
        encoding == "mixed" and any(r.get("encoding") == "unknown" for r in decode.get("run_details") or ())
    )
    if unknown and "unicode_by_font_evidence" not in flags:
        return "encoding_unknown"
    return None


def meaning_allowed(entry: dict[str, Any]) -> bool:
    return meaning_block_reason(entry) is None
