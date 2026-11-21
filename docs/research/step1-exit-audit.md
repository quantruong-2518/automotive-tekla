# Step 1 exit audit: "each fallback path covered by a test; no silent failure"

Date: 2026-11-20. Branch `feat/reading-tools` at `f35da8c`. Auditor: independent agent, read-only
(no code changed). Scope: the Step-1 reading chain in `src/tekla_harness/` as planned in
`docs/roadmap.md` § "Step 1 — plan" (S1–S5), measured against the roadmap exit criterion (row 1),
the AGENTS.md rule "Never swallow an error. A fallback is logged (`read-log.json`) and lowers
confidence", and the exit codes 0/1/2/3.

## Verdict: CLOSE AFTER FIXES

Every converter, cache, header-units, xref, dimension-override, scale, encoding and
section-failure path of the chain is exercised by a passing test, and almost every degraded path
reaches `read-log.json` or a blocking question. The criterion is not met to the letter:

- 1 Major gap: a `.dwg`/`.dxf` whose bytes are not DWG/DXF (empty, garbage, broken header, UTF-8
  BOM) is logged as "no reader implemented for other yet" and intake exits **0**, against the
  intake contract "exit 1: a supported-format file (dwg, dxf) could not be read"
  (`intake.py:29-32`). Not silent, but wrong exit code and a wrong remedy in the question.
- 4 silent handlers (one Step-1 OCS fallback, one dimension-text style fallback, and two groups of
  `rmtree(ignore_errors=True)`), all Minor; they are 3 gaps (m3, m10, m11).
- 12 further Minor gaps (m1, m2, m4–m9, m12–m15): a counted/warned fallback or an error exit
  with no test (confirmed by branch coverage, Appendix B), a partial read that keeps
  `max_confidence` at `high`, an unresolved xref not named in the read log, a crash that exits 1,
  and one doc drift.

All fixes are small (one condition, one warning, or one test each). None needs a capability that
is not built. Gap counts: **Critical 0 · Major 1 · Minor 15**. PDF, image, DOCX and XLSX readers
are not in the written S1–S5 plan (see Scope notes); they do not block this verdict.

Evidence runs: targeted Step-1 tests `595 passed, 2 skipped in 13.99s` (command in Appendix A);
full suite under `coverage run --branch`: `4708 passed, 18 skipped in 298.60s (0:04:58)`
(Appendix B).

## 1. Fallback / degraded path table

Legend. **Log**: what reaches `read-log.json` (attempt with `error`, `warnings`, `outcome`), or
"Q" for a question in `questions.json` only. **Conf**: effect on `max_confidence` (read-log) or on
per-value confidence. **Exit**: `harness intake` exit code for a run whose only problem is this
path (`harness dwg2dxf`/`probe-dxf` noted where they differ). Test ids are pytest node ids under
`tests/`; every one listed passed in the runs of Appendix A/B.

### 1.1 Input detection and sha256 (S1)

| # | Path | Code | Test(s) | Log | Conf | Exit | Status |
|---|---|---|---|---|---|---|---|
| 1 | sha256 of every input file | `detect.py:44-49`, `intake.py:575` (read-log `sha256`) | `test_detect.py::test_sha256_matches_hashlib`, `test_intake.py::test_read_log_outcomes_attempts_and_formats` | yes | — | 0 | OK |
| 2 | Unknown DWG version string | `detect.py:94-95` | `test_detect.py::test_unknown_dwg_version_is_warned_not_guessed` | warning (`intake.py:334`) | none (conversion is still validated by ezdxf, `convert.py:284`) | 0 | OK |
| 3 | Extension disagrees with content (content wins) | `detect.py:107-111` | `test_detect.py::test_extension_mismatch_is_warned` | warning | — | 0 | OK |
| 4 | Input file cannot be read (OSError while hashing) | `intake.py:213-216` | none at intake level (probe-level twin: `test_read_dxf.py::test_cli_unhashable_file_is_environment_error`) | nothing written | — | 3 | **GAP-m6** (no intake test) |
| 5 | Empty file, or `.dwg`/`.dxf` whose bytes are not DWG/DXF (garbage, broken `AC10xx` header, UTF-8 BOM) | `detect.py:88-89, 104-105`; `intake.py:354-360`, `536` | `test_detect.py::test_empty_and_unknown_files` (detect only) | attempt `intake_no_reader` failed "no reader implemented for other yet"; `no_reader_implemented` blocking Q | none (unreadable) | **0** | **GAP-M1** (reproduced, Appendix C) |
| 6 | PDF / image / DOCX / XLSX / other: no reader | `intake.py:78-81, 354-360` | `test_intake.py::test_read_log_outcomes_attempts_and_formats`, `::test_exit_code_rule`, `::test_no_reader_question_is_blocking_and_one_per_file` | attempt failed + warning "PDF type … not determined"; blocking Q | unreadable | 0 (by design, `intake.py:31-32`) | OK (declared) |
| 7 | Corrupt ZIP (`.docx`/`.xlsx`) | `detect.py:65-66` | none (`test_detect.py::test_docx_and_xlsx` covers valid ZIPs only) | becomes row 5/6 ("other", mismatch warning) | — | 0 | OK (no reader exists; Minor test gap folded into GAP-M1 test) |

### 1.2 DWG → DXF chain (S2, ADR-0005)

