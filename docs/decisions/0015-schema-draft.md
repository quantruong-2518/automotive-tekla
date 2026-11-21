# ADR-0015 draft: schema, examples and contract additions

Companion to [ADR-0015](0015-lot-spec-grids-levels-nonlinear-members.md) (status **Accepted**,
engineer, 2026-11-11), revised on 2026-11-11 for the review and the engineer's answers Q1–Q17 and
OQ-A–OQ-E. Nothing here is applied yet: the execution packages of the ADR apply it. `$id` stays
`urn:tekla-harness:schema:spec:0.1` (AGENTS.md), and the change gets a CHANGELOG entry.

**Checked on 2026-11-11** in the repo environment at 09274de. The check used
`tekla_harness.schemas.validate("spec", …)`: the schema plus the **current** `check_spec`, with ECMA
pattern translation. `_REPO_SCHEMAS` was pointed at a copy of `schemas/` holding the schema below,
and `_load_all.cache_clear()` was called.

These validate:
- the three examples below;
- the current `schemas/examples/spec.example.json` at schema level (it fails the extended rule (f)
  until it is updated, §3.4), and its updated version in §3.4;
- a one-direction grid (`y_lines: []`);
- `rotation_deg` 180.

These are rejected:
- `y_lines` with one line;
- a grid without `origin` or without `rotation_deg`;
- `rotation_deg` −180 or 181;
- lot 0 with members, and lot 0 without grids;
- lot 1 with grids, and lot 1 with nothing;
- a label with a space;
- an unknown key in a grid;
- a poly member with 2 points, an unknown chamfer, or of type `column`.

The new rules (a)–(h), (r) and (s) do **not** exist yet and were not run. A scratch probe of rules
(d) and (f) (member and poly member points included, OQ-B), the origin and provenance parts of (r),
and rules (h) and (s) passes on the four examples. It rejects the current `spec.example.json` under
rule (f), as expected. The execution package implements the rules and runs them on
every example plus one reject case per rule.

## 1. `schemas/spec.schema.json` (full replacement)

Additions against the current file:
- `lot` minimum `0`, and `members` without `minItems`;
- new optional `poly_members` and `grids`;
- the top-level `if`/`then`/`else`: lot 0 holds grids only; lots ≥ 1 hold no grids and at least one
  member or poly member;
- new `$defs` `poly_member`, `poly_point`, `grid` (with `origin`, `rotation_deg`, and `y_lines` empty
  or ≥ 2), `grid_line` and `grid_level`;
- the description.

