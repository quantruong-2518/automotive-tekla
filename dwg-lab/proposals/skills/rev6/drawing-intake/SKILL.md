---
name: drawing-intake
description: First pass over a project's drawing files — convert DWG, probe every DXF, log every read, run the extractors, and hand the engineer the first questions in questions.md. Use when a project's input/ folder is new or has changed, or when asked which input files are readable, partial or unreadable, or what the DWG converter did to them.
---


# Drawing intake

You run deterministic commands and hand their questions to the engineer. You interpret nothing
in the drawings here; `structural-drawing-reader` does, once the engineer has answered the units.

Layout: machine artefacts in `projects/<id>/work/`; engineer documents (`questions.md`,
`01-analysis.md`…) in `projects/<id>/`. Below, `W` = `projects/<id>/work`, `I` = `projects/<id>/input`.

## Steps

1. **Intake.** `uv run harness intake I --out W --project-id <id>`. Exit 3 = no DWG converter
   configured (`HARNESS_ODA_CONVERTER` / `HARNESS_DWG2DXF`) or an input unreadable; exit 1 = a
   file could not be read, an output failed its schema, or `knowledge/font-encodings.csv` is
   malformed. *Done when* exit 0, or you stopped and reported the stderr line.
2. **Extractors**, in this order: `uv run harness read-structure W --input-dir I`,
   `uv run harness callouts W --input-dir I`, `uv run harness marks W --input-dir I`,
   `uv run harness grid-system W`. *Done when* all four exit 0.
3. **Status.** `uv run harness status W`. *Done when* every producer is `fresh` (`reader` is
   `n/a`) and you have `gate1.reasons`. Blocking questions of intake, read-structure,
   grid-system and reader block gate 1; those of callouts and marks block lot specs only.
4. **Inventory.** In `W/inventory.json` every file is `read`, `partial` or `unreadable`; state
   why for each non-`read` one (`read-log.json`), its `converter` and `confidence_cap`, and
   `summary.changes` / `summary.stale_answers`. *Done when* all are reported.
5. **Questions.** `uv run harness questions-md W` writes `projects/<id>/questions.md`. It is
   generated: every change goes through the JSON documents and a rerun. *Done when* exit 0 and
   you have its `untranslated_codes`.
6. **Report** to the orchestrator: files by format and outcome, converter and cap, the
   `gate1.reasons`, unreadable files, changes, stale answers, untranslated codes.

## Reading the results

- **Units.** Each probed file has one blocking `units_confirm_all`; its refs carry the header
  evidence (conflict, suspect magnitude, unknown). Header units are never accepted. A blocking
  `units_answer_contradicts_evidence` means the answered unit makes the drawing's dimensions
  implausible: put both to the engineer, who re-answers or confirms the same unit.
- **File sets.** Two or more readable drawing files → one blocking project-level
  `file_set_relation`; its answer puts every file in exactly one set
  (`--value set1=a.dwg,b.dwg --value set2=c.dwg`). grid-system compares grids only within a set;
  until the answer, a conflict between grids of different files does not block, and its gate-1
  reason points at `file_set_relation`.
- **After any units, file-set, `grid_system_select`, axis or `grid_system_missing` answer**,
  rerun `harness grid-system`, then `harness status`: the grid systems read the answers. Status
  wins over the producer files. A question another answer settles is closed only when
  `gate1.closed` lists it; a `closures:` reason (the settling answer is not the engineer's)
  leaves it open and blocking. `proposed_simulated` and `proposed_closed_by` in
  `grid-systems.json` record what a non-engineer answer would do: nothing is confirmed or closed.
- **No usable or selected grid system** for a file → blocking `grid_system_missing`. Its answer
  is the engineer's: the grid values its answer command names, or `no_grid=yes` for a file with
  no plan that needs a grid. An answer in words only or from another role builds nothing.
- **Converter.** LibreDWG output is capped at `medium` (ERROR lines cannot lower it further);
  converter `ERROR` lines make a file `partial` (only their count is kept today); report the
  converter name and that its version is not recorded. `conversion_empty` is unreadable until
  the engineer answers.
- **No sheet detected** (`sheets_not_detected`): the file's text is reachable with `--unassigned`
  (`sheet-text`, `find-text`); name the file in the report so the reader takes that route.
- **Legacy Vietnamese fonts.** Text decodes only by a font name, Unicode evidence or an
  `approved` row of `knowledge/font-encodings.csv`. Other non-ASCII text, and ASCII text in a
  legacy font shaped like encoded Vietnamese (`legacy_ascii_suspect`), is **blocked**: the
  reader quotes it but takes no meaning from it. A `font_encoding_proposed` question closes when
  the engineer approves or rejects the row in a reviewed commit and intake reruns; `harness
  answer` does not settle it. Blocked ASCII text gets a non-blocking `legacy_ascii_text` question
  per file and style: report its Q-id and count; its answer records the engineer's reading of
  the style and unblocks nothing.
- **`dimension_override_differs`**: typed-over dimension text; the engineer decides.
- **`no_reader_implemented`** (PDF, images, DOCX, XLSX): ask for DWG/DXF.

## Answers

The answer command that `questions.md` and `harness status` print (`--role engineer`) is the
engineer's own step: hand it to the engineer, who runs it. You record only an answer the
orchestrator relays from an eval's engineer simulator: take the question's **Lệnh trả lời** line
in `questions.md` (it names the values), replace `--role engineer` with `--role simulated`, and
put the simulator's words verbatim in `--text`, its name in `--by`. No role stated → ask the
orchestrator. Gate 1 counts only the engineer's answers. Then rerun the producer the answer
feeds and `harness status`. The command refuses obsolete ids, changed files and
`grid_system_conflict` (that one closes through `grid_system_select` with `systems=` or
`separate=`).

## Hard stops

Intake exits 2 or 3; a file the engineer calls essential is `unreadable`; a producer stays
`stale` after its rerun. Stop, report, wait for the engineer.
