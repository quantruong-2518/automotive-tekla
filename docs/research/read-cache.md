# Research note: content-addressed result cache ("read cache")

Date: 2026-11-06. Purpose: facts with primary sources to ground a later ADR for a content-addressed
cache that memoizes expensive file conversions (for example DWG to DXF by an external converter),
keyed by input content. This note reports facts only. It makes no design recommendation.

## Method and reliability

- Versions read: ccache manual 4.14.2 (page footer "Last updated 2026-10-18"); Python docs 3.15.2;
  git, CPython, pytest, ruff, Bazel and remote-apis sources read from `master`/`main` on 2026-11-06
  (no commit SHAs recorded); git v2.30.0 `sha1-file.c` for the older temp-file layout.
- Read raw (text is verbatim from the file or page): Build Systems a la Carte ICFP 2018 PDF
  (text extracted locally), Python `os` docs, CPython `posixmodule.c` and `PC/errmap.h`, git
  `object-file.c` and `compat/mingw.c`, Linux man pages `fsync(2)` and `rename(2)`, POSIX
  `rename()`, Microsoft `MoveFileExW`, `CreateFileW` and `FILE_RENAME_INFO` pages.
- Read through a summarizing fetch tool (quotes below marked "(relayed)" were returned by that
  tool, not read by me; re-check before quoting in the ADR): remote-apis proto, ccache manual,
  Bazel docs, Bazel Java source, git docs, pytest and ruff source, RFC 8785, Python `json` docs
  and `json/encoder.py`, NIST pages, reproducible-builds.org pages, bford.info.
- Nothing was executed (no Python, no Windows). Claims about runtime behaviour are derived from
  the cited source and are labelled "derived" where that is the case.

---

## 1. Bazel remote caching: AC vs CAS, action digest, output references

**Split.** Bazel docs: "The action cache, which is a map of action hashes to action result
metadata." and "A content-addressable store (CAS) of output files." "Action result metadata is
stored under the path `/ac/` and output files are stored under the path `/cas/`." (relayed)
Source: https://bazel.build/remote/caching

**AC key is the digest of the encoded `Action` message.** The REAPI `ActionCache` service comment
says results are addressed by the digest of the encoded `Action` that produced them (relayed
paraphrase; `Action` entries are "identified by the digest of their wire format encoding").
Source: https://github.com/bazelbuild/remote-apis/blob/main/build/bazel/remote/execution/v2/remote_execution.proto

**What is in an `Action`** (same proto, relayed):
- `command_digest`: "The digest of the Command to run, which MUST be present in the
  ContentAddressableStorage."
- `input_root_digest`: digest of the root `Directory` (a Merkle tree of the input files).
- `timeout`, `do_not_cache` ("If true, then the `Action`'s result cannot be cached"), `salt`
  ("An optional additional salt value used to place this `Action` into a separate cache
  namespace..."; it "allows disowning an entire set of ActionResults that might have been
  poisoned by buggy software or tool failures"), and `platform` properties (the field comments
  say clients SHOULD set platform properties here; the `Command.platform` field is deprecated
  as of v2.2).
