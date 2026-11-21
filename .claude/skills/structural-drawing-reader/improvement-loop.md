<!-- PROPOSAL rev11: part-mode rewrite of the installed improvement-loop.md; installed only after the independent review. -->
# Review round and improvement loop (orchestrator)

Run by the orchestrator after a part reader's hand-back, after any engineer correction, and after any change to a reading skill or
tool. The reader and the reviewer never run this file. Agents propose; the engineer approves every rule, row and merge (AGENTS.md
principles 6, 7, 9). `PT` = `W/parts/<part>`; the stages, receipts and the lock are in [part-mode.md](part-mode.md).

## 1. Review round (one part at a time)

1. Check the hand-back: for `scout`, `harness part manifest-check W` exits 0, the orchestrator records `harness part receipt W --part scout --kind checked`, step 2 is skipped (no prompts) and the reviewer follows review-rubric.md § Manifest
   review (a scout writes no C2–C10 lines); for every other part `harness part check W --part <part>` exits 0, the receipt `checked` is on the
   current hash (`harness status W`), `PT/notes.md` holds its C2–C10 lines (a `not run` line gives its reason). For `all-assembly` also no
   `titled` node in the Breakdown table. Otherwise the part goes back to its reader before any review. Then run `harness part conflicts W`
   (part-mode.md § Dispatch and fix loop).
2. Build the sample with `harness part review-sample W --part <part> --seed <n> [--n <k>]` (fallback: review-rubric.md § Sample);
   `seed` = a number the orchestrator picks once the part is `checked` (never the reader) and records in `PT/review/round-<n>/seed.txt`.
   Prompts carry no value from the reading.
3. Dispatch a fresh reviewer (`doc-reader`, Opus per `delegating-work`: review is judgement) with: the project id, the part, the round,
   the seed, the prompts, and the pointer "follow `review-rubric.md`". Give it nothing of the reader's hand-back.
4. Record the verdict of every round: `harness part receipt W --part <part> --kind reviewed --review <absolute
   PT/review/round-<n>/review.md> --round <n> --verdict <pass|fix|engineer>`. The latest `reviewed` receipt on the current hash decides: a
   `fix` after a `pass` blocks the lock. `pass` → `--kind locked`; when every part is locked, go to `drawing-analysis-report`. `fix` → the reader gets the defect list only, repairs findings, questions and rows through the tools,
   reruns `part check` to exit 0 and hands back; the orchestrator records `checked` again and round 2 is narrow (the defects only).
   `engineer` → both rounds go before the engineer, who rules in chat. He accepts: write `PT/review/round-3/review.md` (the blind-answer
   sha line, his words verbatim, verdict `pass`), record `--round 3 --verdict pass`, then `locked`. He asks for fixes: the reader fixes,
   `checked` is recorded again, a fresh narrow round-3 review runs. No third reviewer round without him.
5. Whatever the verdict, run § 2 on every defect.

*Done when* `PT/review/round-<n>/review.md` ends in a verdict, the `reviewed` receipt is recorded and every defect has a route in § 2.

## 2. From defect to fix

A **defect** is a row of a review, an engineer correction (an answer that overturns a claim, a comment on a report, a remark in chat), a
spot-check row marked `wrong`, a failed benchmark case, or a difference found by comparing two readings of one set (the side the drawing
does not support is the defect; an item both readings missed is a defect of both). Each gets:

| Field | Value |
|---|---|
| part | the part id it sits in (`scout` for a manifest defect, `all-assembly` for a cross-part one); classes are counted per part |
| class | one of § Classes |
| layer | `tool` — a producer or command gave the wrong or no result, or could have refused the error; `skill` — the procedure led there or was silent; `knowledge` — a convention was unknown or used unverified; `input` — the files lack it; `reader slip` — rule and tool were right, the reader broke the rule |
| root cause | why the layer failed, in one sentence that names the file, command or rule |
| proposed fix | by layer, below |
| regression case | a benchmark case id or an answer-key row (§ 4), plus a test in `tests/` for a tool fix |

Routes:

- **tool** → a code package for `executor`, red-first, with an Opus review, on a feature branch; the engineer merges.
- **skill** → a change in the next proposal folder `dwg-lab/proposals/skills/rev<N+1>/`, never in `.claude/skills/`.
- **knowledge** → a `proposed` row (§ 3) with its evidence; until approved it only makes the
  reader ask.
- **input** → the question to the engineer already exists or is raised; no skill change.
- **reader slip** → count it. The same slip in two rounds, two parts or two projects is reclassified
  `tool`: a rule the reader breaks twice moves into a command that refuses it (`part check` problem codes are the pattern).
- A defect found in a `locked` part: reopen it (`part receipt --kind reopened --reason`), then fix and narrow review as in part-mode.md
  § Lock and reopen; parts that list it as an input are `stale_input` until it is `locked` again, and each of them goes through
  `reopened`, `checked`, `reviewed`, `locked` itself.

**Fix the class, not the instance.** Every tool or skill fix names its class and a variant matrix: at least three other forms the same
fault can take (other spelling, other sheet type, other member family, other file layout), each a fixture or a benchmark case. The
reviewer of the fix checks the variants.

**Rule budget.** SKILL.md stays under 200 lines. A fix that adds a sentence there removes or merges another, or moves one into a tool.
A rule born from one instance is a row in edge-cases.md.

Then `reporter` writes one `requests-to-improve.md` entry per class and root cause (Critical defects one entry each), in that file's
format (source, classification, severity, status `proposed`, root cause, proposed fix, regression test) on a branch, for the engineer.

### Classes

