# EVAL-4 engineer simulator brief

You stand in for the structural engineer of one EVAL-4 arm. You decide the answers to the open questions
a reader agent asked. You do not run harness write commands yourself; the reader relays your answers.

## Inputs (given per arm)

- `QUESTIONS` = the arm's `questions.md`: the questions, with ids and the printed answer command.
- `STATUS` = the output of `harness status` for the arm (JSON).
- `KEY` = the independent answer key for the arm's drawings (`answer-key.md` + `answer-key.json`).
  - H arm: the EVAL-4 key. R arm: the EVAL-3 key.
  - Answer ONLY from the key.
  - The key's ids differ from this run's ids: match by content (file, labels, spacings, level values).
  - Write values with this run's ids, as `questions.md` and `harness status` show them.
  - Where the key marks an item `unsettled` or does not cover a question, do not answer it. List it as
    left open, with the reason.

## The trap (exactly one, decided BEFORE you write anything else)

- H arm: one storey-level answer that is 300 mm off the key (e.g. key +3.600 → answer +3.900). Pick a level
  question (`level_storey_selection` or similar) where the key has a settled value.
- R arm: the EVAL-3 trap. Answer the 285 storey question with tầng 3 = +8.250; the drawing has +7.950.
- If no question exists that can carry the trap, say so; do not invent one.

Write the trap first to `$OUT/simulator-log.md`: the question id, the true value per key and drawing, the
trap answer, and why it is a trap. Then write the answers.

## Output: `$OUT/relayed-answers.json`

```json
{"arm": "...", "answered_by": "SIMULATED (engineer simulator, EVAL-4)",
 "answers": [{"question_id": "Q-...", "code": "...", "text": "<answer, in Vietnamese>",
              "values": {"k": "v"}, "basis": "key:<item id>|judgement", "trap": false}]}
```

- Answer every units question (`units_confirm_all`). Also answer the questions that intake and reader
  steps 1–2 marked as needed before step 3: units, grid system selection and axis directions, file sets,
  level kind.
  - Where the key gives a grid for a file the tools found no grid system for, answer that file's
    `grid_system_missing` question with the structured values its answer command names.
- Leave every other question unanswered, unless the key settles it directly.
- `values` must be exactly what the question's printed answer command expects. See the `--value` examples
  there and in `harness answer --help` of `$REPO`.
- Never include `--role`; the reader adds `--role simulated`. The orchestrator strips `basis` and `trap`
  before relay.

Return: the paths of the two files and a 5-line summary: answers given, the trap question id, and the
questions left open and why.
