# 0013. Grid system from an engineer's answer

- Status: proposed
- Date: 2026-11-09
- Decided by: orchestrator, tool wave 3 decision W2 (reversible), pending engineer approval

## Context

Gate 1 needs a grid system for every building the project uses (`harness status`, reason `grid
systems:`). The grid extractor finds systems from bubbles, labels and lines. When it finds none for a
file, nothing today can give that file a grid. In EVAL-3, two of the four held-out houses had none:
dwgshare 285 has 656 labelled bubbles drawn as polylines and 0 axes, and 286's plan grid was missed.
The engineer could read the grid off the drawing, but there was no way to record it. So gate 1 stayed
blocked even with real engineer answers. EVAL-3's judges rated this the most important tool gap, and
the EVAL-4 protocol counts such a gap as Critical friction.

Tool wave 3 also improves detection, so that 285 and 286 are found. Detection will still miss some
drawings, so a recorded route is needed as well.

## Decision

1. `harness grid-system` raises `grid_system_missing` (blocking, gate-1 producer `grid-system`), one per
   drawing file that has plan sheets but no usable grid system (until a tool classifies plan sheets:
   every read drawing file without one, answered `no_grid=yes` when it holds no plan). Usable means a system that is not
   rejected and has at least two labelled axes in each of two directions. The question quotes what was
   found: bubbles, labels, rejected systems.
2. The answer carries structured values: the labels and spacings of each direction (dir1 and dir2), and
   optionally the sheet. Spacings are in drawing units, like every other grid value. The `--value` keys
   (fixed by the tool wave 3 seam; `harness answer` help and the question's answer command print them):

   | Key | Required | Form on the command line | Stored in answers.json |
   |---|---|---|---|
   | `dir1_labels` | yes | comma-separated axis labels in drawing order, at least 2, distinct, none blank: `dir1_labels=1,2,3,4,5` | array of strings |
   | `dir1_spacings` | yes | comma-separated distances between consecutive axes, each > 0, exactly one fewer than the labels: `dir1_spacings=3130,3540,3520,4590` | array of numbers |
   | `dir2_labels` | yes | as `dir1_labels`, for the other direction: `dir2_labels=A,B,C` | array of strings |
   | `dir2_spacings` | yes | as `dir1_spacings`: `dir2_spacings=4250,3730` | array of numbers |
   | `sheet` | no | the detector sheet id the grid was read from: `sheet=model#05` | string |
   | `no_grid` | instead of all the keys above | `no_grid=yes`: the engineer states that this file holds no plan that needs a grid (notes, details or sections only) | `"yes"` |

   `no_grid=yes` is alone or not at all: it is refused with any other key. From the engineer it closes the
   question and builds nothing; the file then has no grid system by the engineer's statement, which the
   gate-1 document shows. From any other role it closes nothing, like every other answer (decision 4). It
   exists because the question is raised for every read drawing file without a usable system (no tool
   classifies plan sheets yet), and a notes-only file must not hold gate 1 shut for ever (orchestrator
   default, tool wave 3 review; reversible by the engineer).

   Both directions are required: a usable system has two (decision 1). An answer without values is
   recorded as words and builds nothing, so it does not close the question either, even from the
   engineer: the file still has no usable system, and gate 1 stays shut on it until the engineer gives
   the values or the file leaves the input set (orchestrator default, tool wave 3; reversible by the
   engineer). Which direction becomes Tekla X or Y is not part of this answer: it is asked afterwards on
   the built system, like for a detected one (decision 3).
3. A grid system is built from that answer only when the answer is active, structured, and recorded with
   `answered_by_role: engineer`. The system carries `source: engineer_answer` and the answer id as its
   provenance. It then goes through the same gate-1 steps as a detected system: select, X/Y, units.
4. A simulated or role-less answer is recorded and builds nothing. `harness status` lists it under
   `answers:`, the same rule as for every other gate-1 answer (tool wave 2, F3).
5. The drawing is still checked. `grid-system` compares the given spacings with linear dimensions whose
   extension points fall on the given axes (where it can place them). On a mismatch it raises
   `grid_answer_contradicts_drawing`, which quotes both the answer and the dimension. The engineer stays
   authoritative, but the contradiction is never silent.
6. `harness status` closes `grid_system_missing` only from the built result, never from the answer alone:
   the engineer's `no_grid=yes`, or a fresh `grid-systems.json` holding a system whose `source_answer` is
   that question's key. Freshness covers who answered: an answer that changes role (simulated, then the
   engineer with the same values) makes the grid-system output stale. An answer-built system is checked
   for conflicts against every other system, the same way as two detected systems.

## Consequences

- Gate 1 can open for a building whose grid the tools cannot detect, once the engineer has typed the grid
  in. This is a new input path into gate 1, so the commit that adds it carries a `Safety:` line.
- An agent can still record an answer with `--role engineer` (RTI-0011, open). This ADR adds no new
  bypass: a forged role here has the same effect as one on any other gate-1 question.
- A project whose every file is answered `no_grid=yes` has no grid system at all, and gate 1 stays shut
  on "no grid system": a Tekla model needs one. `no_grid=yes` on a file that also has a selected detected
  system is not flagged as a contradiction yet (open; tool wave 3 gridgate fix report).
- The answer is a second source of truth beside the drawing. Spacings are checked against the
  dimensions, but labels and order are taken as given.
- Rejected: building a grid from a simulated answer, so that evals could pass gate 1. Gate 1 never opens
  on simulated answers.
- Rejected: building a grid from the reader's prose. Readers never create gate-1 inputs.
