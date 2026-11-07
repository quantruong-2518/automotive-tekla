# PROPOSAL: ADR-0005 addendum, "Consequences / evidence from the first real run"

Status: PROPOSAL, pending engineer approval. Not yet applied to `docs/decisions/0005-dwg-converter-chain.md`.

## Evidence (LibreDWG 0.14, 29 real DWG files)

- All 29 conversions exit 0 and ezdxf opens every output DXF.
- One file converted to an openable DXF with an empty modelspace (only viewports), with about
  2,100 "unhandled class" warnings on stderr. Exit code 0 and "ezdxf opens it" were both true.
- 20 of 29 files print lines starting with `ERROR:` on stderr and still exit 0 (for example a
  `bit_read_TU` buffer overflow repeated 624 times). Strings may be truncated.
- Before this change stderr was discarded on success, although it is the only signal of a
  partial parse.
- The command line `-y -o <out> <src>` is correct for 0.14.

## Rule (implemented in `convert.py`)

Success = output DXF exists AND ezdxf opens it AND at least one entity exists in modelspace or
any paperspace layout. An empty result from a DWG larger than 10 KB is recorded as attempt
status `partial` (error: "DXF opened but contains no entities in any layout"), not failed,
because an empty drawing can be legitimate; the confidence cap becomes `low`.

Converter stderr lines starting with `ERROR` and `Warning` are counted on success and exposed as
`stderr_error_lines` / `stderr_warning_lines`, with the stderr tail (300 chars). Any ERROR line
adds a warning ("may be missing or truncated"; it does not claim what is lost) and lowers the
confidence cap one step (high to medium; medium and low unchanged). LibreDWG is already capped
at medium, so for it the ERROR count is the finer signal, not a further cap.

## Open points

- ODA File Converter behaviour is unmeasured: no ODA installation was available. Its stderr
  format, exit codes on partial parses and the argument order remain unverified.
- No resource limits (memory, CPU) are applied to converter subprocesses: the production machine
  is Windows and the Python `resource` module is POSIX-only. Only the wall-clock timeout applies.
- `cli.py dwg2dxf` does not yet print the new fields (they are visible only through
  `warnings`); a follow-up may add them to its JSON output.
