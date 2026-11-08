# Strict JSON corpus

Shared by the Python strict loader (`tests/`) and the C# reader in `TeklaCore`
(`tekla/TeklaCore.Tests`), so both read spec and receipt files the same way
([ADR-0010](../../../docs/decisions/0010-spec-validation-receipt.md), Amendment 1).

- `accept/`: every file must parse.
- `reject/`: every file must be rejected.

Files are raw bytes (`binary` in `.gitattributes`): BOM, CRLF and invalid UTF-8 are the point.
A new rule in the profile adds a file here first, then both readers. The 16 MiB size limit is
tested in each language's own tests (the file is generated, not committed).