| # | Path | Code | Test(s) | Log | Conf | Exit | Status |
|---|---|---|---|---|---|---|---|
| 8 | No converter configured or on PATH, DWG present | `intake.py:665-669`; `convert.py:457-461`; `cli.py:202-203` | `test_intake.py::test_no_converter_with_dwg_is_environment_error_and_writes_nothing`, `test_convert.py::test_no_converter_configured_is_environment_error`, `::test_cli_exit_codes` | nothing written (by design) | — | 3 | OK |
| 9 | ODA not configured, LibreDWG only | `convert.py:306-309` | `test_intake.py::test_read_log_outcomes_attempts_and_formats` (asserts the fallback warning, not the "not configured; skipped" text) | warning | medium | 0 | OK |
| 10 | Converter binary missing | `convert.py:267-269` | `test_convert.py::test_missing_binary_is_a_recorded_failure`, `test_intake.py::test_oda_failure_falls_back_and_keeps_both_attempts` | failed attempt + error | fallback → medium | 0 | OK |
| 11 | Converter not executable / exec-format error | `convert.py:270-272` | `test_convert_cache.py::test_unexecutable_converter_is_a_recorded_failure` | failed attempt + error | fallback | 0 | OK |
| 12 | Non-zero exit | `convert.py:274-276` | `test_convert.py::test_oda_failure_falls_back_to_libredwg_with_medium_cap[exit_1-exit code 1]`, `test_intake.py::test_read_log_outcomes_attempts_and_formats` (`sub/bad.dwg`) | failed attempt + error | fallback | 0 / 1 if last | OK |
| 13 | Timeout | `convert.py:264-266` | `test_convert.py::test_oda_failure_falls_back_to_libredwg_with_medium_cap[timeout-timed out]` | failed attempt "timed out after N s" | fallback | 0 | OK (unit level only; the read-log write is the shared attempt path of row 12) |
| 14 | Exit 0, no DXF written | `convert.py:277-279` | `…[no_output-no DXF]` | failed attempt | fallback | 0 | OK |
| 15 | Exit 0, zero-byte DXF | `convert.py:277` (`st_size == 0`) | none | failed attempt | fallback | 0 | **GAP-m7** (branch untested) |
| 16 | Exit 0, DXF not openable (garbage, binary, truncated) | `convert.py:284-288` | `…[garbage_output-cannot be opened]`, `…[binary_output-cannot be opened]`, `…[truncated_output-cannot be opened]`, `test_convert.py::test_both_fail_means_unreadable` | failed attempt | fallback | 0 | OK |
| 17 | DXF opens but has no entities, DWG > 10 KiB | `convert.py:289-291, 231-236`; `intake.py:509-520` | `test_convert.py::test_empty_layouts_from_large_dwg_is_partial_and_low`, `test_intake.py::test_empty_conversion_is_partial_low_and_blocking` | attempt `partial` + warning; outcome `partial`; blocking `conversion_empty` | **low** | 0 | OK |
| 18 | Exit 0 with `ERROR` lines on stderr | `convert.py:219-230` | `test_convert.py::test_error_lines_on_success_are_counted_and_warned`, `::test_error_lines_lower_oda_cap_one_step`, `test_intake.py::test_converter_error_lines_make_the_file_partial` | warnings; outcome `partial`; `converter_errors` Q | one step lower (high→medium) | 0 | OK |
| 19 | Fallback to LibreDWG succeeds | `convert.py:313-318`; `read_dxf.py:1398-1399` | `test_convert.py::test_oda_failure_falls_back_to_libredwg_with_medium_cap` (all 6 parametrizations), `test_read_dxf.py::test_confidence_cap_follows_converter` | warning "fallback converter … capped at medium" | **medium** | 0 | OK |
| 20 | All converters fail | `convert.py:328`; `intake.py:345-349, 778` | `test_convert.py::test_both_fail_means_unreadable`, `test_intake.py::test_exit_code_rule`, `::test_read_failed_question_names_the_conversion` | every attempt + error; outcome `unreadable`; blocking `read_failed` | unreadable | **1** | OK |
| 21 | Non-UTF-8 converter output | `convert.py:197-199` | `test_convert_cache.py::test_non_utf8_converter_output_is_a_recorded_failure` | recorded failure | fallback | 0 | OK |
| 22 | Output folder inside the input folder | `convert.py:448-449`; `intake.py:340-342` | `test_convert.py::test_out_dir_inside_input_is_refused`, `test_intake.py::test_work_folder_inside_or_equal_to_input_is_refused` | nothing written | — | 2 | OK |
| 23 | Converter temp/staging folder cannot be removed | `convert.py:248, 325, 471` (`rmtree(ignore_errors=True)`) | `test_convert_cache.py::test_work_folder_is_removed_when_try_raises` (removal succeeds; failure of removal untested) | **nothing** | — | 0 | **SILENT S3 / GAP-m3** |

### 1.3 Read cache (S2b, ADR-0006/0008)

Only `harness dwg2dxf --cache-dir` uses the cache; `harness intake` never passes one
(`intake.py:341`, no `cache` argument). So no cache path can reach `read-log.json` today.

| # | Path | Code | Test(s) | Log | Conf | Exit | Status |
|---|---|---|---|---|---|---|---|
| 24 | Hit: verified replay | `convert.py:381-404`, `cache.py:206-227` | `test_convert_cache.py::test_second_run_is_a_hit_and_runs_no_converter`, `::test_hit_preserves_provenance_and_cap`, `::test_hit_and_fresh_deliver_files_alike` | `cache.hit` in CLI JSON; no read-log field (ADR-0008 deferred item) | replays recorded cap | 0 | OK |
| 25 | Stale (input, converter, code or ezdxf changed) | key material `convert.py:163-176` | `::test_changed_input_content_invalidates`, `::test_changed_converter_binary_invalidates`, `::test_newly_available_converter_invalidates`, `::test_code_and_oracle_versions_are_in_the_key` | miss → fresh run | fresh | 0 | OK |
| 26 | Corrupt entry / blob, wrong key, unusable replay | `cache.py:217-227, 233-234`; `convert.py:399-400` | `test_cache.py::test_corrupt_blob_is_a_miss_and_is_removed`, `::test_damaged_entry_is_a_miss`, `::test_entry_under_the_wrong_key_is_a_miss`, `test_convert_cache.py::test_well_formed_but_wrong_entry_is_discarded_and_recomputed`, `::test_attempt_field_types_are_checked_on_replay` | stderr warning + invalidate | fresh | 0 | OK |
| 27 | Entry unreadable right now (sharing violation) | `cache.py:219-221` | `test_convert_cache.py::test_unreadable_blob_is_a_miss_and_keeps_the_entry` | stderr warning | fresh | 0 | OK |
| 28 | Fallback after a failure / failures never cached | `convert.py:405-429` | `::test_fallback_after_a_failure_is_never_cached`, `::test_failures_are_not_cached`, `::test_empty_output_from_a_large_dwg_is_never_cached` | warning "result not cached because …" | — | 0 | OK |
| 29 | Cache write fails | `convert.py:428-429` | `::test_cache_write_failure_keeps_the_conversion`, `::test_cache_failure_of_any_kind_still_delivers_the_dxf` | warning | unchanged | 0 | OK |
| 30 | Refresh cannot delete a locked entry | `cache.py:258-262`; `cli.py:208-210` | `::test_locked_entry_makes_refresh_fail_loudly` | stderr | — | 3 | OK |
| 31 | Directory fsync refused | `cache.py:93-104` | none | stderr warning | n/a (durability only; every read re-verifies) | 0 | **GAP-m8** (untested) |

