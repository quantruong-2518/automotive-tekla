# 0005. DWG converter chain: ODA File Converter, then LibreDWG

- Status: accepted
- Date: 2026-11-06

## Context

DWG is a closed format; every reader we use (ezdxf) needs DXF. Two converters exist:
ODA File Converter (best fidelity, freeware, licence terms set by the Open Design Alliance)
and LibreDWG `dwg2dxf` (GPL-3, weaker on recent DWG versions). The engineer chose ODA with a
LibreDWG fallback on 2026-11-06. The ODA commercial-use licence question in
`docs/roadmap.md` stays open until the engineer confirms it in writing.

## Decision

- Order: ODA File Converter → LibreDWG `dwg2dxf` → the file is `unreadable`, and an open
  question asks the engineer for a DXF or PDF export.
- Both converters are external executables at a configured path (CLI option or environment
  variable). Neither is bundled, vendored or linked. LibreDWG runs only as a subprocess, so
  GPL-3 does not reach our code.
- A conversion succeeds only if the output DXF exists and `ezdxf` can open it. Exit code 0
  alone proves nothing (converters are known to exit 0 on failure).
- Every attempt — missing binary, non-zero exit, timeout, missing output, unreadable output —
  is recorded in `read-log.json` with an `error`, then the next converter is tried.
- A DXF produced by the fallback converter caps the confidence of every value read from it
  at `medium`. A DXF produced by ODA does not lower the cap.
- Converters write into a per-file temporary folder, never into `input/`.
- No converter configured or found at all is an environment error (exit `3`): fix the machine,
  do not produce a project of unreadable files.

## Consequences

- Until real DWG samples are available, the DWG path is proven only with fake converter
  executables in tests. Real conversion is verified on the Tekla machine with sample files.
- The ODA command-line signature (folder-based: input folder, output folder, version, type,
  recurse, audit, filter) is taken from memory of the ODA docs and must be checked against the
  installed version before the first project run.
