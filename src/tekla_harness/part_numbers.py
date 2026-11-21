"""part_numbers: the number checks (number_unbacked, token_unbacked) of `harness part check`.

Every number and every glued token a part reader types into a row's `value` must be found in a source the
row cites (`part_values.sources`): this stops a value typed from memory. A row with a `hand_sum` is checked
by its sum (`part_sums`), so its numbers are not looked up here; its glued tokens still are.

- `number_unbacked`: a standalone number of the value (`findings._numbers`) equal to no source number
  (exact for the numbers of a text, the symbols and the item count; within the saved query's tol for the
  `short`, `long` and `diameter` of an item, as `findings._unbacked_numbers`). One problem per
  distinct number.
- `token_unbacked`: a glued token of the value (`-1.200`, `2Ø16`, `-0,450`, `C30/37`) that no source text
  quotes. The sign and the whole token count: a backed number does not back its token.
"""

from __future__ import annotations

from tekla_harness.findings import _numbers
from tekla_harness.part_values import PartContext, Problem, backs, glued_tokens, sources


def number_problems(ctx: PartContext) -> list[Problem]:
    problems: list[Problem] = []
    for r in ctx.rows:
        value = r["value"]
        if value is None:
            continue
        found = sources(ctx, r)
        if not r.get("hand_sum"):
            for n in dict.fromkeys(_numbers(value)):
                if not any(backs(s, n) for s in found):
                    problems.append(
                        Problem("number_unbacked", r["row"], None, f"{n:.10g} is in no cited source")
                    )
        for token in dict.fromkeys(glued_tokens(value)):
            if not any(backs(s, token) for s in found):
                problems.append(
                    Problem("token_unbacked", r["row"], None, f"'{token}' quotes no cited source text")
                )
    return problems