### 1.4 DXF read: `probe_dxf` (S3, RTI-0002)

| # | Path | Code | Test(s) | Log | Conf | Exit | Status |
|---|---|---|---|---|---|---|---|
| 32 | ezdxf cannot open the DXF | `read_dxf.py:1293-1301`; `intake.py:309-311` | `test_read_dxf.py::test_unreadable_dxf_reports_error_in_json`, `::test_cli_unreadable_exits_one_with_json_and_stderr_note`, `test_intake.py::test_unopenable_dxf_is_unreadable` | failed `ezdxf` attempt + error; outcome `unreadable`; blocking `read_failed` | unreadable | 1 | OK |
| 33 | A probe section raises | `read_dxf.py:1229-1240, 1399-1421`; `intake.py:316-319` | `test_read_dxf.py::test_a_failing_section_gives_partial_status_not_a_crash` (all 6 parametrizations), `::test_failing_scan_marks_every_dependent_section`, `::test_failing_dimension_audit_keeps_units_and_skips_the_magnitude_check` | probe `partial` + `section_errors` + blocking `probe_section_failed`; read-log outcome `partial` + warning | **unchanged (`high` for a native DXF)** | 0 | **GAP-m1** (no intake-level test; cap not lowered) |
| 34 | Units section failed → inventory `units_not_read` | `intake.py:369-376` | none | inventory row only | low (units) | 0 | **GAP-m2** (untested) |
| 35 | `$INSUNITS` missing | `read_dxf.py:284-285, 311-321` | `test_read_dxf.py::test_missing_insunits_is_unknown_and_blocking` | blocking `units_unknown` → folded into `units_confirm_all` | low | 0 | OK |
| 36 | `$INSUNITS` 0, invalid, float, non-building code | `read_dxf.py:124-130, 286-298` | `::test_insunits_zero_is_unknown_and_blocking`, `::test_invalid_insunits_codes_are_unknown_with_null_code`, `::test_float_insunits_in_header_is_unknown`, `::test_units_outside_building_set_are_unknown_not_nearest` | blocking Q | low | 0 | OK |
| 37 | Header unit present (never trusted alone) | `read_dxf.py:322-334`; `intake.py:428-460` | `::test_known_units_always_ask_for_confirmation_non_blocking`, `test_intake.py::test_one_units_question_per_dxf`, `::test_units_evidence_folds_into_the_one_units_question_with_true_counts` | blocking `units_confirm_all` per file | ≤ medium | 0 | OK |
| 38 | `$MEASUREMENT` conflicts with `$INSUNITS` | `read_dxf.py:335-350` | `::test_measurement_conflict_lowers_confidence_and_blocks`, `::test_imperial_unit_with_metric_measurement_conflicts` | blocking Q | low | 0 | OK |
| 39 | Implausible dimension magnitude for the declared unit | `read_dxf.py:387-419` | `::test_implausible_magnitude_is_suspect_and_blocking`, `::test_magnitude_counts_only_modelspace_linear_dimensions` | blocking `units_suspect` | low | 0 | OK |
| 40 | Unresolved xref | `read_dxf.py:584-614`; converted DWG looked up beside the DWG `intake.py:352-353` | `::test_xref_resolution_only_next_to_the_dxf`, `::test_xref_dir_replaces_the_dxf_folder_for_converted_files`, `test_intake.py::test_xrefs_of_a_converted_dwg_are_looked_up_next_to_the_original_dwg` | blocking `xref_unresolved`; the read log only gets the text-index note that xref INSERTs were not indexed (`extract_text.py:1315-1317`), not that the file is missing | unchanged | 0 | OK (see GAP-m9) |
| 41 | Overridden dimension text differs from geometry (RTI-0002 regression test) | `read_dxf.py:1109-1163` | `::test_override_that_differs_is_flagged_and_equal_is_ok`, `::test_questions_cover_all_flagged_rows_not_only_the_listed_ones`, `::test_question_count_is_capped_with_a_warning`, `::test_group_42_disagreement_makes_every_row_not_compared` | row `override_differs` + non-blocking Q per dimension; inventory count | value flagged (not a file cap) | 0 | OK |
| 42 | Dimension cannot be audited | `read_dxf.py:1029-1040, 1116-1119` | `::test_error_row_keeps_the_real_dimension_type`, `::test_dimdec_out_of_range_is_not_compared` | row status `error` + warning | row not compared | 0 | OK |
| 42a | Dimension type unreadable inside an error row; DIMSCALE unreadable | `read_dxf.py:1033-1034`, `1099-1101` | none (both uncovered, Appendix B) | `dim_type unknown`; warning | row/scale dropped from count | 0 | **GAP-m4** |
| 43 | Several scales (DIMSCALE, viewports) | `read_dxf.py:1185-1226` | `::test_multiple_dimscale_is_flagged`, `::test_multiple_viewport_scales_are_flagged`, `::test_dimscale_and_viewport_scale_are_not_pooled` | non-blocking `multiple_scales` | unchanged | 0 | OK |
| 44 | Paper space vs model space | `read_dxf.py:457-481` (layouts, viewports), magnitude on modelspace only | `::test_layouts_and_viewports`, `::test_viewport_with_zero_view_height_has_null_scale_and_reason`, `::test_magnitude_counts_only_modelspace_linear_dimensions` | facts in probe | — | 0 | OK |
| 45 | Unreadable objects (proxy, OLE, …) | `read_dxf.py:841-857` | `::test_unreadable_objects_are_listed_explicitly`, `::test_raw_objects_are_counted_by_type_and_only_content_bearing_ones_ask` | listed + Q | unchanged | 0 | OK |
| 46 | R12-era file without handles | `read_dxf.py:1310-1315` | `::test_r12_without_handles_reports_null_handles_not_synthesized_ones` | warning | — | 0 | OK |
| 47 | Bytes that are not valid UTF-8 | `read_dxf.py:1259-1264`; `extract_text.py:712-714` | `::test_undecodable_bytes_in_a_name_are_scrubbed_with_a_warning`, `test_intake.py::test_a_dxf_with_undecodable_bytes_is_still_written_and_flagged` | warning; flag `invalid_utf8_bytes` | entry low | 0 | OK |
| 48 | Malformed knowledge table | `intake.py:652-655`; `read_dxf.py:1247-1249` | `test_read_dxf.py::test_a_bad_default_knowledge_table_raises_instead_of_a_section_error`, `test_intake.py::test_a_bad_knowledge_table_stops_the_run_and_writes_nothing` | nothing written | — | 1 | OK |

