# `questions.md`

`uv run harness questions-md projects/<id>/work` generates it from `work/*questions.json`,
`question-registry.json`, `answers.json`, `grid-systems.json` and `structure-summary.json`;
those are the source of truth. To change it, change them (an answer, a reader question, a
rerun) and render again.

What you write that ends up in it is a reader question (`harness ask --text`) or reader
evidence on a producer's question (`harness ask --supplement Q-id`, printed under it): one per
call, in Vietnamese, plain words (bản vẽ, lưới trục, cao độ), the drawing text quoted verbatim
in `--found`, the place in `--where`. A suggestion goes in `--text` as
`Đề xuất (chưa xác nhận): …`, never as the answer.

The Vietnamese wording of producer questions lives in `src/tekla_harness/questions_md_vi.py`
(proposed copy, pending engineer review). A code listed in `untranslated_codes` prints its
English message: report it, so the wording can be added.