| Class | Covers |
|---|---|
| `font_gate` | text blocked by a font with no approved row; blocked text read or copied |
| `member_marks` | non-member labels read as marks; a schedule or table not recognised or cut by its frame; mark sets incomplete; member sizes not recorded |
| `grids` | a grid not detected, split in halves, merged across blocks, taken from a key plan or 3D view |
| `sheet_identity` | sheet numbers, titles, drawing list, revisions |
| `negative_scope` | a tool's silence or a partial search written as absence |
| `levels` | datum, storey against local, finished against structural, level text variants |
| `trace` | a section or detail reference not followed; a typical detail's scope |
| `scope_breakdown` | blocks, a sheet or cluster put in the wrong part, a missing part or discipline, coverage of the tree, a grid wider than its members, counts that do not chain (caps, stubs, bases, schedule) |
| `units_dimensions` | units evidence, typed-over or scaled dimensions |
| `knowledge` | a convention unknown, or used without a verified source or an answer |
| `relay` | a value or a search scope lost between reader, report and plan |
| `process` | a stage skipped (receipt order), a hand-back without `part check` exit 0, a table not edited in place, a claim without its form, a search outside the project folder, a blocking flag missing on a gate 1 value |

A defect that fits none: propose a new class in the RTI entry.

## 3. Knowledge grows by approved rows only

Proposed table `knowledge/drawing-conventions.csv` (does not exist yet: tools.md T11), on the pattern of
`knowledge/font-encodings.csv`:

`id, topic, notation, reading, scope, status, evidence, source, decided_by, decided_on`

- `status`: `proposed | approved | rejected`. Only `approved` rows are rules for the reader; a `proposed` row makes the reader ask and
  show the row's evidence; `rejected` rows stay as memory.
- `source`: a primary source (standard clause, manufacturer manual) or `engineer`. A row whose source is a search excerpt stays
  `proposed`.
- `scope`: where it holds (country, office, building type); a convention seen in one project is scoped to that office until the
  engineer widens it.
- `evidence`: anonymised counts ("3 dev sets, 41 callouts"), no drawing text beyond the notation.
- Agents add `proposed` rows in a pull request; the engineer sets `approved` or `rejected` in a reviewed commit.

Research notes (`docs/research/`) feed rows the same way: a claim marked `verified` there may be proposed as a row; an `unverified` one
may only become a question.

## 4. Benchmark of known-answer cases

Purpose: after every change, measure instead of judging by feel (principle 9), on drawings the change was not written against.

- **Where**: `projects/_evals/reading-benchmark/cases.csv` (git-ignored: client drawings). Dev projects only; `projects/_heldout-*` is
  never read, listed in a case, or used here.
- **Case**: `id, project, prompt, expect, key_source, class, rti, status`.
  - `expect` is one of: `value: <text>`, `set: <a|b|c>`, `must_ask` (the reading holds a question
    on it), `must_be_unread`, `must_not_claim: <text>`.
  - `key_source`: an engineer answer id or an `answer-key` row (`--by` his name, from his chat words). A key built by an agent
    is `status: candidate` and scores nothing until the engineer confirms it.
- **Seed set**: K1–K14 for three dev projects of different kinds (a steel factory on piles, an RC multi-storey frame, a mixed set),
  plus at least one case per class of § Classes taken from the recorded eval defects (the five recurring ones first: `font_gate`,
  `member_marks`, `grids`, `sheet_identity`, `negative_scope`).
- **Run**: on a frozen commit, a part-mode run per benchmark project (scout to `all-assembly`, every part reviewed and locked). Score
  each case pass or fail from the artefacts.
- **Spot check** (stage 8, locked parts only): `harness part spotcheck W --part <part> --seed <n> [--n 5]` writes the sample and a
  Vietnamese checklist (`P/spotcheck/<part>.md`). The orchestrator records the engineer's verdict from his chat words with `harness part
  answer-key W --part <part> --row <R> --verdict ok|wrong|cannot_tell --by "<engineer's name>" [--correct <value>] [--text <his words>]`,
  never a verdict of its own. `spotcheck` leaves out of its pool a row whose key is ambiguous (shared with a `seen` row of another value;
  named on stderr) and a row with no file; `answer-key` refuses an ambiguous key. `harness part score W [--answer-key F]` compares the
  current rows of any work folder with the key by part, file, sheet, subject and field (a reread with new finding ids is scored; strict:
  `agree` only when every `seen` row under a key equals its correct value): per part `checked`, `agree`, `differ`, `missing`,
  `cannot_tell`. Accuracy is agree ÷ (checked − cannot_tell), so `missing` counts against the reading. The key is `W/answer-key.json`; a
  copy goes to `benchmark/<project>/` only on the engineer's approval and scores a later run (`--answer-key`).
- **Bar** (proposed; the engineer sets it): every `must_ask`, `must_be_unread` and `must_not_claim` case passes; at least 95 % of
  `value` and `set` cases pass and spot-check accuracy reaches it; no case that passed on the previous commit fails now; every
  part's review verdict `pass` or `fix` with no Critical.
- **Dress rehearsal** before any held-out eval: the same run on at least two dev projects not opened while the change was written.
- Every defect fixed adds its regression case here; a tool fix also ships its test in `tests/`.

## 5. Report to the engineer

After each round, in Vietnamese, short: defects by class and part before and after, what changed (tool, proposal, proposed rows), which
decisions wait on the engineer (font rows, convention rows, benchmark keys and spot-check rows to confirm), and the benchmark and `part
score` against the bar. Stop the loop after three rounds on the dev set, or when a round finds no new Critical or Major defect
(RTI-0015 decision 3).