### 1.5 Font / encoding gate (S4, RTI-0004)

| # | Path | Code | Test(s) | Log | Conf | Exit | Status |
|---|---|---|---|---|---|---|---|
| 49 | TCVN3 (`.VnTime`) / VNI text → Unicode (RTI-0004 regression test) | `extract_text.py` decode order, `encoding.convert_legacy` | `test_extract_text.py::test_tcvn3_in_a_lowercase_font_is_converted`, `::test_vni_text_is_converted`, `::test_tcvn3_capital_font_uppercases_and_flags_lowercase_ascii`, `test_encoding.py` (40 tests) | text index | ≤ medium (`extract_text.py:489-493`) | 0 | OK |
| 50 | Unknown encoding, non-ASCII text | `extract_text.py:494`; `intake.py:479-493`; `text_gate.py:56-59` | `test_extract_text.py::test_font_unknown_never_converts_and_lowers_confidence`, `test_intake.py::test_questions_group_unknown_encodings_and_proposed_rows`, `test_text_gate.py::test_non_ascii_text_of_unsettled_encoding_is_blocked`, `test_legacy_text_stays_blocked.py` (6 tests) | non-blocking `encoding_unknown_non_ascii`; meaning blocked | low | 0 | OK |
| 51 | Unicode evidence contradicts a legacy font | `text_gate.py:39-41` | `test_extract_text.py::test_unicode_in_a_legacy_font_style_is_not_converted_and_is_flagged` | flag | low/blocked | 0 | OK |
| 52 | Legacy-looking pure ASCII | `extract_text.py:570-590`; `read_dxf.py:753-791` | `test_extract_text.py::test_suspect_ascii_in_a_legacy_style_is_flagged_and_structural_ascii_is_not`, `test_intake.py::test_intake_asks_legacy_ascii_text_once_per_file_and_style`, `test_text_gate.py::test_ascii_text_flagged_as_legacy_looking_is_blocked` | Q per file and style | low/blocked | 0 | OK |
| 53 | Proposed / conflicting knowledge rows | `read_dxf.py:642-750` | `test_read_dxf.py::test_proposed_knowledge_row_changes_nothing_but_asks_with_its_evidence`, `::test_conflicting_approved_rows_leave_the_style_undecided_and_ask` | Q | blocked | 0 | OK |
| 54 | Code-page re-encode fails | `extract_text.py:270-272, 395, 469-470, 494` | none (`codepage_reencode_failed` appears in no test) | flag `codepage_reencode_failed` | low | 0 | **GAP-m5** (untested) |
| 55 | Unknown `%%` special code, NFD damage | `extract_text.py:494` | `::test_unknown_special_code_is_flagged_and_low`, `::test_nfd_damaged_legacy_text_is_low` | flag | low | 0 | OK |
| 56 | One entity fails during text extraction | `extract_text.py:1077-1078` | `test_extract_text.py::test_a_failing_entity_gives_partial_and_a_listed_error`, `test_intake.py::test_text_partial_status_makes_the_file_partial` | `summary.errors`; outcome `partial` + warning | **unchanged** | 0 | OK (cap: see GAP-m1) |
| 56a | An ATTRIB, a block expansion (`virtual_entities`), handle check or ATTDEF list fails | `extract_text.py:1008-1009`, `1052-1054`, `1253-1255`, `1293-1295` | none (all uncovered, Appendix B) | `summary.errors` / warning | unchanged | 0 | **GAP-m4** |
| 57 | Text index unreadable although the probe opened the file | `intake.py:262-265` | `test_intake.py::test_an_unreadable_text_index_raises_no_legacy_ascii_text` | warning; outcome `partial` | unchanged | 0 | OK (cap: see GAP-m1) |
| 58 | OCS→WCS transform of a text point fails | `extract_text.py:609-616` | none | **nothing**: raw OCS point used as WCS | **unchanged** | 0 | **SILENT S1 / GAP-m10** |
| 59 | Dimension text-style override cannot be read | `extract_text.py:896-901` | none | **nothing**: `style=None`; `style_not_found` only fires when a style is named (`extract_text.py:715`) | non-ASCII → unknown/low; legacy-looking ASCII escapes `legacy_ascii_suspect` | 0 | **SILENT S2 / GAP-m11** |
| 60 | xref INSERT text not indexed | `extract_text.py:1010-1011, 1315-1317` | `test_extract_text.py::test_missing_block_and_xref_are_counted` | warning | — | 0 | OK |

### 1.6 Title-block inventory, grids, levels (S5, RTI-0001, RTI-0003)