- `Command` (referenced by `command_digest`): `arguments`, `environment_variables` ("MUST be
  lexicographically sorted by name"), `output_paths` ("MUST be deduplicated and sorted
  lexicographically by code point"), working directory, platform (deprecated there).
  The sorting rules exist so that one logical action has one digest.
- `Directory` entries "must each be sorted in lexicographical order by path" (relayed).

**Digest.** "A digest for a given blob consists of the size of the blob and its hash." "The size
is considered to be an integral part of the digest and cannot be separated." A request with a
correct hash but wrong `size_bytes` MUST be rejected (relayed).
Hash function is negotiated: `DigestFunction` enum lists SHA256, SHA1, MD5, BLAKE3 among others;
"The digest function used for converting values into keys for CAS and Action Cache."; an
`ActionResult` "MUST use the same digest function as the one used to construct the action"
(relayed). Same proto.

**How outputs are referenced.** `ActionResult` holds `output_files` (`OutputFile`: `path`
relative to the working directory plus a `digest` of the content), `output_directories` (each
refers by digest to a `Tree` message, "a single directory Merkle tree, compressed into one
message"), `exit_code`, `stdout_digest`/`stderr_digest` ("a blob containing the standard output
of the action, which can be retrieved from the CAS"). Output bytes live in the CAS; the AC entry
only carries digests (relayed). Same proto.

**AC to CAS consistency.** `GetActionResult`: "Implementations SHOULD ensure that any blobs
referenced from the" `ActionResult` are in the CAS at return time "and will be for some period of
time afterwards"; `NOT_FOUND` means the result is not in the cache. `UpdateActionResult`: "the
client MUST first upload the Action that produced the result, along with its Command." CAS
lifetime "is implementation specific" (relayed). Same proto.

**What Bazel docs say is NOT in the key.** "Only environment variables explicitly whitelisted
via `--action_env` are included in an action definition." "Bazel currently does not track tools
outside a workspace." (relayed) https://bazel.build/remote/caching
Poisoning: "When an input file is modified during a build, Bazel might upload invalid results to
the remote cache." (relayed) Same page.

---

## 2. ccache: hashed information, direct vs preprocessor mode, `compiler_check`

Source for all of Q2 (manual 4.14.2, relayed): https://ccache.dev/manual/latest.html

- Overview: ccache creates "a unique hash (the 'input hash') from various information that
  affects the compilation". Hash algorithm is BLAKE3 for the key; XXH3 is used for integrity
  checksums of stored data.
- Common hashed information: the compiler's identity and version data (see `compiler_check`),
  the compiler name, the current directory when `hash_dir` is enabled, contents of files named in
  `extra_files_to_hash`.
- Preprocessor mode: "Ccache runs the preprocessor on the source code and hashes the result."
  Inputs to the hash: output of running the compiler with `-E`, most command-line options (except
  include-related ones such as `-I`, `-include`, `-D` as listed in the manual), preprocessor stderr.
- Direct mode: "Ccache hashes the source code and include files directly." It hashes the input
  source file and the compiler options, finds a manifest by that hash, and checks the include-file
  hashes stored in the manifest. On mismatch "ccache falls back to running the preprocessor".
- `compiler_check` (default `mtime`): "By default, ccache includes the modification time
  ("mtime") and size of the compiler in the hash." Values:
  - `mtime`: hash mtime and size of the compiler binary (default; cheap, no file read).
  - `content`: hash the compiler binary content (slightly slower).
  - `string:value`: hash the given string (for example a revision number).
  - `none`: hash nothing ("Use only if you know what you are doing").
  - any other string: treated as a command; its stdout and stderr are hashed; `%compiler%` is
    replaced by the compiler path; commands are separated by `;`.
- So the cheap identification of the compiler binary is size plus mtime by default, with
  `content`, a version string or a command output as stricter alternatives.

---

## 3. Build Systems a la Carte (ICFP 2018; JFP 2020 not verified)

Source read in full text: Mokhov, Mitchell, Peyton Jones, "Build Systems a la Carte", Proc. ACM
Program. Lang. 2, ICFP, Article 79 (2018).
https://www.microsoft.com/en-us/research/wp-content/uploads/2018/03/build-systems.pdf
JFP version: "Build systems a la carte: Theory and practice", JFP 30, e11 (2020),
DOI 10.1017/S0956796820000088;
https://microsoft.com/en-us/research/uploads/prod/2020/04/build-systems-jfp.pdf
UNRESOLVED: the JFP wording was not read (PDF text not extractable here; the Cambridge page
returned HTTP 429). A secondary search result says the JFP version is an expanded revision that
adds a practical-experience section; that is not a statement about changed definitions.

**Traces (ICFP s.4.2.2 to 4.2.4, verbatim):**
- Verifying trace (s.4.2.2): record "the values/hashes of dependencies used last time, and if
  something has changed, the key is dirty and must be rebuilt". "Rather than storing (large)
  values v, the verifying trace VT stores only hashes, of type Hash v, of those values." It is
  "the build system's 'memory'". Operations: `recordVT`, `verifyVT`.
- Constructive trace (s.4.2.3): "A verifying trace deliberately records only small hashes... A
  constructive trace additionally stores the resulting value. Once we are storing the complete
  result it makes sense to record many constructive traces per key, and to share them with other
  users, providing cloud-build functionality." Operations: `recordCT`, `constructCT` (returns a
  list of suitable values; empty list means rebuild).
- Deep constructive trace (s.4.2.4): "Constructive traces always verify keys by looking at their
  immediate dependencies... A deep constructive trace optimises this process by only looking at
  the terminal input keys, ignoring any intermediate dependencies." The input-only variant is the
  case n = infinity; constructive traces are n = 1. "When n >= 2, deep constructive traces require
  the tasks to be deterministic, as otherwise it is possible to violate correctness". Also "they
  cannot support early cutoff". Table 2: verifying traces: Ninja, Shake; constructive: CloudBuild,
  Bazel; deep constructive: Buck, Nix.

**Correctness (s.3.6, Definition 3.1, verbatim):** "The build result is correct if the following
two conditions hold: result and store agree on inputs ... [and] the result is consistent with the
tasks, i.e. for all non-input keys k in O, the result of recomputing the corresponding task matches
the value stored in the result: `getValue k result == compute task result`." "A build system is
correct if it produces a correct result for any given tasks, key and store." Intuition given:
"if we recompute the value of the key (using the task description, and the final store), we should
get exactly the same value as we see in the final store." Correctness is stated only for acyclic
task descriptions.

**Non-deterministic tasks (s.6.3, verbatim):**
- Impurity categories: untracked dependencies ("C compilation will explicitly list the source.c
  file as a dependency, but it may not record that the version of gcc is also a dependency"),
  non-determinism ("producing a result from a possible set"), and volatility ("volatile tasks
  cannot be cached").
- "Most of the implementations in s.5 can deal with non-determinism, apart from Buck, which relies
  on deterministic tasks".
- Correctness is adjusted: instead of `getValue k result == compute task result`, "we now require
  that result contains one possible result of recomputing the task: `getValue k result `elem`
  computeND task result`".
- s.6.4 "Frankenbuild" example: a profiler output `main.prof` differs on each run; with deep
  constructive traces keyed only on the hash of terminal input `main.exe`, the cloud returns a
  `report.txt` inconsistent with a freshly built `main.prof`. "the resulting store is incorrect
  according to all three definitions of correctness".

---

## 4. git object storage

**Loose layout and hashing.** Pro Git (git-scm.com, the project's site): "The subdirectory is
named with the first 2 characters of the SHA-1, and the filename is the remaining 38
characters." Header: object type, a space, "the size in bytes of the content", and "a final null
byte"; "Git concatenates the header and the original content and then calculates the SHA-1
checksum". Content is zlib-compressed. (relayed) https://git-scm.com/book/en/v2/Git-Internals-Git-Objects
Source: `odb_loose_path()`/`fill_loose_path()` add a slash after the first byte; `hash_object_file()`
calls `format_object_header()` ("<type> <size>" plus NUL), then hashes the header, then the
content. https://github.com/git/git/blob/master/object-file.c (read raw: `hash_object_file` hashes
`hdr` then `buf`).
Hash-function-transition doc: "The SHA-1 name of an object is the SHA-1 of the concatenation of
its type, length, a nul byte" and the content (relayed).
https://github.com/git/git/blob/master/Documentation/technical/hash-function-transition.adoc

**Safe write: temp file in the target directory, then link or rename.**
- v2.30.0 `create_tmpfile`: temp name `tmp_obj_XXXXXX`, comment "This creates a temporary file in
  the same directory as the final 'filename'" (relayed). https://github.com/git/git/blob/v2.30.0/sha1-file.c
  Current master reworked this around object-database transactions and `tmp_objdir`
  (`odb_transaction_files_*`); the temp-file naming was not re-verified on master.
- `finalize_object_file_flags()` on master (read raw): "Move the just written object into its
  final resting place." It first tries `link(tmpfile, filename)`; on success `unlink_or_warn(tmpfile)`.
  If `link` fails with something other than `EEXIST` (comment: "Coda hack - coda doesn't like
  cross-directory links, so we fall back to a rename, which will mean that it won't be able to
  check collisions, but that's not a big deal. The same holds for FAT formatted media") it falls
  back to `stat(filename)` then `rename(tmpfile, filename)`. If the destination already exists
  (`EEXIST`) it calls `check_collision()` (byte-compares both files in 4096-byte chunks; error
  "files '%s' and '%s' differ in contents") unless `FOF_SKIP_COLLISION_CHECK`, retries up to 5
  times if the destination vanished, then unlinks the temp file. If the repo setting
  `OBJECT_CREATION_USES_RENAMES` is on, it goes straight to rename.
  Consequence stated by the code: the primary path never replaces an existing object; an
  identical existing object wins and the temp file is deleted.
  https://github.com/git/git/blob/master/object-file.c
- Existing objects are not rewritten; `freshen_loose_object` (v2.30.0) updates mtime of an
  existing loose object (relayed). v2.30.0 `sha1-file.c`.

**Durability.** `core.fsync`: "The default on most platforms is equivalent to
`core.fsync=committed,-loose-object`, which has good performance, but risks losing recent work in
the event of an unclean system shutdown." `core.fsyncMethod`: `fsync`, `writeout-only` ("data added
to the repository may not be durable in the event of a system crash"; default on macOS), `batch`
(loose objects only). (relayed) https://github.com/git/git/blob/master/Documentation/config/core.adoc
On master, in a transaction git issues "a full hardware flush against a temporary file" before
objects get their final names (code comment, relayed).

**Integrity on read / check.**
- `git fsck`: "Verifies the connectivity and validity of the objects in the database." and
  "git-fsck tests SHA-1 and general object sanity". Messages include `badObjectSha1` and
  `hash mismatch <object>` ("indicates a serious data integrity problem"). `--connectivity-only`
  does not read blobs: "Corruption in blob objects will not be detected at all." (relayed)
  https://git-scm.com/docs/git-fsck
- In code: `check_object_signature()` recomputes the hash and compares with the oid;
  `check_stream_oid()` errors "hash mismatch for %s (expected %s)"; `unpack_loose_rest()` errors
  "corrupt loose object '%s'" (relayed from `object-file.c`). Whether the ordinary read path
  (`git cat-file`, checkout) always verifies the hash was NOT established: UNRESOLVED (the
  relayed summary names `read_loose_object()` as hash-checking, which is the fsck/verification
  path).

---

## 5. `os.replace`, `os.rename`, Windows rename, fsync

**Python docs (3.15.2, read raw).** https://docs.python.org/3/library/os.html
- `os.rename`: "On Windows, if dst exists a FileExistsError is always raised." "On Unix, ... If
  both are files, dst will be replaced silently if the user has permission. The operation may fail
  on some Unix flavors if src and dst are on different filesystems. If successful, the renaming
  will be an atomic operation (this is a POSIX requirement)." "If you want cross-platform
  overwriting of the destination, use replace()."
- `os.replace`: "If dst exists and is a file, it will be replaced silently if the user has
  permission. The operation may fail if src and dst are on different filesystems. If successful,
  the renaming will be an atomic operation (this is a POSIX requirement)." The docs give no
  separate statement for Windows atomicity; the "POSIX requirement" wording is the only guarantee
  text.
- `os.fsync(fd)`: "Force write of file with filedescriptor fd to disk. On Unix, this calls the
  native fsync() function; on Windows, the MS _commit() function. If you're starting with a
  buffered Python file object f, first do f.flush(), and then do os.fsync(f.fileno())". Directory
  fsync is not mentioned in the Python docs.

**What backs it (CPython `posixmodule.c`, read raw).** On Windows `internal_rename()` sets
`flags = is_replace ? MOVEFILE_REPLACE_EXISTING : 0` and calls `MoveFileExW(src->wide, dst->wide,
flags)`; on other platforms it calls `rename()` (or `renameat()` with dir fds). Failure goes to
`path_error2`. https://github.com/python/cpython/blob/main/Modules/posixmodule.c

**Microsoft `MoveFileExW` (read raw).** `MOVEFILE_REPLACE_EXISTING`: "If a file named
lpNewFileName exists, the function replaces its contents with the contents of the
lpExistingFileName file, provided that security requirements regarding access control lists
(ACLs) are met." The page contains no sentence about atomicity, in either direction.
`MOVEFILE_WRITE_THROUGH`: "The function does not return until the file is actually moved on the
disk." https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw
UNRESOLVED: no Microsoft primary source found that states MoveFileExW replace is or is not atomic.
Tried: MoveFileExW page, FILE_RENAME_INFO page (documents `ReplaceIfExists`/`Flags` for
`FileRenameInfoEx` but gives no atomicity text).

**Target open on Windows.** No Python doc statement found (UNRESOLVED as documentation). Derived
chain:
- CPython `PC/errmap.h` maps `ERROR_ACCESS_DENIED` (5) and `ERROR_SHARING_VIOLATION` (32) to
  `EACCES`, which Python raises as `PermissionError`; `ERROR_ALREADY_EXISTS` (183) and
  `ERROR_FILE_EXISTS` (80) map to `EEXIST`.
  https://github.com/python/cpython/blob/main/PC/errmap.h
- Microsoft `CreateFileW`: `FILE_SHARE_DELETE` "Enables subsequent open operations on a file or
  device to request delete access... If this flag is not specified, but the file or device has
  been opened for delete access, the function fails. Note: Delete access allows both delete and
  rename operations." https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
- Git's own Windows code admits the failure mode (read raw, `compat/mingw.c`, `mingw_rename`):
  "In theory, we shouldn't get ERROR_ACCESS_DENIED because we always open files with
  FILE_SHARE_DELETE But in practice we cannot assume that Git is the only one accessing files, and
  other applications may not set FILE_SHARE_DELETE. So we have to retry." It then retries with
  `retry_ask_yes_no(... "Rename from '%s' to '%s' failed. Should I try again?")` and finally sets
  `errno = EACCES`. https://github.com/git/git/blob/master/compat/mingw.c
- Git does not use plain `MoveFileExW` first: it opens the source with `DELETE` and
  `FILE_SHARE_WRITE|FILE_SHARE_READ|FILE_SHARE_DELETE` and calls `SetFileInformationByHandle` with
  `FileRenameInfoEx` and flags `FILE_RENAME_FLAG_REPLACE_IF_EXISTS | FILE_RENAME_FLAG_POSIX_SEMANTICS`;
  on `ERROR_INVALID_PARAMETER`/`ERROR_NOT_SUPPORTED`/`ERROR_INVALID_FUNCTION` it falls back to
  `MoveFileExW(MOVEFILE_REPLACE_EXISTING | MOVEFILE_COPY_ALLOWED)`. Same file.
- Not verified by execution: whether a file opened with Python's `open()` on Windows is opened
  with `FILE_SHARE_DELETE` (not established here); so "a reader holding the target open makes
  `os.replace` raise PermissionError" is a derived expectation, not a tested fact.

**POSIX/Linux rename atomicity (read raw).**
- POSIX.1-2024 `rename()`: "if the directory entry named by new exists, it shall be removed and
  old renamed to new. In this case, a directory entry named new shall remain visible to other
  threads throughout the renaming operation and refer either to the file referred to by new or
  old before the operation began." "If the rename() function fails for any reason other than
  [EIO], any file named by new shall be unaffected."
  https://pubs.opengroup.org/onlinepubs/9799919799/functions/rename.html
- Linux `rename(2)`: "If newpath already exists, it will be atomically replaced, so that there is
  no point at which another process attempting to access newpath will find it missing. However,
  there will probably be a window in which both oldpath and newpath refer to the file being
  renamed." https://man7.org/linux/man-pages/man2/rename.2.html
- These texts promise atomic visibility, not durability.

**fsync and directory fsync (Linux `fsync(2)`, read raw).** "Calling fsync() does not necessarily
ensure that the entry in the directory containing the file has also reached disk. For that an
explicit fsync() on a file descriptor for the directory is also needed."
https://man7.org/linux/man-pages/man2/fsync.2.html
Windows has no documented directory-fsync equivalent in the sources read (UNRESOLVED);
`MOVEFILE_WRITE_THROUGH` is the documented flag for the move itself, and CPython does not set it.

---

## 6. CACHEDIR.TAG specification

Source (relayed): https://bford.info/cachedir/ (pytest links https://bford.info/cachedir/spec.html).
- File name `CACHEDIR.TAG`, placed in the cache directory; must be an ordinary file, not a
  symbolic link.
- "The first 43 octets must be: `Signature: 8a477f597d28d172789f06886806bc55`". Case matters,
  nothing may precede the "S", exactly one space after the colon, trailing newline not required.
- The remainder "should be a plain text file in UTF-8 encoding"; lines starting with `#` are
  comments to be ignored; applications are encouraged to add a comment pointing to the spec.
- Purpose: lets backup, transfer and synchronisation tools identify cache directories so users
  can skip them. Place it in the topmost directory whose contents are entirely cached data.
  Tags are hints, "never the final word"; tools should verify it is a regular file with the
  43-byte header and should tell the user which directories they skipped.
- Spec versions: 0.6 (2019-11-04, no substantive change), 0.5 (2004-10-27), ... 0.1 (2004-07-19).

---

## 7. How pytest and ruff make cache directories self-ignoring

**pytest** (`src/_pytest/cacheprovider.py`, relayed):
https://github.com/pytest-dev/pytest/blob/main/src/_pytest/cacheprovider.py
- `.gitignore` bytes: `b"# Created by pytest automatically.\n*\n"`.
- `CACHEDIR.TAG`: `Signature: 8a477f597d28d172789f06886806bc55`, then comment lines
  "# This file is a cache directory tag created by pytest." and
  "# For information about cache directory tags, see:" and "#<TAB>https://bford.info/cachedir/spec.html".
- Also writes `README.md` ("**Do not** commit this to version control.").
- Creation is atomic by construction: `_make_cachedir` makes a temp directory
  (`tempfile.mkdtemp(prefix="pytest-cache-files-", dir=target.parent)`), writes the three files
  into it, then `path.rename(target)`; if two processes race, the loser gets "Directory not empty"
  (ENOTEMPTY/EEXIST) which is ignored, and its temp dir is removed.
- Default directory `.pytest_cache`; under tox the default sits inside `TOX_ENV_DIR`.

**ruff** (`crates/ruff/src/cache.rs`, relayed): https://github.com/astral-sh/ruff/blob/main/crates/ruff/src/cache.rs
- `fn init(path)` does `fs::create_dir_all(path.join(VERSION))`, then `cachedir::ensure_tag(path)`,
  then writes `.gitignore` only if absent (`create_new(true)`) with
  `b"# Automatically created by ruff.\n*\n"`.
- `cachedir::ensure_tag` (crate cachedir 0.3.1, docs.rs, relayed): `HEADER` is the 43-byte
  `Signature: 8a477f597d28d172789f06886806bc55`; the doc comment says an existing `CACHEDIR.TAG`
  "regardless of its content" counts as success; `add_tag` opens with `create_new(true)`.
  The full file text the crate writes after the signature was not captured (UNRESOLVED, minor).
- Cache file writes use temp file plus rename: comment "Write the cache to a temporary file first
  and then rename it for an 'atomic' write." (`tempfile_in` in the same directory, then `persist`).
- Cache path is `<cache_dir>/<VERSION>/<key>` where `VERSION` is the ruff version and `key` hashes
  package root and settings. Per-file invalidation uses `FileCacheKey { file_last_modified,
  file_permissions_mode }`: mtime and permissions, no content hash and no size field.
  `CACHE_DIR_NAME` is `.ruff_cache`. `crates/ruff_cache/src/lib.rs` only computes the path.

---

## 8. Canonical JSON: RFC 8785 vs Python `json.dumps`

**RFC 8785 (relayed)** https://www.rfc-editor.org/rfc/rfc8785
- Purpose: a "hashable" canonical form; input restricted to I-JSON (s.3.1): no duplicate property
  names, strings expressible as Unicode, numbers expressible as IEEE 754 doubles (larger
  precision should be strings, Appendix D).
- s.3.1 note: Unicode string data is preserved "as is"; no normalization is applied.
- s.3.2.1: no whitespace between tokens.
- s.3.2.2.2 strings: specified escaping; lone surrogates must make the implementation fail.
- s.3.2.2.3 numbers: ECMAScript Number-to-string rules (ECMA-262 s.7.1.12.1); NaN and Infinity
  are errors.
- s.3.2.3: properties sorted recursively; names compared as UTF-16 code units (unsigned
  integers), locale independent; array order untouched.
- s.3.2.4: output encoded as UTF-8.

**Python (3.15.2 docs and `Lib/json/encoder.py`, relayed)**
https://docs.python.org/3/library/json.html and
https://github.com/python/cpython/blob/main/Lib/json/encoder.py
- `separators=(",", ":")`: "For the most compact JSON, specify `(',', ':')` to eliminate
  whitespace." This matches JCS on whitespace.
- `ensure_ascii=False`: "all characters will be outputted as-is, except for the characters that
  must be escaped: quotation mark, reverse solidus, and the control characters U+0000 through
  U+001F." The pure-Python regex is `[\x00-\x1f\\"\b\f\n\r\t]`. Whether the hex case of `\u00XX`
  escapes matches JCS was not checked.
- `sort_keys=True`: encoder does `sorted(dct.items())`. Python compares `str` "lexicographically
  using the numerical Unicode code points" (language reference, value comparisons,
  https://docs.python.org/3/reference/expressions.html). Docs note: "sort_keys sorts the keys
  before they are converted to strings, so numeric keys are sorted by value, not by their string
  representation."
- Floats: finite floats are emitted as `float.__repr__(o)` (encoder `floatstr`); the `json` docs
  do not describe float formatting.
- NaN/Infinity: by default `allow_nan=True` emits `NaN`, `Infinity`, `-Infinity`; the docs say
  "The RFC does not permit the representation of infinite or NaN number values." Duplicate names on
  input: last one wins; no exception by default.
- Large ints: "This module does not impose any such limits beyond those of the relevant Python
  datatypes"; docs warn about consumers using IEEE 754 doubles.
- Returns `str`, not bytes (UTF-8 encoding is the caller's step). No Unicode normalization appears
  in the encoder code read; the docs do not mention it.

**Gaps relative to JCS, derived from the two sources above (not executed):**
1. Key order: code point order (Python) vs UTF-16 code unit order (JCS) differ when keys mix
   supplementary-plane characters (above U+FFFF) with characters in U+E000 to U+FFFF. Agree
   otherwise (ASCII and BMP below U+D800).
2. Number text: Python uses `float.__repr__`; JCS uses the ECMAScript algorithm. Both are
   "shortest round-trip" style but the textual forms are specified by different algorithms; exact
   differences (exponent thresholds, `1.0` vs `1`) were not tested here. Python also emits integers
   of any size exactly, where JCS requires double-representable numbers.
3. Non-finite floats: Python default emits `NaN`/`Infinity`; JCS requires an error. `allow_nan=False`
   raises `ValueError` as JCS demands.
4. Lone surrogates: JCS requires failure; Python behaviour with `ensure_ascii=False` was not
   verified (UNRESOLVED).
5. Mixed-type or non-string keys: Python stringifies keys after sorting; JCS has only string
   names. Two different Python keys can map to one JSON name.
6. Unicode normalization: neither applies it. Two canonically-equivalent strings (for example NFC
   vs NFD) hash differently under both.
So the call `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` yields a stable,
whitespace-free, key-sorted text for the same Python object; it is not a conforming JCS
implementation.

---

## 9. Hash choice and domain separation

**NIST status of SHA-256.**
- NIST Hash Functions project page (relayed): SHA-256 row: collision resistance 128, preimage
  resistance 256, second preimage resistance "256 - L(M)" (bits), where L(M) = log2(len(M)/B) and
  B = 512 for SHA-256; values derived from Kelsey and Schneier (LNCS 3494, 2005). "The collision
  resistance strength in bits is equal to half of the output size of the hash function." "The
  preimage resistance strength in bits is equal to the output size". https://csrc.nist.gov/projects/hash-functions
- Approved hash algorithms are in FIPS 180-4 (SHA-1, SHA-224, SHA-256, SHA-384, SHA-512,
  SHA-512/224, SHA-512/256) and FIPS 202 (SHA-3) (relayed from the same page; links
  https://csrc.nist.gov/pubs/fips/180-4/upd1/final and https://csrc.nist.gov/pubs/fips/202/final).
  FIPS 180-4 PDF text itself was not read.
- SP 800-107 Rev. 1 originally held this table. NIST announced on 2022-12-20 it "has decided to
  withdraw" it and moved the supplementary material to the hash functions webpage (relayed)
  https://www.nist.gov/news-events/news/2022/12/withdrawal-nist-special-publication-800-107-revision-1
  The same page also says NIST "is planning to withdraw" it once a new CMVP Implementation Guidance
  is published. The PDF text of SP 800-107r1 was not readable here.
- SHA-1: "NIST deprecated the use of SHA-1 in 2011 and disallowed its use for digital signatures
  at the end of 2013"; transition away from SHA-1 "will be completed by December 31, 2030"
  (relayed). https://csrc.nist.gov/projects/hash-functions and
  https://csrc.nist.gov/news/2022/nist-transitioning-away-from-sha-1-for-all-apps
- A search summary (not a primary source) reports a 2^69 collision attack on SHA-1 per RFC 6194; not
  used further.

**Domain separation by type prefix, as practiced.**
- git hashes `"<type> <size>\0"` before the content (`format_object_header` + `hash_object_file`,
  quoted in Q4), so a blob and a tree with equal bytes get different names.
- REAPI makes `size_bytes` part of the digest (quoted in Q1).
- UNRESOLVED: a NIST primary-source quote using the term "domain separation" (SP 800-185 PDF was
  fetched but its text could not be extracted; its abstract page calls cSHAKE "a customizable
  variant of the SHAKE functions").
- git's own doc on SHA-1: "Over time some flaws in SHA-1 have been discovered", the 2017 SHAttered
  collision, "Git v2.13.0 and later subsequently moved to a hardened SHA-1 implementation by
  default", and in late 2018 "the project picked SHA-256 as its successor hash" (relayed).
  https://github.com/git/git/blob/master/Documentation/technical/hash-function-transition.adoc

---

## 10. Are failures cached?

**Bazel.**
- Client source `RemoteExecutionService.java` (relayed): `commitResultAndDecideWhetherToUpload`
  returns true only when `result.status().equals(SpawnResult.Status.SUCCESS) && result.exitCode()
  == 0`. `uploadOutputs` asserts `checkState(SUCCESS.equals(spawnResult.status()) &&
  spawnResult.exitCode() == 0, "shouldn't upload outputs of failed local action")`. Also
  `shouldUploadLocalResultsToRemoteCache` needs `--remote_upload_local_results` and no
  `no-remote-cache-upload` requirement; `checkForConcurrentModifications` can skip the upload.
  https://github.com/bazelbuild/bazel/blob/master/src/main/java/com/google/devtools/build/lib/remote/RemoteExecutionService.java
- Bazel docs page https://bazel.build/remote/caching does not mention failed actions (checked).
  Exclusion switches documented: tag `no-remote-cache`; `--remote_upload_local_results=false`.
- Protocol: `ExecuteResponse.status`: "If the status code is other than `OK`, then the result MUST
  NOT be cached." (relayed). Whether a successful execution with non-zero `exit_code` may be
  cached is not stated in the proto text read: UNRESOLVED from the spec; the Bazel client's own
  behaviour (above) is not to upload it.
- `download side`: "In case the action failed, download all outputs." (relayed, `shouldDownload`).
  Server-side behaviour on failed actions may differ per implementation; not researched.

**ccache.** Manual statistic: "The compilation failed. No result stored in the cache." Related
counters: "Preprocessing failed", "Compiler produced empty output". No option to cache failed
compiles is documented (relayed). https://ccache.dev/manual/latest.html

---

## 11. Non-determinism and caches keyed by inputs

Sources: https://reproducible-builds.org/docs/ (index) and linked pages (all relayed).
- Definition (/docs/definition/): "A build is reproducible if given the same source code, build
  environment and build instructions," any party "can recreate bit-by-bit identical copies of all
  specified artifacts." Build environment includes "dependencies and their versions, build
  configuration flags and environment variables".
- Timestamps (/docs/timestamps/): "Timestamps make the biggest source of reproducibility issues."
  "Many build tools record the current date and time." Remedy: `SOURCE_DATE_EPOCH`, seconds since
  1970-01-01 UTC.
- Randomness (/docs/randomness/): "Random data will make builds unreproducible and must be
  avoided."; remedy is a predetermined seed; GCC LTO writes random identifiers unless
  `-frandom-seed` is set. Embedded paths from temp files also vary.
- Deterministic build systems (/docs/deterministic-build-systems/): variance comes from "factors
  that are hard or impossible to control like the ordering of files on a filesystem or the current
  time"; Qt `rcc` embeds source mtime; CMake puts the build path in the environment; "Capture as
  little as possible from the environment."
- Other listed variance pages: file order (stable-inputs/stable-outputs), locales, timezones,
  archive metadata, build path, value initialization, version information.
- UNRESOLVED: no reproducible-builds.org page read mentions GUIDs or UUIDs by name (checked the
  randomness, timestamps, definition and deterministic-build-systems pages; other variance pages
  were not read).

**Sourced statements about implications for input-keyed caches:**
- Bazel docs: "If your build is reproducible, the outputs from one machine can be safely reused on
  another machine" (relayed, https://bazel.build/remote/caching).
- Build Systems a la Carte s.6.3: non-determinism requires the weaker correctness definition
  (result is one possible outcome); s.4.2.4 and s.6.4: input-keyed deep traces plus
  non-deterministic tasks can yield inconsistent combinations (Frankenbuild).
- REAPI `salt` and `do_not_cache` exist to namespace or exclude suspect results (Q1).

---

## Disagreements and OS/version differences

1. Rename atomicity. POSIX: the destination "shall remain visible ... refer either to" the old or
   new file. Linux `rename(2)` adds that for a moment both names refer to the same file. Python docs
   claim atomicity only as "this is a POSIX requirement" and are silent for Windows. Microsoft's
   `MoveFileExW` page is silent. CPython on Windows uses plain `MoveFileExW(MOVEFILE_REPLACE_EXISTING)`;
   git on Windows uses `FileRenameInfoEx` with `FILE_RENAME_FLAG_POSIX_SEMANTICS` first and falls
   back to `MoveFileExW`. No source read states Windows `os.replace` atomicity.
2. `os.rename` vs `os.replace`. On Windows `os.rename` raises `FileExistsError` if the destination
   exists; `os.replace` overwrites. On Unix both overwrite files silently.
3. Windows target in use. Rename or replace fails when a handle without `FILE_SHARE_DELETE` is
   open (CreateFileW docs). Python maps `ERROR_ACCESS_DENIED`/`ERROR_SHARING_VIOLATION` to
   `PermissionError`. Git admits it must retry because other applications "may not set
   FILE_SHARE_DELETE". Whether Python's own `open()` handles allow it was not established.
4. Overwrite policy. `os.replace` clobbers. git's finalize path uses `link()`, which never replaces,
   plus a byte compare on collision; it falls back to `rename()` (clobbering, no collision check)
   on Coda and FAT, per its own comment.
5. Durability vs atomicity. Rename sources promise visibility, not persistence. Linux `fsync(2)`
   says the directory entry may need a separate directory `fsync`. Python documents `os.fsync` only
   for files (`fsync()` on Unix, `_commit()` on Windows). git's default `core.fsync` excludes
   loose objects, with the stated risk of losing recent work after an unclean shutdown;
   `core.fsyncMethod` default is `writeout-only` on macOS.
6. git layout differs by version: v2.30.0 uses `create_tmpfile`/`tmp_obj_XXXXXX` in the object's
   own `objects/xx/` directory; current master uses object-database transactions and `tmp_objdir`.
   `core.fsyncObjectFiles` is deprecated in favour of `core.fsync`.
7. Failure caching. REAPI: non-`OK` status MUST NOT be cached; silent on non-zero `exit_code` with
   `OK` status. Bazel client does not upload unless `SUCCESS` and exit code 0. Bazel docs page does
   not state it. ccache stores nothing on failure.
8. Hash status. NIST announced SP 800-107r1 withdrawal on 2022-12-20 (wording "has decided" and
   "is planning" both appear on the same page); its SHA-256 strength figures are now on the CSRC hash
   functions page. SHA-1 transition end date is 2030-12-31.
9. Canonical JSON. Python `json.dumps` with the stated options differs from RFC 8785 on key
   ordering (code point vs UTF-16), number text (`float.__repr__` vs ECMAScript), NaN/Infinity
   (emitted by default vs error), integer size limits, and lone surrogates (unverified). Both skip
   Unicode normalization.
10. Cache identification of tools. ccache default identifies the compiler by size and mtime;
    Bazel docs say tools outside the workspace are not tracked; both can serve stale results if the
    tool changes without changing those attributes. (From Q1 and Q2 sources; no source compares the
    two directly.)
11. Directory self-ignore. pytest writes `.gitignore` unconditionally inside a temp directory then
    renames; ruff writes `.gitignore` only if absent and the tag only if absent. pytest's tag
    comment points to `https://bford.info/cachedir/spec.html`; the spec page read was
    `https://bford.info/cachedir/` (URL difference, same document assumed, not verified).
12. Document versions. ccache 4.14.2 manual and Python 3.15.2 docs were read; behaviour in older
    releases was not checked. Build Systems a la Carte: ICFP 2018 read, JFP 2020 not read.

## UNRESOLVED list (summary)

- JFP 2020 wording of trace definitions, correctness, non-determinism.
- Microsoft statement on atomicity of `MoveFileExW` replace.
- Python/Microsoft statement on behaviour when the `os.replace` target is open (only derived).
- Whether ordinary git object reads always verify the hash.
- NIST primary-source quote using "domain separation"; SP 800-107r1 and FIPS 180-4 PDF text.
- REAPI statement on caching non-zero `exit_code` results with `OK` status.
- Exact float and lone-surrogate output differences (not executed).
- Windows directory-fsync equivalent; ccache atomic-write behaviour (manual silent, source not read).
- GUID/UUID guidance on reproducible-builds.org.
- Ruff's complete CACHEDIR.TAG text beyond the signature line.
