# 0007. Read cache design: content-addressed, verified on every read

- Status: accepted
- Date: 2026-11-06
- Research: [`docs/research/read-cache.md`](../research/read-cache.md) (section numbers below)

## Context

ADR-0006 adds a per-project read cache. A cache that returns a wrong or stale result is worse
than no cache: it turns one bad reading into a silent, repeated one. The bar is therefore
correctness first, speed second.

## Decision

**Model.** A memoised action, i.e. a *constructive trace* (Build Systems à la Carte, §3): the
key is a hash of every input that can change the result; the value is the recorded result.

**Layout** (Bazel REAPI Action Cache + CAS, §1; git loose-object fan-out, §4):

```
<cache>/CACHEDIR.TAG            backup tools skip it (§6)
<cache>/.gitignore              "*": git ignores it, like .pytest_cache and .ruff_cache (§7)
<cache>/cas/<2 hex>/<sha256>    output blobs, named by their own digest
<cache>/ac/<2 hex>/<key>.json   action entry (schemas/cache-entry.schema.json)
```

The entry is written after all its blobs, so it is the commit marker. Identical outputs are
stored once.

**Key.** `sha256(domain tag || canonical JSON(material))`.
- Domain tag `tekla-harness/read-cache/action/v1\0`, the same idea as git's `type size\0`
  header (§4, §9). SHA-256 gives 128-bit collision resistance (§9).
- Canonical JSON = `json.dumps(sort_keys, separators=(",", ":"), ensure_ascii=False,
  allow_nan=False)` in UTF-8. Floats are refused. This is *not* RFC 8785: it does not need
  to be, because only this implementation reads the keys. It differs from RFC 8785 only on
  floats (refused), non-ASCII key order and Unicode normalisation (§8). Material is ASCII by
  construction (digests, tool names, version strings, argument templates).
- Material for `dwg_to_dxf`: the digest of a **staged copy** of the input (made once; the key
  and every converter see the same bytes even if the file changes mid-run); the resolved
  converter chain in order, each command word that is a file identified by its **content**
  digest (ccache `compiler_check=content`, §2; memoised per process by path, size and
  mtime); a bare name is resolved on PATH first, so the file that runs is the file that is
  hashed; the argument templates; the ezdxf version (the success oracle); the digest of the
  modules that produce or replay the result (`convert.py`, `cache.py`, `readlog.py`,
  `detect.py`, line endings normalised); the cache format version.
- Not in the key: paths (they would leak client folder names and break hits across
  machines), timeouts and timestamps. Timeouts can only turn a success into a failure, and a
  run with any failed attempt is not cached (below), so they cannot change a cached value.

**Read.** Every hit is verified: entry JSON parses and passes its schema; the stored key and
the recomputed key of the stored material both equal the requested key; every blob exists
with the recorded size and digest. Then the recorded result must be one this code could have
recorded: a known converter with its own confidence cap, a non-empty list of attempts that
all succeeded and end with that converter, warnings that are strings, exactly one output.
Any failure is a miss: the entry (and a corrupt blob) is deleted with a stderr warning and
the action reruns. A file that cannot be opened right now (Windows sharing violation) is a
miss without deletion.

**Write.** Temp file in the target folder, `flush`, `fsync`, `os.replace`, then `fsync` the
folder on POSIX (Linux `fsync(2)`, §5). `os.replace` is documented atomic only as a POSIX
requirement; Microsoft does not document `MoveFileExW` replace as atomic (§5). The design
therefore does not depend on rename atomicity: verification on read is what makes a torn or
foreign file harmless. On a Windows `PermissionError` with an identical target already in
place, the other writer won and the write is a no-op. No locks: concurrent writers of one key
write equivalent results; the last one wins.

**What is cached.** Only clean successes: every attempt in the run succeeded (Bazel, REAPI
and ccache never cache failures, §10). A fallback that follows a failed attempt is not cached,
because the failure may be transient (timeout, licence server) and caching it would pin the
`medium` result for good. A LibreDWG result is cached only when LibreDWG was the whole chain;
if ODA is installed later, the chain and therefore the key change. The blob stored is the
converter's validated output in its work folder, never the copy delivered to the output
folder, which another run may overwrite. A hit replays the recorded converter, confidence
cap, attempts (with their original timestamps: that is their provenance) and warnings. A
cache write failure leaves the conversion valid and adds a warning.

**Refresh.** `--refresh` deletes the entry first, then recomputes. A refresh that fails, or
that only reaches the fallback, therefore leaves no entry behind, and the next run tries the
full chain again. This is the remedy for a converter upgraded in place.

**Non-determinism.** Converter output is probably not byte-reproducible (timestamps, GUIDs,
§11). A hit therefore means "a recorded valid result of the same action", which Build Systems
à la Carte accepts for non-deterministic tasks ("one possible result", §3). Byte equality is
tested only with deterministic fake converters.

**Interface.** `harness dwg2dxf --cache-dir <projects/<id>/.cache> [--refresh]`. No cache
without `--cache-dir`; no default under the home folder (ADR-0006: never shared across
projects); `--refresh` without `--cache-dir` is a usage error. Refused: a cache folder inside
the input's folder, a cache folder that contains the input, and an existing non-empty folder
that is not already a read cache (tagging it would make git and backup tools skip unrelated
files).

## Not now

- Eviction: a project cache is bounded by the project; delete the folder to reset.
- Cross-project or remote sharing: forbidden by ADR-0006.
- Vision reads: when implemented, their key adds the tile image digest, render parameters
  (dpi, region), model id and prompt digest.

## Consequences

- Known gap: a converter's own libraries (ODA DLLs, `libredwg.so`) are not in the key; only
  the executable is. After upgrading a converter in place without changing its executable,
  run with `--refresh` or delete the cache. A command word that is a wrapper script is
  identified by the wrapper's bytes, not by what it calls.
- Known gap: only the input's own folder is guarded. With nested input folders
  (`input/sub/x.dwg`) a cache at `input/.cache` is not detected; the orchestrator must always
  pass `projects/<id>/.cache`.
- Growth: blobs orphaned by a refresh and `.tmp-*` files left by a killed writer are not
  collected. Accepted for a per-project cache; delete the folder to reset.
- Every hit costs one hash pass over its outputs. Accepted: DXF files are megabytes, a
  conversion costs seconds.
- Changing anything in the key material, the layout or the listed modules invalidates old
  entries automatically; no manual cache version bump is needed for code changes.
- Review: an independent Opus review (2026-11-06) found 2 critical and 4 major defects in the
  first implementation (transient-failure pinning, caching the delivered copy, refresh leaving
  stale entries, unvalidated replay, unsnapshotted input, bare names keyed by name). Each has a
  regression test that fails on the first implementation.