| # | Path | Code | Test(s) | Log | Conf | Exit | Status |
|---|---|---|---|---|---|---|---|
| 61 | No sheet frame found | `sheets.py` (`sheets_not_detected`) | `test_sheets.py::test_non_sheet_shaped_rectangles_are_rejected`, `::test_a_schedule_table_is_not_a_sheet` | Q | — | 0 | OK |
| 62 | Two revisions / copies of one sheet number (RTI-0001 half) | `sheets.py:2030-2065` | `test_sheets.py::test_duplicate_sheet_number_is_a_blocking_question` | blocking Q | — | 0 | OK |
| 63 | Sheet number or revision not found | `sheets.py:2066-2080` | `test_sheets.py::test_missing_number_and_revision_are_questions` | Q | — | 0 | OK |
| 64 | Missing sheet vs drawing list (RTI-0001 other half) | `sheets.py:79-80, 2130-2131` (`drawing_list.status = "not_searched"`) | none | declared in output | — | 0 | Not built (Scope note 3) |
| 65 | INSERT expansion / rectangle read raises (sheets) | `sheets.py:366-368, 1629-1631`, reported `2110-2111` | none (`expand_error`, `rect_error` in no test) | warning in sheets doc | unchanged | 0 | **GAP-m4** (untested) |
| 66 | No grid found | `grids.py` (`grid_none_found`) | `test_grids.py::test_no_grid_found` | Q | — | 0 | OK |
| 67 | Grid entity read raises | `grids.py:690-691`, reported `2379-2380` | none (`read_error:` in no test) | warning | unchanged | 0 | **GAP-m4** |
| 68 | No level found | `levels.py` (`level_none_found`) | `test_levels.py::test_no_level_found`, `::test_only_blocked_level_texts_give_no_candidate_and_say_so` | Q | — | 0 | OK |
| 69 | Level-symbol block entity raises | `levels.py:258-259`, reported `362-363` | none | warning | unchanged | 0 | **GAP-m4** |
| 70 | Grid section missing at gate 1 (RTI-0003 regression test) | `status.py`, grid gate | `test_grid_gate.py::test_world3_is_blocked_by_the_missing_grid_only`, `::test_a_used_system_without_a_tekla_grid_blocks_gate1` | gate blocked | — | — | OK |
| 71 | read-structure: input changed since intake, missing/invalid text index | `structure.py` | `test_structure.py::test_changed_input_dxf_is_exit_1_and_nothing_is_written`, `::test_missing_text_index_file_is_exit_1`, `::test_invalid_inventory_is_exit_1` | nothing written | — | 1 | OK |
| 71a | read-structure skips a file: DWG not converted, no text index; or the probe / converted DXF is missing or unreadable | `structure.py:316-318, 321-329, 333-335, 348-350` | none (uncovered, Appendix B); only the non-DWG/DXF skip (`313-315`) and the unreadable-probe skip (`330-332`) run | stderr + `structure-summary.json` (skip) or exit 1 (problem) | — | 0 / 1 | **GAP-m15** |
| 72 | Stale work subfolders cannot be cleared on rerun | `intake.py:702`, `structure.py:563` (`rmtree(ignore_errors=True)`) | `test_intake.py::test_rerun_into_same_folder_leaves_no_stale_files`, `test_structure.py::test_stale_structure_files_are_removed` (success only) | **nothing** | — | 0 | **SILENT S4 / GAP-m3** |

### 1.7 Read-log integrity and process exit

| # | Path | Code | Test(s) | Status |
|---|---|---|---|---|
| 73 | Failed attempt without an error, entry without attempts, duplicate file, schema-invalid log: never written | `readlog.py:94-100, 119-125`; `intake.py:731-735, 752-755` | `test_readlog.py::test_failed_attempt_needs_an_error`, `::test_entry_without_attempts_is_rejected`, `::test_same_file_twice_is_rejected`, `::test_invalid_log_is_not_written`, `::test_exception_inside_attempt_is_recorded_and_reraised` | OK |
| 74 | Uncaught exception in any command | `cli.py:928-951` (no catch-all) | none | traceback on stderr, exit **1**, which reads as "validation failure" (ADR-0008 deferred finding, still open) — **GAP-m12** |

## 2. Silent-failure sweep (`src/tekla_harness/*.py`)

Method: `grep -cE "^\s*except\b"` over the 39 modules gives 201 handlers in 34 modules (an
unanchored grep gives 209 hits; 8 are prose in docstrings and comments). There is no bare
`except:`, no `contextlib.suppress` and no `pass` in a handler. Each handler body was read with its
caller where the body did not obviously re-raise or record. A second grep for
`rmtree(…, ignore_errors=True)` added 5 swallow sites. "Step-1" = part of the S1–S5 chain.

### 2.1 SILENT or borderline (one row each)

| Id | Site | Step-1 | What is swallowed | Class |
|---|---|---|---|---|
| S1 | `extract_text.py:609-616` `_point` | yes | Any error of `ocs.to_wcs`; the raw OCS point is returned as a WCS point with no flag, counter or warning. A text on an extruded/mirrored OCS would be placed wrongly and still feed sheet assignment, marks and grids. | **SILENT** |
| S2 | `extract_text.py:896-901` `_dimension` | yes | Error reading the dimension's `dimtxsty` override; style becomes `None` silently. Non-ASCII text then decodes as unknown (low, blocked: self-limiting), but pure-ASCII legacy-looking text skips `legacy_ascii_suspect` because no legacy style is known. | **SILENT** (narrow) |
| S3 | `convert.py:248, 325, 471` `rmtree(ignore_errors=True)` | yes | Failure to delete a converter work folder or the staging folder. Each holds a copy of a client drawing in the system temp folder (ADR-0008: "a converter's work folder is removed on every exit path"). Not a reading error; a confidentiality leftover with no warning. | **SILENT** |
| S4 | `intake.py:702`, `structure.py:563` `rmtree(ignore_errors=True)` | yes | Failure to clear `converted/`, `probe/`, `text/`, `structure/` before a rerun. New files overwrite by name; files of a removed input could stay. Readers index by `inventory.json`, so they are not read, but nothing says they are there. | **SILENT** (low impact) |
| B1 | `detect.py:65-66` | yes | `BadZipFile` → kind `other`. Logged through the extension-mismatch warning and the no-reader attempt. | OK (becomes GAP-M1 bucket) |
| B2 | `answers.py:303-304` `_raised_question` | no (Step 2 ledger) | An unreadable question document is skipped; the answer is then refused with "question not found"-style errors (`answers.py:330-336`) that do not name the damaged file. | borderline, not Step 1 |
| B3 | `status.py:338-339, 486-487, 513-514` | no | `grid-systems.json` / `inventory.json` unreadable → empty result; docstrings say "the outputs check says so". | OK (documented, Step 2) |
| B4 | `worklock.py:95-96` | no | Unreadable holder record → `None` (informational only, docstring). | OK |
| B5 | `saved_evidence.py:145-146` | no | `ReaderError` → `None`; docstring: the computation then fails with its own message. | OK |