The `member` definition is unchanged.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:tekla-harness:schema:spec:0.1",
  "title": "Lot spec",
  "description": "Everything the builder needs to create one lot. Units: millimetres, global coordinates unless a field says otherwise. Lot 0 is the setup lot: it holds grids only, and a grid's levels are its Z planes. Lots 1 and above hold members and poly_members, never grids (ADR-0015). Semantic rules not expressible here (spec_id unique across members, poly_members and grids; non-zero length and segment length; increasing grid positions on a 0.01 mm step; grid frame and level provenance; engineer answers carry their question_id; poly member point rules; low confidence anywhere in an item needs a question) are checked by tekla_harness.schemas.check_spec.",
  "type": "object",
  "required": ["schema_version", "project_id", "lot", "units", "members", "open_questions"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": "0.1"},
    "project_id": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/project_id"},
    "lot": {"type": "integer", "minimum": 0, "description": "0 = setup lot (grids only); 1 and above = member lots."},
    "units": {"const": "mm"},
    "description": {"type": "string"},
    "members": {"type": "array", "description": "Straight members, one start-end line each. Empty in lot 0.", "items": {"$ref": "#/$defs/member"}},
    "poly_members": {"type": "array", "description": "Members that are not one straight start-end line (Tekla PolyBeam). Absent or empty in lot 0.", "items": {"$ref": "#/$defs/poly_member"}},
    "grids": {"type": "array", "description": "Grids with their levels, each in its own frame (origin and rotation about +Z). Lot 0 only.", "items": {"$ref": "#/$defs/grid"}},
    "open_questions": {
      "type": "array",
      "description": "Question ids from questions.md that affect this lot.",
      "items": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/question_id"},
      "uniqueItems": true
    }
  },
  "if": {"properties": {"lot": {"const": 0}}, "required": ["lot"]},
  "then": {"required": ["grids"], "properties": {"grids": {"minItems": 1}, "members": {"maxItems": 0}, "poly_members": {"maxItems": 0}}},
  "else": {"properties": {"grids": {"maxItems": 0}}, "anyOf": [{"properties": {"members": {"minItems": 1}}}, {"required": ["poly_members"], "properties": {"poly_members": {"minItems": 1}}}]},
  "$defs": {
    "member": {
      "type": "object",
      "required": ["spec_id", "type", "profile", "material", "start", "end"],
      "additionalProperties": false,
      "properties": {
        "spec_id": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/spec_id"},
        "type": {"enum": ["column", "beam", "brace", "purlin", "girt", "rafter", "other"]},
        "mark": {"type": "string", "description": "Member mark as printed on the drawing, e.g. 'C1', 'B12'."},
        "profile": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_string"},
        "material": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_string"},
        "start": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_point"},
        "end": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_point"},
        "rotation_deg": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_number"},
        "name": {"type": "string"},
        "class": {"type": "string", "pattern": "^[0-9]{1,3}$"},
        "question_ids": {"type": "array", "items": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/question_id"}, "uniqueItems": true},
        "notes": {"type": "string"}
      }
    },
    "poly_member": {
      "type": "object",
      "description": "A Tekla PolyBeam through `points` in order. A 'none' point is a corner (Chamfer CHAMFER_NONE); an 'arc_point' point gets Chamfer CHAMFER_ARC_POINT, intended to make the run from the previous point through it to the next point one arc (ADR-0015 To verify T3). The first and last points are 'none'; two 'arc_point' points are never adjacent.",
      "required": ["spec_id", "type", "profile", "material", "points"],
      "additionalProperties": false,
      "properties": {
        "spec_id": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/spec_id"},
        "type": {"enum": ["beam", "brace", "purlin", "girt", "rafter", "other"], "description": "Harness kind; every value is built as PolyBeamTypeEnum.BEAM."},
        "mark": {"type": "string", "description": "Member mark as printed on the drawing."},
        "profile": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_string"},
        "material": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_string"},
        "points": {"type": "array", "minItems": 3, "description": "At least three points; a two-point member is a `members` item.", "items": {"$ref": "#/$defs/poly_point"}},
        "rotation_deg": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_number"},
        "name": {"type": "string"},
        "class": {"type": "string", "pattern": "^[0-9]{1,3}$"},
        "question_ids": {"type": "array", "items": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/question_id"}, "uniqueItems": true},
        "notes": {"type": "string"}
      }
    },
    "poly_point": {
      "type": "object",
      "description": "Global coordinates in millimetres, with the point's chamfer.",
      "required": ["x", "y", "z", "chamfer", "provenance", "confidence"],
      "additionalProperties": false,
      "properties": {
        "x": {"type": "number"},
        "y": {"type": "number"},
        "z": {"type": "number"},
        "chamfer": {"enum": ["none", "arc_point"]},
        "provenance": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/provenance"},
        "confidence": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/confidence"}
      }
    },
    "grid": {
      "type": "object",
      "description": "One Tekla Grid. Its frame: `origin` (global mm, z = 0) and `rotation_deg` (the angle from global +X to the grid's local x axis, counter-clockwise seen from +Z). Line positions are absolute distances from the origin along the local axes, never spacings; with origin (0, 0, 0) and rotation 0 they are global X and Y. Its levels are its Z planes, at global Z. `y_lines` empty = a one-direction grid (one family of parallel lines; ADR-0015 To verify T8). The CLI composes Origin, CoordinateX/Y (spacings from the first line, 2 decimals), CoordinateZ (absolute) and sets IsMagnetic false; a rotated grid is inserted in a work plane turned by rotation_deg (ADR-0015 decision 2, To verify T7).",
      "required": ["spec_id", "name", "origin", "rotation_deg", "x_lines", "y_lines", "levels"],
      "additionalProperties": false,
      "properties": {
        "spec_id": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/spec_id"},
        "name": {"type": "string", "pattern": "^\\S(.*\\S)?$", "description": "Tekla grid name; unique among the spec's grids. A harness choice, not a drawing value."},
        "origin": {
          "$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_point",
          "description": "Global point where the grid's local axes meet, mm; z must be 0 (check_spec). Confirmed by the engineer (provenance engineer_answer or derived from one)."
        },
        "rotation_deg": {
          "$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_number",
          "properties": {"value": {"exclusiveMinimum": -180, "maximum": 180}},
          "description": "Angle from global +X to the grid's local x axis, degrees, counter-clockwise seen from +Z, in (-180, 180]. 0 = axis-aligned. Confirmed by the engineer, like origin."
        },
        "x_lines": {
          "type": "array",
          "minItems": 2,
          "description": "Lines at constant local x (parallel to the local y axis), in increasing position: Tekla CoordinateX and LabelX. At least two.",
          "items": {"$ref": "#/$defs/grid_line"}
        },
        "y_lines": {
          "type": "array",
          "description": "Lines at constant local y (parallel to the local x axis), in increasing position: Tekla CoordinateY and LabelY. Empty (a one-direction grid) or at least two.",
          "anyOf": [{"maxItems": 0}, {"minItems": 2}],
          "items": {"$ref": "#/$defs/grid_line"}
        },
        "levels": {"type": "array", "minItems": 1, "description": "Level planes in increasing Z: Tekla CoordinateZ and LabelZ.", "items": {"$ref": "#/$defs/grid_level"}},
        "question_ids": {"type": "array", "items": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/question_id"}, "uniqueItems": true},
        "notes": {"type": "string"}
      }
    },
    "grid_line": {
      "type": "object",
      "required": ["label", "position"],
      "additionalProperties": false,
      "properties": {
        "label": {
          "$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_string",
          "properties": {"value": {"pattern": "^\\S+$"}},
          "description": "Axis label as printed, no whitespace (Tekla labels are space-separated)."
        },
        "position": {
          "$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_number",
          "description": "Absolute distance of the line from the grid origin along the local x axis (x_lines) or local y axis (y_lines), mm, on a 0.01 mm step. Never a spacing from the previous line (ADR-0015 decision 2)."
        }
      }
    },
    "grid_level": {
      "type": "object",
      "required": ["label", "z"],
      "additionalProperties": false,
      "properties": {
        "label": {
          "$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_string",
          "properties": {"value": {"pattern": "^\\S+$"}},
          "description": "Level label, no whitespace, e.g. '+3.600' as printed."
        },
        "z": {
          "$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_number",
          "description": "Global Z of the level plane, mm. Its provenance is the engineer's answer (method engineer_answer) or derived from one, since a drawing never says whether a level is structural or finished."
        }
      }
    }
  }
}
```

Note on `"$ref"` with a sibling `"properties"` (grid labels, `rotation_deg`): in 2020-12 both apply.
So the label keeps `sourced_string`'s shape and its `value` also gets the no-whitespace pattern. The
repo's ECMA-pattern translation (ADR-0010 A1 decision 10) rejects a label with a no-break space and
a name ending in a newline. The C# reader checks the same rules by hand.

## 2. `check_spec` additions (Python; ADR-0015 decision 6)

Rules (a)–(h), (r) and (s) of ADR-0015 decision 6, each with a regression test, and
`SPEC_RULES_VERSION` + 1 (one bump with ADR-0016's rules). Messages name the JSON pointer, as today.
- **Erratum (2026-11-11, review of P15-5 m-2).** Rule (g) also refuses two **consecutive** segments
  that fold back on each other (the second reverses the first), at any position including the
  first and last segment: point k+1 within 1 mm of segment [k-1, k], or point k-1 within 1 mm of
  segment [k, k+1]. The loop test on non-adjacent segments alone misses a reversal on the first
  or last segment. Closed outlines (ADR-0016 rule (l)) need nothing: a reversal there always lands
  on a non-adjacent edge. Approved by the engineer.
- **Tolerances.** 1 mm for every distance rule, as the existing member length rule uses. 0.1 mm
  where a value is meant to be equal (`origin.z` = 0).
- **Step (rule (d)).** A value v is on the 0.01 mm step when `abs(v·100 − round(v·100)) ≤ 1e-6`.
- **Provenance walk (rules (f), (r)).** A provenance passes when its `method` is `engineer_answer`,
  or when it is `derived` and any entry of `derived_from` passes, recursively at any depth.
- **Elevation paths (rule (f)).** `grids[*].levels[*].z`; `members[*].start` and `members[*].end`,
  except `.end` of a `pile` (the toe, ADR-0016 Q14); `poly_members[*].points[*]` (engineer,
  2026-11-11, OQ-B). A point carries one provenance for x, y and z, so the point's chain must reach
  an engineer answer (the storey-levels answer, directly or derived). ADR-0016 rule (p) adds its own
  paths.
- **Question ids (rule (s)).** Every object with a `method` key, at any depth of the spec, is
  checked: `engineer_answer` needs a non-empty `question_id`.
- **Low confidence (rule (h)).** The walk visits every object that holds a `confidence`, at any
  depth of an item. A low value needs a question in the item's `question_ids`, and every listed id
  must be in `open_questions`.
- **Coplanarity (rule (g)).** Every point lies within 1 mm of the plane through the first point and
  the two points that give the largest triangle. A poly member whose points are all collinear is
  refused: it is a straight `members` item.
- **Composed strings (rule (e)).** Exactly what the CLI writes (decision 2): spacings with 2
  decimals, Z values in invariant form.
- **Orthogonal one-direction grids (rule (r)).** For two grids with empty `y_lines`, the rotation
  difference d = |r1 − r2| mod 180 is refused when |d − 90| ≤ 0.5.

## 3. Examples

New files: `schemas/examples/spec-lot0-grid.example.json` (3.1),
`spec-lot0-rotated-grid.example.json` (3.2) and `spec-poly-members.example.json` (3.3). The existing
`schemas/examples/spec.example.json` is replaced by 3.4.
- Levels have no example of their own. They are not stand-alone objects (ADR-0015 decision 1); the
  `levels` arrays below are the level examples.
- In every grid example:
  - Q-001 is the units answer, Q-004 the gate-1 answer that fixes origin and rotation, and Q-010 the
    storey-levels answer.
  - A line's position is `derived` from the printed dimension and the units answer. The first
    line's position (0) derives from the origin answer.

### 3.1 Axis-aligned grid with its levels (lot 0)

```json
{
  "schema_version": "0.1",
  "project_id": "demo-warehouse",
  "lot": 0,
  "units": "mm",
  "description": "Synthetic example: setup lot, one axis-aligned grid (origin 0, rotation 0), lines 1-3 / A-B, with three levels.",
  "members": [],
  "grids": [
    {
      "spec_id": "L0-G-MAIN",
      "name": "GRID MAIN",
      "origin": {"x": 0, "y": 0, "z": 0, "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-004"}, "confidence": "high"},
      "rotation_deg": {"value": 0, "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-004"}, "confidence": "high"},
      "x_lines": [
        {
          "label": {"value": "1", "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "region": {"grid_ref": "1"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 0,
            "provenance": {
              "file": "S-101.dxf",
              "sheet": "S-101",
              "revision": "B",
              "region": {"grid_ref": "1"},
              "method": "derived",
              "derived_from": [{"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-004"}]
            },
            "confidence": "high"
          }
        },
        {
          "label": {"value": "2", "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "region": {"grid_ref": "2"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 6000,
            "provenance": {
              "file": "S-101.dxf",
              "sheet": "S-101",
              "revision": "B",
              "region": {"grid_ref": "2"},
              "method": "derived",
              "derived_from": [
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "dxf_dimension_text"},
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-001"}
              ]
            },
            "confidence": "high"
          }
        },
        {
          "label": {"value": "3", "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "region": {"grid_ref": "3"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 12000,
            "provenance": {
              "file": "S-101.dxf",
              "sheet": "S-101",
              "revision": "B",
              "region": {"grid_ref": "3"},
              "method": "derived",
              "derived_from": [
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "dxf_dimension_text"},
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-001"}
              ]
            },
            "confidence": "high"
          }
        }
      ],
      "y_lines": [
        {
          "label": {"value": "A", "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "region": {"grid_ref": "A"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 0,
            "provenance": {
              "file": "S-101.dxf",
              "sheet": "S-101",
              "revision": "B",
              "region": {"grid_ref": "A"},
              "method": "derived",
              "derived_from": [{"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-004"}]
            },
            "confidence": "high"
          }
        },
        {
          "label": {"value": "B", "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "region": {"grid_ref": "B"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 7500,
            "provenance": {
              "file": "S-101.dxf",
              "sheet": "S-101",
              "revision": "B",
              "region": {"grid_ref": "B"},
              "method": "derived",
              "derived_from": [
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "dxf_dimension_text"},
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-001"}
              ]
            },
            "confidence": "high"
          }
        }
      ],
      "levels": [
        {
          "label": {"value": "+0.000", "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "region": {"detail": "ELEVATION 1"}, "method": "dxf_entity"}, "confidence": "medium"},
          "z": {"value": 0, "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}, "confidence": "high"}
        },
        {
          "label": {"value": "+3.600", "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "region": {"detail": "ELEVATION 1"}, "method": "dxf_entity"}, "confidence": "medium"},
          "z": {"value": 3600, "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}, "confidence": "high"}
        },
        {
          "label": {"value": "+7.200", "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "region": {"detail": "ELEVATION 1"}, "method": "dxf_entity"}, "confidence": "medium"},
          "z": {"value": 7200, "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}, "confidence": "high"}
        }
      ]
    }
  ],
  "open_questions": []
}
```

### 3.2 Main grid plus a wing rotated 30° (lot 0)

The wing's local x axis runs at 30° from global X, and its origin is (15000, 2000, 0).
- Line W2 lies 5400 mm from the origin along that axis, which puts it at global
  (15000 + 5400·cos 30°, 2000 + 5400·sin 30°) on line WA.
- WB at 6000.5 shows a position on the 0.01 mm step that is not a whole millimetre.
- The CLI inserts the wing in a work plane turned by 30° about its origin (blocked until To verify
  T7).

```json
{
  "schema_version": "0.1",
  "project_id": "demo-warehouse",
  "lot": 0,
  "units": "mm",
  "description": "Synthetic example: setup lot, the main grid plus a wing grid rotated 30 degrees about its origin (15000, 2000).",
  "members": [],
  "grids": [
    {
      "spec_id": "L0-G-MAIN",
      "name": "GRID MAIN",
      "origin": {"x": 0, "y": 0, "z": 0, "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-004"}, "confidence": "high"},
      "rotation_deg": {"value": 0, "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-004"}, "confidence": "high"},
      "x_lines": [
        {
          "label": {"value": "1", "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "region": {"grid_ref": "1"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 0,
            "provenance": {
              "file": "S-101.dxf",
              "sheet": "S-101",
              "revision": "B",
              "region": {"grid_ref": "1"},
              "method": "derived",
              "derived_from": [{"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-004"}]
            },
            "confidence": "high"
          }
        },
        {
          "label": {"value": "2", "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "region": {"grid_ref": "2"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 6000,
            "provenance": {
              "file": "S-101.dxf",
              "sheet": "S-101",
              "revision": "B",
              "region": {"grid_ref": "2"},
              "method": "derived",
              "derived_from": [
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "dxf_dimension_text"},
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-001"}
              ]
            },
            "confidence": "high"
          }
        },
        {
          "label": {"value": "3", "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "region": {"grid_ref": "3"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 12000,
            "provenance": {
              "file": "S-101.dxf",
              "sheet": "S-101",
              "revision": "B",
              "region": {"grid_ref": "3"},
              "method": "derived",
              "derived_from": [
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "dxf_dimension_text"},
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-001"}
              ]
            },
            "confidence": "high"
          }
        }
      ],
      "y_lines": [
        {
          "label": {"value": "A", "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "region": {"grid_ref": "A"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 0,
            "provenance": {
              "file": "S-101.dxf",
              "sheet": "S-101",
              "revision": "B",
              "region": {"grid_ref": "A"},
              "method": "derived",
              "derived_from": [{"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-004"}]
            },
            "confidence": "high"
          }
        },
        {
          "label": {"value": "B", "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "region": {"grid_ref": "B"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 7500,
            "provenance": {
              "file": "S-101.dxf",
              "sheet": "S-101",
              "revision": "B",
              "region": {"grid_ref": "B"},
              "method": "derived",
              "derived_from": [
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "dxf_dimension_text"},
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-001"}
              ]
            },
            "confidence": "high"
          }
        }
      ],
      "levels": [
        {
          "label": {"value": "+0.000", "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "region": {"detail": "ELEVATION 1"}, "method": "dxf_entity"}, "confidence": "medium"},
          "z": {"value": 0, "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}, "confidence": "high"}
        },
        {
          "label": {"value": "+3.600", "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "region": {"detail": "ELEVATION 1"}, "method": "dxf_entity"}, "confidence": "medium"},
          "z": {"value": 3600, "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}, "confidence": "high"}
        },
        {
          "label": {"value": "+7.200", "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "region": {"detail": "ELEVATION 1"}, "method": "dxf_entity"}, "confidence": "medium"},
          "z": {"value": 7200, "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}, "confidence": "high"}
        }
      ]
    },
    {
      "spec_id": "L0-G-WING",
      "name": "GRID WING",
      "origin": {"x": 15000, "y": 2000, "z": 0, "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-004"}, "confidence": "high"},
      "rotation_deg": {"value": 30, "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-004"}, "confidence": "high"},
      "x_lines": [
        {
          "label": {"value": "W1", "provenance": {"file": "S-102.dxf", "sheet": "S-102", "revision": "A", "region": {"grid_ref": "W1"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 0,
            "provenance": {
              "file": "S-102.dxf",
              "sheet": "S-102",
              "revision": "A",
              "region": {"grid_ref": "W1"},
              "method": "derived",
              "derived_from": [{"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-004"}]
            },
            "confidence": "high"
          }
        },
        {
          "label": {"value": "W2", "provenance": {"file": "S-102.dxf", "sheet": "S-102", "revision": "A", "region": {"grid_ref": "W2"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 5400,
            "provenance": {
              "file": "S-102.dxf",
              "sheet": "S-102",
              "revision": "A",
              "region": {"grid_ref": "W2"},
              "method": "derived",
              "derived_from": [
                {"file": "S-102.dxf", "sheet": "S-102", "revision": "A", "method": "dxf_dimension_text"},
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-001"}
              ]
            },
            "confidence": "high"
          }
        },
        {
          "label": {"value": "W3", "provenance": {"file": "S-102.dxf", "sheet": "S-102", "revision": "A", "region": {"grid_ref": "W3"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 10800,
            "provenance": {
              "file": "S-102.dxf",
              "sheet": "S-102",
              "revision": "A",
              "region": {"grid_ref": "W3"},
              "method": "derived",
              "derived_from": [
                {"file": "S-102.dxf", "sheet": "S-102", "revision": "A", "method": "dxf_dimension_text"},
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-001"}
              ]
            },
            "confidence": "high"
          }
        }
      ],
      "y_lines": [
        {
          "label": {"value": "WA", "provenance": {"file": "S-102.dxf", "sheet": "S-102", "revision": "A", "region": {"grid_ref": "WA"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 0,
            "provenance": {
              "file": "S-102.dxf",
              "sheet": "S-102",
              "revision": "A",
              "region": {"grid_ref": "WA"},
              "method": "derived",
              "derived_from": [{"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-004"}]
            },
            "confidence": "high"
          }
        },
        {
          "label": {"value": "WB", "provenance": {"file": "S-102.dxf", "sheet": "S-102", "revision": "A", "region": {"grid_ref": "WB"}, "method": "dxf_entity"}, "confidence": "high"},
          "position": {
            "value": 6000.5,
            "provenance": {
              "file": "S-102.dxf",
              "sheet": "S-102",
              "revision": "A",
              "region": {"grid_ref": "WB"},
              "method": "derived",
              "derived_from": [
                {"file": "S-102.dxf", "sheet": "S-102", "revision": "A", "method": "dxf_dimension_text"},
                {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "engineer_answer", "question_id": "Q-001"}
              ]
            },
            "confidence": "high"
          }
        }
      ],
      "levels": [
        {
          "label": {"value": "+0.000", "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "region": {"detail": "ELEVATION 1"}, "method": "dxf_entity"}, "confidence": "medium"},
          "z": {"value": 0, "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}, "confidence": "high"}
        },
        {
          "label": {"value": "+3.600", "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "region": {"detail": "ELEVATION 1"}, "method": "dxf_entity"}, "confidence": "medium"},
          "z": {"value": 3600, "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}, "confidence": "high"}
        },
        {
          "label": {"value": "+7.200", "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "region": {"detail": "ELEVATION 1"}, "method": "dxf_entity"}, "confidence": "medium"},
          "z": {"value": 7200, "provenance": {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}, "confidence": "high"}
        }
      ]
    }
  ],
  "open_questions": []
}
```

### 3.3 Non-linear members (a curved beam and a kinked rafter)

- **Curved beam.** Chord 12 000 mm and rise 1 500 mm give R = (6000² + 1500²) / (2 × 1500) =
  12 750 mm. The arc point is derived from the printed radius.
- **Rafter.** Its ridge point is low confidence and carries its question.
- The arc point assumes the intended meaning of `arc_point` (the curve passes through it), which is
  To verify T3. If T3 fails, the derivation changes, not the schema.
- Under Q5 and OQ-B every point's Z traces to the storey-levels answer Q-010: each point is
  `derived` from its drawing source and that answer. The ridge point stays low confidence.

```json
{
  "schema_version": "0.1",
  "project_id": "demo-warehouse",
  "lot": 3,
  "units": "mm",
  "description": "Synthetic example: a curved edge beam on level +7.200 (R = 12750 mm) and a kinked rafter on grid B.",
  "members": [],
  "poly_members": [
    {
      "spec_id": "L3-B-CURVE-A",
      "type": "beam",
      "mark": "CB1",
      "profile": {"value": "IPE300", "provenance": {"file": "S-102.dxf", "sheet": "S-102", "revision": "A", "region": {"grid_ref": "A/1-3"}, "method": "dxf_entity"}, "confidence": "high"},
      "material": {
        "value": "S355JR",
        "provenance": {"file": "S-001.pdf", "sheet": "S-001", "revision": "A", "region": {"page": 1, "detail": "GENERAL NOTES 3.1"}, "method": "pdf_text_layer"},
        "confidence": "medium"
      },
      "points": [
        {
          "x": 0,
          "y": 0,
          "z": 7200,
          "chamfer": "none",
          "provenance": {
            "file": "S-102.dxf",
            "sheet": "S-102",
            "revision": "A",
            "region": {"grid_ref": "A/1"},
            "method": "derived",
            "derived_from": [
              {"file": "S-102.dxf", "sheet": "S-102", "revision": "A", "region": {"grid_ref": "A/1"}, "method": "dxf_entity"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        },
        {
          "x": 6000,
          "y": -1500,
          "z": 7200,
          "chamfer": "arc_point",
          "provenance": {
            "file": "S-102.dxf",
            "sheet": "S-102",
            "revision": "A",
            "region": {"detail": "R=12750"},
            "method": "derived",
            "derived_from": [
              {"file": "S-102.dxf", "sheet": "S-102", "revision": "A", "method": "dxf_dimension_text"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "medium"
        },
        {
          "x": 12000,
          "y": 0,
          "z": 7200,
          "chamfer": "none",
          "provenance": {
            "file": "S-102.dxf",
            "sheet": "S-102",
            "revision": "A",
            "region": {"grid_ref": "A/3"},
            "method": "derived",
            "derived_from": [
              {"file": "S-102.dxf", "sheet": "S-102", "revision": "A", "region": {"grid_ref": "A/3"}, "method": "dxf_entity"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        }
      ],
      "class": "4"
    },
    {
      "spec_id": "L3-R-B-KINK",
      "type": "rafter",
      "mark": "R1",
      "profile": {"value": "IPE240", "provenance": {"file": "S-202.dxf", "sheet": "S-202", "revision": "A", "region": {"detail": "SECTION B-B"}, "method": "dxf_entity"}, "confidence": "high"},
      "material": {"value": "S355JR", "provenance": {"file": "S-001.pdf", "sheet": "S-001", "revision": "A", "method": "pdf_text_layer"}, "confidence": "medium"},
      "points": [
        {
          "x": 0,
          "y": 7500,
          "z": 7200,
          "chamfer": "none",
          "provenance": {
            "file": "S-202.dxf",
            "sheet": "S-202",
            "revision": "A",
            "method": "derived",
            "derived_from": [
              {"file": "S-202.dxf", "sheet": "S-202", "revision": "A", "method": "dxf_dimension_text"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        },
        {
          "x": 6000,
          "y": 7500,
          "z": 7800,
          "chamfer": "none",
          "provenance": {
            "file": "S-202.dxf",
            "sheet": "S-202",
            "revision": "A",
            "method": "derived",
            "derived_from": [
              {"file": "S-202.dxf", "sheet": "S-202", "revision": "A", "method": "vision"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "low"
        },
        {
          "x": 12000,
          "y": 7500,
          "z": 7200,
          "chamfer": "none",
          "provenance": {
            "file": "S-202.dxf",
            "sheet": "S-202",
            "revision": "A",
            "method": "derived",
            "derived_from": [
              {"file": "S-202.dxf", "sheet": "S-202", "revision": "A", "method": "dxf_dimension_text"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        }
      ],
      "class": "4",
      "question_ids": ["Q-031"]
    }
  ],
  "open_questions": ["Q-031"]
}
```

### 3.4 `spec.example.json`, updated (OQ-B)

The current example with each member point `derived` from its drawing source and the storey-levels
answer Q-010, so that it passes rule (f). Nothing else changes.

```json
{
  "schema_version": "0.1",
  "project_id": "demo-warehouse",
  "lot": 1,
  "units": "mm",
  "description": "Synthetic example: two columns on grid A/1 and A/2 and the beam between them; every point's Z traces to the storey-levels answer Q-010.",
  "members": [
    {
      "spec_id": "L1-C-A1",
      "type": "column",
      "mark": "C1",
      "profile": {"value": "HEA300", "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "region": {"grid_ref": "A/1"}, "method": "dxf_entity"}, "confidence": "high"},
      "material": {
        "value": "S355JR",
        "provenance": {"file": "S-001.pdf", "sheet": "S-001", "revision": "A", "region": {"page": 1, "detail": "GENERAL NOTES 3.1"}, "method": "pdf_text_layer"},
        "confidence": "medium"
      },
      "start": {
        "x": 0,
        "y": 0,
        "z": 0,
        "provenance": {
          "file": "S-101.dxf",
          "sheet": "S-101",
          "revision": "B",
          "method": "derived",
          "derived_from": [
            {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "dxf_entity"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "high"
      },
      "end": {
        "x": 0,
        "y": 0,
        "z": 6000,
        "provenance": {
          "file": "S-201.dxf",
          "sheet": "S-201",
          "revision": "A",
          "region": {"detail": "ELEVATION 1"},
          "method": "derived",
          "derived_from": [
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "region": {"detail": "ELEVATION 1"}, "method": "dxf_dimension_text"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "high"
      },
      "class": "3"
    },
    {
      "spec_id": "L1-C-A2",
      "type": "column",
      "mark": "C1",
      "profile": {"value": "HEA300", "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "region": {"grid_ref": "A/2"}, "method": "dxf_entity"}, "confidence": "high"},
      "material": {
        "value": "S355JR",
        "provenance": {"file": "S-001.pdf", "sheet": "S-001", "revision": "A", "region": {"page": 1, "detail": "GENERAL NOTES 3.1"}, "method": "pdf_text_layer"},
        "confidence": "medium"
      },
      "start": {
        "x": 6000,
        "y": 0,
        "z": 0,
        "provenance": {
          "file": "S-101.dxf",
          "sheet": "S-101",
          "revision": "B",
          "method": "derived",
          "derived_from": [
            {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "dxf_dimension_text"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "high"
      },
      "end": {
        "x": 6000,
        "y": 0,
        "z": 6000,
        "provenance": {
          "file": "S-201.dxf",
          "sheet": "S-201",
          "revision": "A",
          "method": "derived",
          "derived_from": [
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "dxf_dimension_text"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "high"
      },
      "class": "3"
    },
    {
      "spec_id": "L1-B-A12",
      "type": "beam",
      "mark": "B1",
      "profile": {
        "value": "IPE300",
        "provenance": {"file": "S-102.pdf", "sheet": "S-102", "revision": "A", "region": {"page": 1, "bbox": [412.5, 220.0, 470.0, 236.0]}, "method": "vision"},
        "confidence": "low"
      },
      "material": {"value": "S355JR", "provenance": {"file": "S-001.pdf", "sheet": "S-001", "revision": "A", "method": "pdf_text_layer"}, "confidence": "medium"},
      "start": {
        "x": 0,
        "y": 0,
        "z": 6000,
        "provenance": {
          "file": "S-201.dxf",
          "sheet": "S-201",
          "revision": "A",
          "method": "derived",
          "derived_from": [
            {"file": "S-101.dxf", "sheet": "S-101", "revision": "B", "method": "dxf_entity"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "medium"
      },
      "end": {
        "x": 6000,
        "y": 0,
        "z": 6000,
        "provenance": {
          "file": "S-201.dxf",
          "sheet": "S-201",
          "revision": "A",
          "method": "derived",
          "derived_from": [{"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}]
        },
        "confidence": "medium"
      },
      "class": "4",
      "question_ids": ["Q-001"]
    }
  ],
  "open_questions": ["Q-001"]
}
```

## 4. `docs/tekla-cli-contract.md` additions (applies with `git apply` at base 09274de)

> **Erratum (2026-11-11, review of P15-8).** The diff below was applied as accepted, and it dropped
> refusals that ADR-0015 requires. The contract (`docs/tekla-cli-contract.md`) gained these
> sentences after the review; the diff is not rewritten.
> - C-1: rule 9 states the T9 gate for an additive lot-0 `update` and for the override flag, and
>   lists it among what the flag does not lift (decision 10).
> - M-4: rule 9 finds parts by enumeration, never `GetObjectsByBoundingBox`, and defines the
>   extent (decision 10 gives the span plus 1 000 mm; the union of before and after is the
>   engineer decision of 2026-11-11), To verify #18.
> - M-5: new rule 13 lists the To verify gates: T4 for every write (decision 11), T1, T2, T3
>   (decision 4), T9; walls, C1 (ADR-0016 Consequences).
> - m-1: rule 9 defines "member lot" (any lot >= 1) and the counting rule, with `project-state.json`.
> - m-2: rule 9 "additive" also means no rename or change of origin or rotation.
> - m-3: rule 9 gives the flag's exit `2` for a wrong command, lot or `question_id` pattern
>   (contract choice; ADR-0015 decision 10 gives no exit code).
> - m-8: the exit `3` list names the member-lot disagreement and the unreadable tag.
> - m-13: rule 8 says "`y_lines` empty" for a one-direction grid.
>
> Second review (P15-8B, applied in P15-8C), one bullet per finding:
> - Ma-1: rule 11 keys its Position refusal on (kind x material type); `walls`, `slabs` and
>   `polygonal_caps` are kinds too.
> - Ma-2: rule 13 names T1 and T2 for grids; rule 4 closes the grid route if a `Grid` cannot keep
>   the tags.
> - Ma-3: openings open only when C4, C5 and C6 pass and C7 has a recorded result with either C7
>   passed or C7 failed and C8 passed (C5 and C6 before build: engineer decision 2026-11-11).
> - Ma-4: every gate is a code constant opened by an engineer-merged commit (engineer decision
>   2026-11-11).
> - Ma-5: one ordering sentence under the "Safety rules" heading: rule 1 first, then the refusals of
>   rules 3 to 13, before the backup and the first write.
> - Ma-6: commit text only (the `Safety:` lines).
> - m-1: the exit `3` list names a failed cut tag write or read-back and its mid-run meaning.
> - m-2: the rectangular wall cutter has four corners and no work-plane change.
> - m-3: rule 9 says union and `≤ 0.1 mm`; the one-direction grid extent is an open question.
> - m-4: the flag's pattern is `^Q-[0-9]{3,}$` (`schemas/common.schema.json`).
> - m-5: `update` never deletes now sits in rule 5.
> - m-6: rule 6 says "a `members` `column` item named `PILE`".
> - m-7: rule 9 rewrapped, one blank line removed here.
> - m-8: attributions corrected in this note.
> - m-9: CHANGELOG extended.
>
> Third review (P15-8C, applied in P15-8D) and engineer decisions of 2026-11-11:
> - rule 5: an `update` whose spec lacks an existing object of the lot, under any `RUN_ID`,
>   refuses (exit `5`) and lists each `SPEC_ID`, `RUN_ID` and GUID; the engineer uses `rollback`,
>   for lot 0 within rule 9's limits (engineer).
> - rule 13: C1 also gates the profiles of pad footings, pile caps (both kinds), strip footings,
>   slabs and opening cutters (walls: ADR-0016 Consequences), C10 the rectangular wall cutter and
>   C14 piles built as columns (engineer); To verify #13 gates the backup macro; gates are keyed
>   on the full `tekla_version`, service pack included, and a version without evidence keeps
>   every gate closed; the list is complete, and `rollback` waits only for T4, #13 and the
>   opening gates (engineer).
> - rule 4: a failed T2 exits `3`; while T2 has no result, rule 13 exits `5`.
> - the Order paragraph: rule 1 first, then the refusals of rules 3 to 13, before the backup; a
>   command stops mid-run only on an API error, a failed journal write, a failed rule 1 re-check
>   before `CommitChanges`, or a failed check after a model call in rules 10 to 12.

No new subcommand and no new exit code. New refusals map onto the existing codes:
- `5`:
  - a spec read closed-world that has an unknown key or enum value;
  - a receipt whose rules version is too old;
  - lot and grid placement;
  - a rotated grid before T7, or a one-direction grid before T8;
  - a non-additive lot-0 `update`, or a lot-0 `rollback`, while a member lot exists or parts sit on
    the grid (for `update` with no member lot, unless `--allow-untagged-shift <question_id>` is
    given);
- `3`:
  - grid tag UDAs not defined;
  - the two sources for "a member lot exists" disagree, or a tag is unreadable;
  - a CLI without the 2026 level members running on Tekla 2026 or later;
- `4`: a part still bound to a level after `Insert` (stop, keep, journal);
- `1`: a bound part found while planning a resume.

The diff was generated from the contract at 09274de and checked with `git apply --check`.

```diff
--- a/docs/tekla-cli-contract.md
+++ b/docs/tekla-cli-contract.md
@@ -36,14 +36,14 @@
 
 | Subcommand | Class | Purpose |
 |---|---|---|
-| `info` | read | Tekla version, open model, catalogs available, tag UDA definitions |
-| `validate` | read | Check profiles/materials/components in a spec exist in the catalogs |
-| `query` | read | Objects by `LOT` / `RUN_ID` / `SPEC_ID` / GUID |
+| `info` | read | Tekla version, open model, catalogs available, tag UDA definitions (parts and `CatalogObjectTypeEnum.GRID`) |
+| `validate` | read | Check profiles/materials/components in a spec exist in the catalogs (members and poly members); poly member point count within `Contour.MAX_POLYBEAM_POINTS` |
+| `query` | read | Objects by `LOT` / `RUN_ID` / `SPEC_ID` / GUID; grids by enumerating every `Grid` and reading its tags (no UDA filter); untagged grids listed separately |
 | `selected` | read | Objects currently selected in the Tekla UI |
-| `export` | read | CSV + IFC of a lot or run (writes files, not the model; may change the UI selection, restores it afterwards) |
-| `build` | **write** | Create the objects of one lot from `spec.json`, tag them, one commit; resumes a stopped run |
-| `update` | **write** | Modify objects of one lot from a corrected spec |
-| `rollback` | **write** | Delete all objects of a `RUN_ID`; run only on the engineer's request, never automatically |
+| `export` | read | CSV + IFC of a lot or run (writes files, not the model; may change the UI selection, restores it afterwards). CSV adds one row per grid (frame), one per grid line or level and one per polybeam point; grids are not exported to IFC |
+| `build` | **write** | Create the objects of one lot from `spec.json`, tag them, one commit; resumes a stopped run. Lot 0 builds grids (levels are their Z planes); lots ≥ 1 build members and poly members |
+| `update` | **write** | Modify objects of one lot from a corrected spec; for lot 0 only additive while a member lot exists (rule 9) |
+| `rollback` | **write** | Delete all objects of a `RUN_ID`, grids included; run only on the engineer's request, never automatically; refused for lot 0 while a member lot exists (rule 9) |
 
 Any subcommand not listed as **read** is treated as a write by the guard hook (fail closed).
 Adding a read subcommand requires updating `READ_SUBCOMMANDS` in
@@ -67,10 +67,12 @@
    a validation receipt from `harness validate spec` whose SHA-256 matches the spec file
    ([ADR-0010](decisions/0010-spec-validation-receipt.md), Amendment 1). A missing or mismatched
    receipt, a spec the reader rejects, or a spec `lot` other than `--lot` exits `5`; missing
-   arguments exit `2`; an existing spec or receipt that cannot be read exits `3`.
-4. Tag every created or modified object with UDAs `LOT`, `RUN_ID`, `SPEC_ID`. Refuse (exit `3`)
-   unless all three are defined in the model as `unique_attribute`, type `string`, not affecting
-   numbering (the repo ships the `objects.inp` to copy into each model folder).
+   arguments exit `2`; an existing spec or receipt that cannot be read exits `3`. `--lot` accepts
+   `0` (the setup lot, [ADR-0015](decisions/0015-lot-spec-grids-levels-nonlinear-members.md)).
+4. Tag every created or modified object, grids included, with UDAs `LOT`, `RUN_ID`, `SPEC_ID`.
+   Refuse (exit `3`) unless all three are defined in the model as `unique_attribute`, type
+   `string`, not affecting numbering, for parts and for grids (`CatalogObjectTypeEnum.GRID`; the
+   repo ships the `objects.inp`, with a `grid` section, to copy into each model folder).
 5. Commit once per command. On any API error: stop, keep every object already created or
    modified, write the run journal (GUID and `SPEC_ID` of each object done, the failing item,
    the error) and exit `4`. Never delete objects to clean up.
@@ -78,10 +80,52 @@
    `SPEC_ID` already exists in that lot and run, and builds only the missing ones. If an existing
    object differs from its spec item, stop with exit `1` and ask the engineer. Never create a
    duplicate `SPEC_ID`. Journal, snapshot, matching rules ("differs" includes kind, rotation and
-   class since 2026-11-08), lock and refusals: [ADR-0012](decisions/0012-run-journal-and-resume-planner.md).
+   class since 2026-11-08), lock and refusals: [ADR-0012](decisions/0012-run-journal-and-resume-planner.md),
+   as amended by ADR-0015. The kind compared is the Tekla kind the spec item maps to (`brace`,
+   `purlin`, `girt`, `rafter`, `other` are kind `beam`); a grid item matches only kind `grid`, a
+   poly member only kind `polybeam` (its spec `type` is not compared); "differs" per ADR-0015
+   decision 9.
+7. Read the spec closed-world: any key or enum value outside the spec schema, at any nesting level
+   the CLI interprets, refuses (exit `5`), so no spec item is ever skipped or misread silently.
+   `spec_id` is unique across `members`, `poly_members` and `grids`. A receipt whose
+   `rules_version` is below the CLI's minimum refuses (exit `5`).
+8. Lot 0 holds grids only and lots ≥ 1 hold no grids; anything else refuses (exit `5`). A grid
+   with `rotation_deg` 0 is built in the global work plane with `Origin` = its origin plus its
+   first line positions; a rotated grid in a work plane turned by `rotation_deg` about +Z at its
+   origin, the global plane set back afterwards (refused, exit `5`, until To verify T7 passes); a
+   one-direction grid (no `y_lines`) is refused until T8 passes. X/Y are written as spacings from
+   the first line with 2 decimals, Z as absolute level values, `IsMagnetic = false`. A poly member
+   is a `PolyBeam` of type `BEAM`, one `ContourPoint` per spec point, chamfer `CHAMFER_NONE` or
+   `CHAMFER_ARC_POINT`, built in the global work plane.
+9. Lot 0 after it is built. Never modify or delete an untagged grid; `build` of lot 0 lists
+   untagged grids in its output. Whether a member lot exists is decided from two sources, an
+   enumeration of every harness-built kind with `LOT` read per object and the run journals of the
+   project's lot folders; a disagreement or an unreadable tag refuses (exit `3`). While a member
+   lot exists, `update` of lot 0 may only add grids, lines or levels (nothing moved or removed) and
+   `rollback` of lot 0 refuses (exit `5`). A non-additive `update` or a `rollback` of lot 0 also
+   refuses (exit `5`) while any part, tagged or not, is bound to a level of a grid being changed or
+   has a reference point within the grid's extent plus 1 000 mm; the refusal lists each such part
+   (GUID, type, name, reference points, level names). Only while no member lot exists, `update`
+   of lot 0 with `--allow-untagged-shift <question_id>` lifts this one refusal; the `question_id`
+   is the engineer answer that authorises it. The output then lists those parts before the change
+   and again after it, each read back and marked moved when a reference point changed by more
+   than 0.1 mm or a level name changed, and the run journal records the flag, the `question_id`
+   and the parts. The flag lifts nothing else: not the member-lot rule, not the exit `3`, not
+   untagged grids, and `rollback` of lot 0 takes no such flag.
+10. Tekla 2026: parts are not bound to levels. A write command first checks that this CLI can read
+    the level members; one built without them refuses on Tekla 2026 or later (exit `3`). The CLI
+    sets the unbound value (To verify T4); a part whose `StartLevelName` or `EndLevelName` is still
+    set after `Insert` stops the run as in rule 5 (keep, journal, exit `4`); one found in the
+    snapshot when planning a resume differs from its spec item (exit `1`). If T4 shows that the API
+    cannot unbind, no write route opens until a new ADR.
 
 ## Open questions
 
+- ADR-0015 To verify T1–T10 (`tekla/api-notes.md`): how the API reads grid coordinate strings and
+  rounds them, grid UDAs, polybeam arc read-back and point limit, 2026 level binding (first test on
+  2026), string limits, rotated and one-direction grids, additive grid `Modify`, the model-wide
+  `LOT` enumeration.
+
 - Whether objects inserted before a crash, without `CommitChanges`, persist
   (`tekla/api-notes.md`, To verify #9).
 - The backup macro (To verify #13) and the backup folder location (`XS_MODEL_BACKUP_DIRECTORY`)
```

## 5. `tekla/api-notes.md` additions ("To verify on the test model")

Every check runs with the global work plane set unless it names another. On the 2026 test model,
run T4 first.
- **T1. Grid strings.**
  - Insert a `Grid` with `Origin = (1000, 2000, 0)`, `CoordinateX = "0.00 6000.00 6000.00"` and
    `CoordinateZ = "0.00 3600.00 7200.00"`.
  - Do the child `GridPlane`s sit at global X 1000/7000/13000 (spacings) and Z 0/3600/7200
    (absolute)?
  - Does `Select()` return the strings as written, or normalised (`0.00`, `2*6000.00`)?
  - Do 2-decimal spacings such as `4050.55`, written 20 times, round-trip exactly (review Minor 13)?
- **T2. Grid UDAs.** The three UDAs are in the `grid` section of `objects.inp`.
  - Does `SetUserProperty` on a `Grid` return true and persist after save and reopen?
  - Does `GetAllObjectsWithType(GRID)` return the grid?
  - Does `GetUserPropertyItems(CatalogObjectTypeEnum.GRID)` report the definitions? (Extends #7.)
- **T3. Polybeam arc.** Take a `PolyBeam` with 3 points whose middle point is `CHAMFER_ARC_POINT`.
  - Does the centre line (`GetCenterLinePolycurve`) pass through the middle point?
  - Does `Contour` read back the same count, order, coordinates (≤ 0.1 mm) and chamfer types?
  - What is the value of `Contour.MAX_POLYBEAM_POINTS`?
  - Which catalog object type and `objects.inp` section define UDAs for polybeams?
- **T4. Tekla 2026 level binding: the first test on 2026.** Insert a `Beam`, a `PolyBeam` and a
  `ContourPlate` through the API with no level set.
  - Is each one bound (`Auto`, SP4)?
  - Which value unbinds it: an empty `StartLevelName`/`LevelName` before `Insert`, or a `Modify`
    after it?
  - Is the unbinding kept after save and reopen?
  - Does a CLI built against 2024.0.4 run on 2026 at all (extends #4)?
- **T5. String limits.** What is the API length limit of `CoordinateX/Y/Z` and `LabelX/Y/Z` (the UI
  allows 1024 characters for coordinates)? Do non-ASCII (Vietnamese) labels round-trip?
- **T6. Label syntax.**
  - Are labels containing `*`, `+` or `.` (e.g. `2*`, `+3.600`) taken as labels, not as the `n*d`
    repeat syntax?
  - What is the `Grid.Name` length limit, and does the name round-trip?
- **T7. Rotated grid.** Set a work plane with origin (15000, 2000, 0) and its X axis at 30° from
  global X, insert a `Grid`, and set the global plane back.
  - Is the grid rotated, with its lines where the local frame puts them?
  - With the global plane set, what do `Origin` and the coordinate strings read back as?
  - Which call gives the grid's rotation back? No rotation member is documented (F6).
    `ModelObject.GetCoordinateSystem()` on the grid is the candidate: does it return the rotated
    axes?
  - Does `SetCurrentTransformationPlane` change the work plane the engineer sees in the UI, and what
    state remains if the CLI dies before setting the global plane back (review To verify 17)?
- **T8. One-direction grid.** Insert a `Grid` with `CoordinateY`/`LabelY` empty.
  - Is it accepted?
  - Does it create only the X family, with no extra Y line?
  - How does it read back?
  - If empty is refused, what is the smallest input that gives one family and no visible extra
    line?
- **T9. Additive grid change and grid delete.**
  - On a non-magnetic grid, does `Modify` that adds a line or a level keep every existing
    `GridPlane` and leave every part (tagged, untagged, and on 2026 bound to its levels) exactly
    where it was?
  - Does `Delete()` of the grid remove its `GridPlane`s and leave unbound parts where they were?
    Does it move or orphan bound parts? (Review To verify 4.)
  - With `--allow-untagged-shift` (OQ-A): after a `Modify` that moves or removes a line or a level,
    does the read-back of each listed untagged part (reference points, level names) show exactly
    what moved, so the "after" list is true? The flagged route waits for this check.
- **T10. Model-wide `LOT` check.** Does an enumeration of every harness-built kind, with `LOT` read
  per object, agree with a UDA filter, including just-inserted, uncommitted parts? (Extends #20.)

## 6. CHANGELOG entry (Unreleased → Changed)

```markdown
- `spec.schema.json` (0.1, ADR-0015): lot 0 setup lot with `grids` (each with an engineer-confirmed
  `origin` and `rotation_deg`, line positions absolute in the grid's frame, `y_lines` empty for a
  one-direction grid; levels as each grid's Z planes); `poly_members` (Tekla PolyBeam, `points[]`
  with `none`/`arc_point` chamfers); `members` stays required and may be empty, so lot 0 carries
  `"members": []`; `lot` minimum 0. `spec.example.json` updated: every member point's provenance
  traces to the storey-levels answer (ADR-0015 rule (f), OQ-B).
```

## API facts relied on

Status as in `tekla/api-notes.md`: `nuget-metadata` = shipped XML doc read from the package,
`doc` = Trimble page fetched on 2026-11-10. Packages, each from
`https://api.nuget.org/v3-flatcontainer/<id>/<version>/` (no package was on this machine):
- **PKG24** = `Tekla.Structures.Model` 2024.0.4;
- **PKG26** = `Tekla.Structures.Model` 2026.0.3, the target version (Q1);
- **CAT24** and **CAT26** = `Tekla.Structures.Catalogs` 2024.0.4 and 2026.0.3.

The review re-checked F1–F18 on 2026-11-11 against PKG24, PKG26, CAT24 and CAT26. F8 was wrong and
is corrected below.

| # | Fact | Version | Source | Status |
|---|---|---|---|---|
| F1 | `PolyBeam`: "a continuous beam with a contour as input"; `AddContourPoint(ContourPoint)` (false "if there is no more space"), `Contour`, `Insert/Select/Modify/Delete`, `GetCenterLinePolycurve`; `PolyBeamTypeEnum` = `BEAM, COLUMN, PANEL, STRIP_FOOTING`, default beam | 2024, 2026 | PKG24, PKG26 `T:Tekla.Structures.Model.PolyBeam` | nuget-metadata |
| F2 | `Chamfer` "defines how the corners of a polybeam or a contour plate are rounded"; `ChamferTypeEnum` includes `CHAMFER_NONE`, `CHAMFER_ARC`, `CHAMFER_ARC_POINT` ("The arc point type chamfer", no geometry stated); `DZ1/DZ2` "does nothing when used with the PolyBeam"; `ContourPoint(Point, Chamfer)` | 2024, 2026 | PKG24 `T:...Chamfer`, `T:...ContourPoint` | nuget-metadata |
| F3 | `Contour`: "Contours must not have loops"; fields `MAX_POLYBEAM_POINTS` and `MAX_CONTOUR_POINTS` exist, values not documented | 2024, 2026 | PKG24 `T:...Contour`, `F:...Contour.MAX_POLYBEAM_POINTS`, `F:...Contour.MAX_CONTOUR_POINTS` | nuget-metadata |
| F4 | `Beam.Radius` appears only as a field (`F:`) "Radius for curved beam"; `F:…ModelInternal.dotPart_t.Radius`: "Used only internally! May be removed later when conversion from curved to polybeam exists"; no property or constructor takes a radius | 2024, 2026 | PKG24, PKG26 | nuget-metadata |
| F5 | `Beam/PolyBeam.StartLevelName/EndLevelName/StartLevelOffset/EndLevelOffset`, `ContourPlate.LevelName/LevelOffset`: present in 2026.0.3, absent in 2024.0.4 | 2026 only | PKG24 vs PKG26 member diff | nuget-metadata |
| F6 | `Grid`: `CoordinateX/Y/Z`, `LabelX/Y/Z`, extensions, `Color`; constructor defaults `CoordinateX "0.00 4*3000.00"` (repeat syntax: spacings), `CoordinateZ "0.00 6000.00 8000.00 9000.00"` with `LabelZ "+0 +6000 +8000 +9000"` (labels match only if Z is absolute), `IsMagnetic false`; "A grid has grid plane instances as children"; no rotation member on `Grid` or `GridBase` (full member list of PKG26 read 2026-11-11: `Name`, `Origin`, `IsMagnetic`, `Coordinate*`, `Label*`, `Extension*`, `Color`, `FontColor`, `FontSize`); `GridPlane` has `Plane`, `Label`, `Father` (T8 fallback); `ModelObject.GetCoordinateSystem()` "Returns the coordinate system for the given model object" (T7 candidate); documented Grid, GridPlane, Chamfer, ContourPoint members identical in 2024.0.4 and 2026.0.3 | 2024, 2026 | PKG24/PKG26 `T:...Grid`, `M:...Grid.#ctor`, `P:...GridBase.*`, `M:...ModelObject.GetCoordinateSystem`, member diff | nuget-metadata |
| F7 | `Grid` inherits `GridBase` (`Name`, `Origin`, `IsMagnetic`, `Insert/Modify/Delete/Select`) and `ModelObject` (`SetUserProperty`, `GetUserProperty`, `GetChildren`); no remark on relative vs absolute strings | 2025 | https://developer.tekla.com/doc/tekla-structures/2025/grid-class-52622 | doc |
| F8 | `ModelObjectEnum` has `GRID`, `GRIDPLANE`, `POLYBEAM`, and already `STOREY`, `SPACE`, `BUILDING` in 2024.0.4; 2026.0.3 adds only `BUILDING_SITE`. The 2026-only additions `BUILDING`, `BUILDING_SECTION`, `STOREY` are in `CatalogObjectTypeEnum` (CAT26, absent in CAT24); `HierarchicObject` exists | 2024, 2026 | PKG24, PKG26, CAT24, CAT26 | nuget-metadata |
| F9 | `CatalogObjectTypeEnum` has `GRID` and `GRID_PLANE` (no polybeam-specific value) | 2024, 2026 | CAT24, CAT26 | nuget-metadata |
| F10 | UI grid: "x and y coordinates are relative … to the previous entry"; "Z coordinates are absolute … from the work plane origin"; origin offsets "from the work plane origin, not from the global model origin"; grid name "can be used … when you bind parts to grid levels"; grid UDAs "can be used for customizing drawing grid labels" | 2026 | https://help.trimble.com/doc/tekla-structures/2026/mod_creating_a_grid | doc |
| F11 | Coordinates box max 1024 characters | 2025 | *Create models* PDF p.20-27 (research note S1) | doc |
| F12 | Bind parts to grid levels (new in 2026): levels are "z-direction elevations that are taken from the project grids"; beams and polybeams bind start and end; bound parts follow when the level changes | 2026 | https://help.trimble.com/doc/tekla-structures/2026/rel_bind_to_levels | doc |
| F13 | 2026 SP4: `Auto` binds a part "to the closest level of the part's handle point"; `None` creates no binding; the page does not say which is the default | 2026 SP4 | https://help.trimble.com/doc/tekla-structures/2026/rel_2026_sp4_new_features_and_improvements | doc |
| F14 | `objects.inp` grid sections `grid(0,"Grid")` and `grid_plane(0,"Grid")` holding a `unique_attribute`; Trimble's `objects.inp` parser (`TSModelObjectTypes`) lists `grid` and `grid_plane`, and no polybeam or boolean section | TS 18+ (extension page); parser sample code | "Erweiterte Achsbezeichnungen" (Advanced Grid Labels), https://help.trimble.com/node/107852?old_alias_match=1; Trimble GitHub `TeklaApplicationLibrary/Library/InpParser/UDAValue.cs` | doc (German extension page), sample-code |
| F15 | UI curved beam: three picked points (start, point on arc, end); properties Plane, Radius, Number of segments | 2024 | https://help.trimble.com/doc/tekla-structures/2024/mod_creating_curved_beam | doc |
| F16 | Curved beam component: "end result of a poly-beam"; Modify/Get work only on a poly-beam with 3 points whose middle point has the arc chamfer | not version-specific | https://help.trimble.com/help/tekla-structures/not-version-specific/curved_beam | doc |
| F17 | Polybeams: "alternate the chamfer type between None and Arc point"; Arc point on every point "can cause solid errors and incorrect length"; keep points in the same plane (unfolding for drawings/NC) | not version-specific | https://help.trimble.com/article/recommendations-for-creating-polybeams | doc |
| F18 | `XS_POLYBEAM_CURVATURE_TOLERANCE` (default `2.0e-6`): three nearly collinear points are a straight line and "the arc chamfer is omitted" | 2025 | https://help.trimble.com/doc/tekla-structures/2025/xs_polybeam_curvature_tolerance | doc |

No source settles the following, so each is written as To verify and never asserted:
- T1–T10 above;
- whether an `arc_point` lies on the built curve;
- whether Tekla's `Insert` through the API applies a UI binding default;
- how a rotated grid reads back.
