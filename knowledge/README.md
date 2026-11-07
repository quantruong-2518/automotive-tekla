# knowledge/

Approved knowledge tables (ADR-0006, layer 2). Plain CSV, versioned in git, reviewed like code.
Only anonymised rules belong here: never drawings, model data or client names.

## Rule

**Only `approved` rows change behaviour.** A `proposed` row changes nothing: it only makes the
harness ask a question that shows the row's evidence. A `rejected` row is kept as memory and does
nothing. Agents never write to these tables; they propose rows in a pull request.

## font-encodings.csv

Which legacy Vietnamese encoding a text style uses, when the font name alone cannot tell.
Consulted only after `encoding.font_hint` returned "unknown": a row never overrides a positive
font-name result. Loaded and validated by `src/tekla_harness/knowledge.py`; a malformed table is an
error (exit 1), never ignored.

| Column | Meaning |
|---|---|
| `pattern` | Case-insensitive glob (`*`, `?`, `[...]`). No leading or trailing spaces. |
| `applies_to` | `style_name`: matched against the text style name. `font_file`: matched against the file name of the style's font (folders are ignored). |
| `encoding` | `tcvn3`, `vni` or `unicode`. |
| `capital_font` | `true` or `false` (TCVN3 rows only), or blank = unknown. Only fills a gap: the style-name hint from `font_hint` wins. |
| `status` | `proposed`, `approved` or `rejected`. |
| `evidence` | What was observed, with counts. No drawing text beyond what a reviewer needs. |
| `source` | Where the evidence comes from (sample, project, document). |
| `decided_by`, `decided_on` | Who decided and when (`YYYY-MM-DD`). Blank for `proposed`; required for `approved` and `rejected`. |

Two approved rows that match one style with different encodings are a conflict: the style stays
"unknown", its entries are flagged `knowledge_conflict` and nothing is decoded.

## Approving a row

The engineer reads the evidence (shown in the `font_encoding_proposed` question of the intake run,
or in the CSV), then edits the row in a reviewed commit: set `status` to `approved` (or `rejected`),
and fill `decided_by` and `decided_on`. Engineer answers to intake questions become rows the same way.
The tests validate the file, so a half-edited row fails CI.