### 2.2 OK handlers, by module (logged and re-raised, or recorded as data)

| Module | Lines | Rule met |
|---|---|---|
| `readlog.py` | 71 | marks attempt failed, re-raises |
| `convert.py` | 247 (re-raise), 264, 267, 270, 286 (failed attempt + error), 399 (invalidate + stderr), 428 (warning) | recorded attempt / warning |
| `cache.py` | 96, 101, 145, 219 (stderr warning), 124 (identical-bytes check else raise), 217 (missing = miss), 222, 225 (invalidate + warning), 233 (raise `_Corrupt`), 261 (raise) | warned or raised |
| `intake.py` | 215, 249, 257, 290, 301, 342, 589, 607, 654, 673, 679, 696, 709, 733, 741, 754 | all raise `IntakeError` with exit 1/2/3 |
| `read_dxf.py` | 107 (number parse → None, caller treats as non-finite), 295 (unit name → evidence line), 1029/1033 (row status `error`), 1099 (warning), 1233 (`section_errors`), 1297 (failed attempt) | recorded |
| `extract_text.py` | 271, 290 (re-encode → `codepage_reencode_failed`, low; evidence logic), 1008, 1052, 1077 (`_record_error` → `summary.errors`, partial), 1050 (normal generator end), 1241, 1253, 1293 (failed attempt / status) | recorded |
| `encoding.py` | 595 | builds a code-point set: an unencodable byte is simply not in it (no data lost) |
| `sheets.py` | 212 (unit decode), 366, 1630 (counted in `skipped` → warnings `sheets.py:2110`), 1772 (warning) | counted + warned (untested: GAP-m4) |
| `grids.py` | 690 | counted → warning `grids.py:2379` (untested: GAP-m4) |
| `levels.py` | 258 | counted → warning `levels.py:362-363` (untested: GAP-m4) |
| `marks.py` | 578 | counted → `skipped` + warning `marks.py:933-936` |
| `geometry.py` | 225, 353 | `None` → counted in `noted` (`geometry.py:325-327, 340-342, 612-617`) |
| `render.py` | 217 | `_UNKNOWN` → entity kept and drawn (conservative), 528/530/562/717/806 raise or exit |
| `grid_system.py`, `callouts.py`, `contents.py`, `dimensions.py`, `findings.py`, `questions*.py`, `structure.py`, `status.py` (others), `ask.py`, `answers.py` (others), `lifecycle.py`, `knowledge.py`, `supplements.py`, `strict_json.py`, `receipt.py`, `sheet_text.py`, `marks.py` (others), `cli.py`, `worklock.py` (others) | every remaining handler | raise a typed error with an exit code, print to stderr and return 1/2/3, or append to a reported `problems`/`skipped` list |

## 3. Ranked gaps, smallest fix, regression test

### Critical

None.

### Major

**GAP-M1. A `.dwg`/`.dxf` that is not DWG/DXF inside exits 0 as "no reader implemented".**
Reproduced (Appendix C): `empty.dxf`, `garbage.dxf`, `badhead.dwg` (`XX1032…`) and a UTF-8-BOM DXF
(which ezdxf also refuses) all give `format other`, attempt `intake_no_reader` "no reader
implemented for other yet (roadmap)", blocking `no_reader_implemented` ("wait for the reader"),
exit 0. The intake contract (`intake.py:29-32`) says a supported-format file that cannot be read
is exit 1 with `read_failed`. Not silent, but the exit code hides a damaged client file from a
script, and the question gives the engineer the wrong remedy.
- Fix: in `intake._process` (`intake.py:354`), when `detect` kind is `other` and the extension is
  `.dwg`/`.dxf` (`detect._EXTENSION_KINDS`), set `read_failure` ("content is not DWG/DXF: …first
  bytes / empty file") with stage `detect` instead of `no_reader`. Optionally make `detect`
  classify a BOM-prefixed DXF and say so in a warning.
- Regression test: `test_intake.py::test_a_dwg_or_dxf_whose_bytes_are_not_that_format_is_a_read_failure`
  parametrized over empty, garbage, broken DWG header, BOM-prefixed DXF: exit 1, `read_failed`
  question, read-log outcome `unreadable` with the reason, no `no_reader_implemented`.

### Minor

**GAP-m1. Partial reads keep `max_confidence` at the converter cap.** A probe section failure
(row 33), a text-index entity failure (row 56) or an unreadable text index (row 57) set outcome
`partial` and add a warning, but `entry.cap` (`intake.py:320`) ignores them, so a native DXF reads
`outcome: partial, max_confidence: high`. AGENTS.md says a fallback "lowers confidence". The values
that failed are absent, not wrong, so this is a reading of the rule for the engineer.
- Fix: in `_run_probe`/`_run_text`, lower `entry.cap` one step (`high`→`medium`) when status is
  `partial`, and say so in the warning; or record the engineer's decision that `outcome: partial`
  is enough.
- Test: `test_intake.py::test_a_partial_probe_lowers_the_file_cap_and_warns` (monkeypatch a
  section as in `test_read_dxf.py::test_a_failing_section_gives_partial_status_not_a_crash`).
  This also closes the missing intake-level test of row 33.

**GAP-m2. `units_not_read` (row 34) is untested.** Fix: none in code. Test:
`test_intake.py::test_a_failed_units_section_reads_unknown_low_with_units_not_read` (monkeypatch
`read_dxf._units` to raise; assert inventory `units.flags` contains `units_not_read` and the
`probe_section_failed` question).

**GAP-m3. `rmtree(ignore_errors=True)` swallows cleanup failures (S3, S4).** Fix: replace with
`rmtree(path, onexc=…)` (Python ≥ 3.12) that appends a warning (conversion result warnings for
`convert.py`; stderr + summary warning for intake/structure). Tests:
`test_convert.py::test_a_work_folder_that_cannot_be_removed_is_warned` and
`test_intake.py::test_a_work_subfolder_that_cannot_be_cleared_is_warned` (monkeypatch
`shutil.rmtree` to call `onexc`).

**GAP-m4. Counted entity failures have no test (rows 42a, 56a, 65, 67, 69).** The code counts
and warns, but branch coverage shows the handler bodies never run: `extract_text.py:1008-1009,
1052-1054, 1253-1255, 1293-1295`; `read_dxf.py:1033-1034, 1099-1101`; `sheets.py:366-368,
1630-1632, 1772-1773`; `grids.py:690-691` and its warning `2380`; `levels.py:258-259` and its
warning `364`. Nothing proves the warning appears. Tests (monkeypatch the entity method to raise;
assert the count and the warning text):
`test_extract_text.py::test_an_attrib_or_block_expansion_that_fails_is_listed_and_partial`,
`test_read_dxf.py::test_an_unreadable_dimscale_is_warned_and_left_out`,
`test_sheets.py::test_an_insert_that_fails_to_expand_is_counted_and_warned`,
`test_grids.py::test_an_entity_that_fails_to_read_is_counted_and_warned`,
`test_levels.py::test_a_symbol_block_entity_that_fails_is_warned`.

**GAP-m5. `codepage_reencode_failed` (row 54) is untested.** Test:
`test_extract_text.py::test_text_that_cannot_be_reencoded_in_the_file_codepage_is_flagged_low`
(a `$DWGCODEPAGE` such as `ANSI_1258` plus a character outside it via `\U+` escape).

**GAP-m6. Intake: input file unreadable → exit 3 (row 4) is untested.** Test:
`test_intake.py::test_an_unreadable_input_file_is_exit_3_and_writes_nothing` (monkeypatch
`detect_file` to raise `PermissionError`).

**GAP-m7. Zero-byte converter output (row 15) is untested.** Test: add
`"zero_byte_output": "open(out_path, 'w').close()"` to `BEHAVIOURS` and to the parametrize list of
`test_convert.py::test_oda_failure_falls_back_to_libredwg_with_medium_cap` (expects "no DXF").

**GAP-m8. Cache warning paths are untested (row 31).** Uncovered: directory fsync
(`cache.py:93-102`), Windows replace race (`cache.py:124-130`), delete failure warning
(`cache.py:145-146`). Tests: `test_cache.py::test_a_refused_directory_fsync_is_warned_and_the_entry_is_kept`,
`test_cache.py::test_an_entry_that_cannot_be_deleted_is_warned_and_verified_again` (monkeypatch
`os.fsync` / `Path.unlink` / `os.replace` to raise).

**GAP-m9. An unresolved xref is not named in the read log.** It is a blocking question (row 40),
so the engineer sees it, but `read-log.json` for that file says `outcome: read`; its only trace is
the text-index warning that xref INSERTs were not indexed (`extract_text.py:1315-1317`), which
appears whether or not the xref file is found. Fix:
append a probe warning per unresolved xref in `_xrefs` so it reaches the read log. Test: extend
`test_intake.py::test_xrefs_of_a_converted_dwg_are_looked_up_next_to_the_original_dwg` with a
missing xref and assert the read-log warning.

**GAP-m10. OCS→WCS fallback is silent (S1, row 58).** Fix: on exception, count it
(`ctx.transform_failed`), add flag `ocs_transform_failed` and set the entry confidence to low; list
the count in `summary` and a warning. Test:
`test_extract_text.py::test_a_text_whose_ocs_cannot_be_transformed_is_flagged_low` (monkeypatch
`ocs()` to raise).

**GAP-m11. Dimension text-style fallback is silent (S2, row 59).** Fix: on exception add flag
`style_unreadable` (and a summary count). Test:
`test_extract_text.py::test_a_dimension_whose_text_style_cannot_be_read_is_flagged`.

**GAP-m12. An uncaught crash exits 1, like a validation failure (row 74).** ADR-0008 lists it as a
deferred review finding. Fix: in `cli.main`, catch `Exception`, print the traceback to stderr and
return a distinct code; the contract only has 0/1/2/3, so the smallest choice is exit 3 with
"internal error" (the engineer decides; it changes the AGENTS.md exit-code table if a new code is
used). Test: `test_cli.py::test_an_unexpected_exception_is_not_reported_as_a_validation_failure`.

**GAP-m14. Intake's own error exits are mostly untested.** Every one raises `IntakeError` with an
exit code (not silent), but these bodies never run: `intake.py:249-250, 290-291` (DXF unreadable
mid-run → 3), `204, 207` (work-folder path refused → 2), `253-254, 257-258, 297-298, 301-302, 628-629, 733-734` (self-check: invalid
probe/text/inventory/read-log → 1), `342-343` (converter refuses paths → 2), `589-590` (non-UTF-8
name → 1), `673-674, 741-742` (work folder not writable → 3), `709-710`. Fix: none in code. Tests:
one parametrized `test_intake.py::test_each_intake_error_exit_writes_nothing` that monkeypatches
`probe_dxf`/`extract_text`/`validate`/`Path.write_text` to fail and asserts the exit code and an
untouched work folder.

**GAP-m15. read-structure skip paths are untested (row 71a).** Tests:
`test_structure.py::test_a_dwg_that_did_not_convert_is_skipped_and_reported` and
`::test_a_file_without_text_index_is_skipped_and_reported` (intake with a failing converter, then
read-structure; assert the skip reason in `structure-summary.json`, stderr and exit 0).

**GAP-m13. Documentation drift.** `docs/workflow.md:24` lists "render to PDF/image" between
LibreDWG and "ask engineer"; ADR-0005 and `convert.py:328` go straight to "ask the engineer for a
DXF or PDF". Fix: align the workflow row with ADR-0005 (or record the render step as a later
slice). No test.

## 4. Scope notes (for the engineer to decide; none changes the verdict)

1. **PDF, image, DOCX, XLSX readers do not exist.** `detect.py` only classifies them
   (`detect.py:4`, `30-37`); intake logs them as `no reader implemented` with a blocking question
   and exit 0 (`intake.py:31-32, 354-360`). No `read_pdf` or `render_tiles` exists in `src/`
   (`docs/workflow.md:42-43` names them). The written Step-1 plan (`docs/roadmap.md:29-39`, S1–S5)
   is "DWG first, by engineer decision" and does not list any PDF, image or office reader, so
   their absence does not fail the Step-1 criterion as planned. The roadmap row 1 says "readers"
   generically and `docs/workflow.md` table rows for `.pdf`, images and `.docx/.xlsx` describe
   fallbacks that do not exist yet: the engineer decides whether they belong to Step 1 or a later
   step, and the roadmap should say so explicitly. (`render.py` renders DXF regions for Step-2
   reading; it is not a PDF reader.)
2. **The read cache is not wired into intake.** `harness intake` never passes `--cache-dir`
   (`intake.py:341`); only `harness dwg2dxf` uses it. ADR-0008's deferred item "read-log.json
   has no field for a cache hit yet" therefore stays open. Decide whether intake should use
   `projects/<id>/.cache` (ADR-0006) before or after closing Step 1.
3. **RTI-0001 is half built.** Hashing, the input diff (`intake.py:615-622`) and duplicate sheet
   numbers (row 62) exist; the comparison with the drawing list is declared not done
   (`drawing_list.status = "not_searched"`, `sheets.py:79-80`) and there is no "new revision"
   flow. Its regression test ("one missing sheet and two revisions → both blocking") is therefore
   only half present. The roadmap's S5 says "title-block inventory", which is built.
4. **Real conversion has only used LibreDWG.** All 87 `read-log.json` files under the main
   checkout's git-ignored `projects/` folder (runs and evals) show only `libredwg_dwg2dxf` attempts
   (86 with `ok`, 1 with `failed`) and no ODA attempt: ODA was never executed, and its argument order is still
   marked UNVERIFIED (`convert.py:9-11`, ADR-0005 Consequences). A wrong ODA command is not silent
   (row 12: recorded failure, fallback), but the high-confidence path is unproven on a real
   binary. Step 0's open item (env-check on the Tekla machine) is where this belongs.
5. RTI-0002 (`$INSUNITS`, overridden dimension text, xrefs, scales), RTI-0003 (grid section at
   gate 1) and RTI-0004 (`.VnTime` → Unicode) each have the regression test their entry asks for:
   rows 35-36/41/40/43, row 70 and row 49.

## Appendix A. Targeted test run

```
uv run pytest -q -x -p no:cacheprovider tests/test_detect.py tests/test_readlog.py \
  tests/test_convert.py tests/test_convert_cache.py tests/test_cache.py tests/test_intake.py \
  tests/test_extract_text.py tests/test_encoding.py tests/test_text_gate.py \
  tests/test_legacy_text_stays_blocked.py <24 named test_read_dxf.py ids> \
  tests/test_grid_gate.py::test_world3_is_blocked_by_the_missing_grid_only \
  tests/test_grid_gate.py::test_a_used_system_without_a_tekla_grid_blocks_gate1
→ 595 passed, 2 skipped in 13.99s
  (skips: Windows PATHEXT lookup; corpus test needs HARNESS_CORPUS_TESTS=1)

uv run pytest -q tests/test_grids.py::test_no_grid_found tests/test_levels.py::test_no_level_found \
  tests/test_sheets.py::test_duplicate_sheet_number_is_a_blocking_question \
  tests/test_sheets.py::test_missing_number_and_revision_are_questions \
  tests/test_sheets.py::test_non_sheet_shaped_rectangles_are_rejected
→ 5 passed in 1.01s
```

## Appendix B. Full suite and coverage

```
COVERAGE_FILE=<scratch>/.coverage uv run --with coverage \
  coverage run --branch --source=src/tekla_harness -m pytest -q -p no:cacheprovider
→ 4708 passed, 18 skipped in 298.60s (0:04:58)      (exit 0; run under coverage --branch)

coverage report -m --include=<the 13 Step-1 modules>
cache.py 88%   missing 64, 93, 96-98, 101-102, 124-130, 145-146, 185, 236, 257, 274, 295
convert.py 98%  missing 91, 117, 344
detect.py 98%   missing 65-66
encoding.py 100%; text_gate.py 100%; readlog.py 98% (109)
extract_text.py 95%  missing incl. 271-272, 395, 470, 614-615, 900-901, 1008-1009, 1052-1054,
                     1253-1255, 1293-1295
grids.py 95%    missing incl. 690-691, 2380
intake.py 91%   missing 204, 207, 215-216, 249-250, 253-254, 257-258, 290-291, 297-298, 301-302,
                317-318, 342-343, 371, 589-590, 628-629, 673-674, 709-710, 733-734, 741-742, 754-755
levels.py 91%   missing incl. 258-259, 364
read_dxf.py 96% missing incl. 295-296, 1033-1034, 1099-1101
sheets.py 92%   missing incl. 212-213, 366-368, 1630-1632, 1772-1773
structure.py 87% missing incl. 317-318, 321, 323-324, 327-329, 334-335, 344-346, 349-350
TOTAL (13 modules) 94%
```

Coverage shows a line ran, not that a test asserts it; the path table cites the asserting test.
Single-expression branches (`convert.py:277`, zero-byte output) do not show in coverage; GAP-m7
comes from reading the tests.

## Appendix C. GAP-M1 reproduction

```
mkdir -p in && : > in/empty.dxf && printf 'garbage not a dxf\n' > in/garbage.dxf
printf 'XX1032\x00\x00\x00' > in/badhead.dwg
uv run harness intake in --out work --project-id edge-test ; echo "exit=$?"
→ exit=0
  read-log: badhead.dwg  other unreadable "no reader implemented for other yet (roadmap)"
            ["file extension '.dwg' suggests dwg, content is other; content wins"]
            empty.dxf    other unreadable "no reader implemented for other yet (roadmap)" ['empty file']
            garbage.dxf  other unreadable "no reader implemented for other yet (roadmap)"
            ["file extension '.dxf' suggests dxf, content is other; content wins"]
  questions: no_reader_implemented (blocking) × 3
```

A valid R2018 DXF with a UTF-8 BOM prepended gives the same result (and `ezdxf.readfile` itself
raises "is not a DXF file" on it).
