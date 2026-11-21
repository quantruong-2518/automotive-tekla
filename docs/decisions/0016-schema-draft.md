# ADR-0016 draft: schema, examples and contract additions

Companion to [ADR-0016](0016-lot-spec-slabs-footings-piles-walls.md) (status **Accepted**,
engineer, 2026-11-11), revised on 2026-11-11 for the review and the engineer's answers Q1–Q17 and
OQ-A–OQ-E. It is composed on top of the [ADR-0015 draft](0015-schema-draft.md) and applies after
it. Nothing here is applied yet: the execution packages of both ADRs apply it. `$id` stays
`urn:tekla-harness:schema:spec:0.1` (AGENTS.md), and the change gets a CHANGELOG entry.

**Checked on 2026-11-11** in the repo environment at 09274de, with
`tekla_harness.schemas.validate("spec", …)`: the schema plus the **current** `check_spec`, with ECMA
pattern translation. `_REPO_SCHEMAS` was pointed at a copy of `schemas/` holding the composed schema
below, and `_load_all.cache_clear()` was called. The `$defs` it shares with ADR-0015's schema
(`poly_member`, `poly_point`, `grid`, `grid_line`, `grid_level`) were compared by program and are
identical. Only `member` differs, as intended.

These validate:
- ADR-0015's four examples (3.4 is the updated `spec.example.json`), and the current
  `schemas/examples/spec.example.json` at schema level;
- the two examples below;
- a lot of polygonal caps only;
- a pile named `PILE`, and a pile cap named `PILE_CAP`;
- an opening `spec_id` of 60 characters, and a slab `spec_id` of 64.

These are rejected:
- in lot 0: a slab, or a polygonal cap;
- a polygonal cap without `class`, with a `name` key, or with `openings`;
- a pile or a pile cap without `class`;
- reserved names misused:
  - a pile named `P`;
  - a pad footing named `PILE_CAP`;
  - a column named `PILE`;
  - a slab named `PILE_CAP`;
  - a wall named `PILE`;
- openings: one with an `arc_point`, an opening `spec_id` of 61 characters, and a top-level
  `openings` key;
- slabs: one with 2 outline points, thickness 0, or a `profile` key;
- walls: height 0.5, or a `rotation_deg` key;
- a member of type `slab`, and a poly member of type `strip_footing`.

Rules (i)–(q) do not exist yet and were not run. A scratch probe of rules (j), (k), (p) and (q),
and of ADR-0015 rule (f) with the member paths of OQ-B, passes on the six examples. The execution package runs the real rules on every example plus one
reject case per rule.

The contract block was generated from the contract at 09274de with ADR-0015's §4 diff applied, and
checked by applying ADR-0015's diff with `git apply` and then this one with `git apply --check`.

## 1. `schemas/spec.schema.json` (full replacement, ADR-0015 + ADR-0016)

> **Erratum (2026-11-11, review of P15-3 M1).** This draft missed a guard: `$defs/poly_member/properties/name`
> was `{"type": "string"}`, so a poly member could carry the reserved Names `PILE` or `PILE_CAP`
> (ADR-0016 decisions 3 and 9). The applied schema uses
> `{"type": "string", "not": {"enum": ["PILE", "PILE_CAP"]}}`, as for `slab` and `wall`.

Additions against the ADR-0015 draft:
- `members[].type` gains `pad_footing`, `pile_cap`, `pile` and `strip_footing`. Its description
  states each type's reference line (decision 2).
- Member rules: `allOf` makes `class` required for `pile` and `pile_cap`, fixes their `name` to
  `PILE` / `PILE_CAP` when given, and forbids both names on every other type.
- New optional arrays `slabs`, `polygonal_caps` and `walls`.
- Lot 0: these three get `maxItems: 0`. Lots ≥ 1: three more `anyOf` branches, so a lot may consist
  of slabs, caps or walls only.
- New `$defs` `slab`, `polygonal_cap`, `wall` and `opening`. Outline points reuse ADR-0015's
  `poly_point`.
- Openings: `spec_id` `maxLength` 60, and outline points with `chamfer` `none` only.
- The top-level description.

`thickness` and `height` use `$ref` with a sibling `properties.value.minimum`, the same 2020-12
pattern ADR-0015 uses for grid labels, so a value of 0 or 0.5 is rejected.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:tekla-harness:schema:spec:0.1",
  "title": "Lot spec",
  "description": "Everything the builder needs to create one lot. Units: millimetres, global coordinates unless a field says otherwise. Lot 0 is the setup lot: it holds grids only, and a grid's levels are its Z planes. Lots 1 and above hold members, poly_members, slabs, polygonal_caps and walls, never grids (ADR-0015, ADR-0016). Openings are nested in their slab or wall. Every reference line or face is the drawing's: a member's line as its type states, a slab's or cap's top face, a wall's base line; the CLI maps it to Tekla's Position (ADR-0016 decision 2). Semantic rules not expressible here (spec_id unique across every array and every nested opening; non-zero length and segment length; increasing grid positions on a 0.01 mm step; poly member, outline and opening geometry rules; vertical footings and piles, horizontal strip footings, slabs, caps and wall bases; elevation and grid frame provenance; engineer answers carry their question_id; low confidence anywhere in an item needs a question) are checked by tekla_harness.schemas.check_spec.",
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
    "slabs": {"type": "array", "description": "Horizontal concrete slabs (Tekla ContourPlate, type SLAB), with their openings. Lots 1 and above (ADR-0016).", "items": {"$ref": "#/$defs/slab"}},
    "walls": {"type": "array", "description": "Straight concrete walls (Tekla Beam of type PANEL), with their openings. Lots 1 and above (ADR-0016).", "items": {"$ref": "#/$defs/wall"}},
    "polygonal_caps": {
      "type": "array",
      "description": "Pile caps whose plan is a polygon (3-pile, hexagonal): Tekla ContourPlate (type SLAB), Name PILE_CAP and the item's class tell them from slabs. Lots 1 and above (ADR-0016 decision 3).",
      "items": {"$ref": "#/$defs/polygonal_cap"}
    },
    "open_questions": {
      "type": "array",
      "description": "Question ids from questions.md that affect this lot.",
      "items": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/question_id"},
      "uniqueItems": true
    }
  },
  "if": {"properties": {"lot": {"const": 0}}, "required": ["lot"]},
  "then": {
    "required": ["grids"],
    "properties": {"grids": {"minItems": 1}, "members": {"maxItems": 0}, "poly_members": {"maxItems": 0}, "slabs": {"maxItems": 0}, "walls": {"maxItems": 0}, "polygonal_caps": {"maxItems": 0}}
  },
  "else": {
    "properties": {"grids": {"maxItems": 0}},
    "anyOf": [
      {"properties": {"members": {"minItems": 1}}},
      {"required": ["poly_members"], "properties": {"poly_members": {"minItems": 1}}},
      {"required": ["slabs"], "properties": {"slabs": {"minItems": 1}}},
      {"required": ["polygonal_caps"], "properties": {"polygonal_caps": {"minItems": 1}}},
      {"required": ["walls"], "properties": {"walls": {"minItems": 1}}}
    ]
  },
  "$defs": {
    "member": {
      "type": "object",
      "required": ["spec_id", "type", "profile", "material", "start", "end"],
      "additionalProperties": false,
      "properties": {
        "spec_id": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/spec_id"},
        "type": {
          "enum": ["column", "beam", "brace", "purlin", "girt", "rafter", "other", "pad_footing", "pile_cap", "pile", "strip_footing"],
          "description": "Harness kind. pad_footing and pile_cap are built as Beam PAD_FOOTING, pile as Beam COLUMN, strip_footing as Beam STRIP_FOOTING (ADR-0016). start-end is the drawing's reference line: column bottom centre to top centre; a concrete beam's top centre line; pad_footing and pile_cap top centre to bottom centre; pile head (cut-off) to toe; strip_footing top centre line. The CLI sets Tekla's Position per (type, material type) so the solid lies on the stated side (ADR-0016 decision 2)."
        },
        "mark": {"type": "string", "description": "Member mark as printed on the drawing, e.g. 'C1', 'B12'."},
        "profile": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_string"},
        "material": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_string"},
        "start": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_point"},
        "end": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_point"},
        "rotation_deg": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_number"},
        "name": {
          "type": "string",
          "description": "Tekla Name. Reserved: PILE (the CLI writes it for every pile) and PILE_CAP (every pile cap); a pile may omit it or give PILE, a pile cap PILE_CAP, no other type may use either."
        },
        "class": {"type": "string", "pattern": "^[0-9]{1,3}$"},
        "question_ids": {"type": "array", "items": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/question_id"}, "uniqueItems": true},
        "notes": {"type": "string"}
      },
      "allOf": [
        {"if": {"properties": {"type": {"const": "pile"}}, "required": ["type"]}, "then": {"required": ["class"], "properties": {"name": {"const": "PILE"}}}},
        {"if": {"properties": {"type": {"const": "pile_cap"}}, "required": ["type"]}, "then": {"required": ["class"], "properties": {"name": {"const": "PILE_CAP"}}}},
        {"if": {"properties": {"type": {"not": {"enum": ["pile", "pile_cap"]}}}, "required": ["type"]}, "then": {"properties": {"name": {"not": {"enum": ["PILE", "PILE_CAP"]}}}}}
      ]
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
    },
    "slab": {
      "type": "object",
      "description": "One horizontal concrete slab: Tekla ContourPlate, concrete material (type SLAB). `outline` is the slab's top face, counter-clockwise seen from +Z, every point at the same Z. The CLI builds the contour on the top face, with the Position Depth that puts the thickness below it (value set by To verify C2), and composes the profile from `thickness` (ADR-0016).",
      "required": ["spec_id", "material", "thickness", "outline"],
      "additionalProperties": false,
      "properties": {
        "spec_id": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/spec_id"},
        "mark": {"type": "string", "description": "Slab mark as printed, e.g. 'S1'."},
        "material": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_string"},
        "thickness": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_number", "properties": {"value": {"minimum": 1}}, "description": "Slab thickness, mm."},
        "outline": {
          "type": "array",
          "minItems": 3,
          "description": "Top-face corners in order, global mm. 'arc_point' rounds the run through that corner into an arc (ADR-0015 poly_point); a slab with an arc_point has no openings (check_spec).",
          "items": {"$ref": "#/$defs/poly_point"}
        },
        "openings": {"type": "array", "description": "Through openings, each outline on the slab's top face.", "items": {"$ref": "#/$defs/opening"}},
        "name": {"type": "string", "not": {"enum": ["PILE", "PILE_CAP"]}, "description": "Tekla Name; PILE and PILE_CAP are reserved."},
        "class": {"type": "string", "pattern": "^[0-9]{1,3}$"},
        "question_ids": {"type": "array", "items": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/question_id"}, "uniqueItems": true},
        "notes": {"type": "string"}
      }
    },
    "polygonal_cap": {
      "type": "object",
      "description": "A pile cap whose plan is a polygon: Tekla ContourPlate, concrete material (type SLAB, not PAD_FOOTING). The CLI writes Name PILE_CAP; `class` is required, so reports tell it from slabs by Name and class. `outline` is the cap's top face, counter-clockwise seen from +Z, every point at the same Z; built like a slab (ADR-0016 decision 3). No openings.",
      "required": ["spec_id", "material", "thickness", "outline", "class"],
      "additionalProperties": false,
      "properties": {
        "spec_id": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/spec_id"},
        "mark": {"type": "string", "description": "Cap mark as printed, e.g. 'PC3'."},
        "material": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_string"},
        "thickness": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_number", "properties": {"value": {"minimum": 1}}, "description": "Cap depth, mm."},
        "outline": {"type": "array", "minItems": 3, "description": "Top-face corners in order, global mm.", "items": {"$ref": "#/$defs/poly_point"}},
        "class": {"type": "string", "pattern": "^[0-9]{1,3}$", "description": "Tekla class for pile caps in this project (gate 2)."},
        "question_ids": {"type": "array", "items": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/question_id"}, "uniqueItems": true},
        "notes": {"type": "string"}
      }
    },
    "wall": {
      "type": "object",
      "description": "One straight concrete wall: Tekla Beam of type PANEL, concrete material. `start`-`end` is the wall's base centre line (horizontal); `height` is measured up from it. The CLI uses the base line as the panel's reference line, with the Position that puts the wall above it and centred on it (values set by To verify C2), and composes the profile from `thickness` and `height` (ADR-0016).",
      "required": ["spec_id", "material", "start", "end", "thickness", "height"],
      "additionalProperties": false,
      "properties": {
        "spec_id": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/spec_id"},
        "mark": {"type": "string", "description": "Wall mark as printed, e.g. 'W1', 'V1'."},
        "material": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_string"},
        "start": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_point"},
        "end": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_point"},
        "thickness": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_number", "properties": {"value": {"minimum": 1}}, "description": "Wall thickness, mm."},
        "height": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/sourced_number", "properties": {"value": {"minimum": 1}}, "description": "Wall height above the base line, mm."},
        "openings": {"type": "array", "description": "Through openings, each outline in the wall's vertical centre plane.", "items": {"$ref": "#/$defs/opening"}},
        "name": {"type": "string", "not": {"enum": ["PILE", "PILE_CAP"]}, "description": "Tekla Name; PILE and PILE_CAP are reserved."},
        "class": {"type": "string", "pattern": "^[0-9]{1,3}$"},
        "question_ids": {"type": "array", "items": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/question_id"}, "uniqueItems": true},
        "notes": {"type": "string"}
      }
    },
    "opening": {
      "type": "object",
      "description": "A through opening in its parent slab or wall: a Tekla BooleanPart cut (BOOLEAN_CUT) whose operative part the CLI composes from `outline` and the parent (ADR-0016 decision 6). Same lot as its parent, always. Corners only (no arc_point). spec_id at most 60 characters, so the reserved cutter tag '<spec_id>~CUT' fits 64.",
      "required": ["spec_id", "outline"],
      "additionalProperties": false,
      "properties": {
        "spec_id": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/spec_id", "maxLength": 60},
        "mark": {"type": "string", "description": "Opening mark as printed, if any."},
        "outline": {
          "type": "array",
          "minItems": 3,
          "description": "Opening corners in order, global mm, on the parent's top face (slab) or vertical centre plane (wall); chamfer 'none' only.",
          "items": {"$ref": "#/$defs/poly_point", "properties": {"chamfer": {"const": "none"}}}
        },
        "question_ids": {"type": "array", "items": {"$ref": "urn:tekla-harness:schema:common:0.1#/$defs/question_id"}, "uniqueItems": true},
        "notes": {"type": "string"}
      }
    }
  }
}
```

## 2. `check_spec` additions (Python; ADR-0016 decision 9)

Rules (i)–(q), each with a regression test, in the one `SPEC_RULES_VERSION` bump shared with
ADR-0015. Messages name the JSON pointer, as today.

- **Erratum (2026-11-11, review of P15-5 m-1).** The inside rule is not only a test of the corner
  points: a slab opening edge must also not **properly cross** an edge of the slab outline (each
  segment has its ends strictly on opposite sides of the other's line, by more than 1 mm). Without
  it, an opening whose four corners sit in two arms of a concave (U-shaped) slab passes although
  its middle spans empty space. An edge that touches the outline, or lies within 1 mm of it, is
  still accepted. Wall openings need nothing: a wall rectangle is convex. Approved by the engineer.
- **Fail closed (2026-11-11, review of P15-5 M-1/M-2).** A geometry rule that overflows to `inf` or
  `NaN` refuses with "geometry cannot be evaluated: the coordinates are too large" at the pointer;
  there is no coordinate magnitude bound.

Tolerances:
- **0.1 mm** where a value is meant to be equal: one Z per slab or cap, a horizontal strip footing
  or wall base, a vertical footing or pile, an opening in its parent's plane. These are the same
  values the CLI compares on read-back.
- **1 mm** for distances and containment, as ADR-0015 uses.

Geometry, all in the outline's own plane:
- **Normal.** +Z for slabs, caps and slab openings. For a wall, n = Z × (end − start), normalised.
- **Winding.** Counter-clockwise about n means the signed area is > 0, computed by the shoelace
  formula in a right-handed basis (a, b) with a × b = n. For a wall, a = Z and b = the wall
  direction (Z × direction = n).
- **Simple polygon.** No two non-adjacent edges meet, using a segment-intersection test with the
  1 mm tolerance.
- **Inside.** Every opening corner is inside or within 1 mm of the parent polygon, by a
  point-in-polygon test on the corner points. Openings in a slab whose outline has an `arc_point` are
  refused (rule (m)).
- **Overlap (o).** No edge of one opening crosses an edge of another opening of the same parent, and
  no corner of one lies inside the other.

Elevation paths (rule (p)) use ADR-0015's provenance walk, at any depth of `derived_from`:
- `slabs[*].outline[*]` and `polygonal_caps[*].outline[*]`;
- `walls[*].start` and `walls[*].end`;
- `members[*].start` where `type` is `pad_footing`, `pile_cap` or `pile`;
- `members[*].start` and `.end` where `type` is `strip_footing`;
- `members[*].end` where `type` is `pad_footing` or `pile_cap`: the bottom, derived from the top's
  answer and the depth (Q5 "every elevation"; ADR-0015 rule (f) already covers every member point
  since OQ-B, so this path is listed for clarity, not checked twice).

`members[*].end` of a `pile` (the toe) is exempt (Q14). It falls under the low-confidence rule only.

## 3. Examples

New files `schemas/examples/spec-foundations.example.json` (3.1) and
`schemas/examples/spec-slab-wall.example.json` (3.2). Together they hold one item per kind: pile,
rectangular pile cap, polygonal pile cap, pad footing, strip footing, slab with an opening, and wall
with an opening. Q-010 is the storey-levels answer and Q-012 the concrete grade answer.

### 3.1 Foundation lot

- **Pile** P1 under cap PC1, class `2`; the CLI writes Name `PILE`.
  - The head sits 100 mm into the cap, at −1.400 (`derived` from the plan and the level answer,
    Q5).
  - The toe is **taken from the drawing** (Q14): `derived` from the pile note "L=18m"
    (`pdf_text_layer`) and the head, at −19.400. Its confidence is medium, so it needs no question.
- **Pile cap** PC1, 1200 × 1200 × 800, top −0.700, class `8`; Name `PILE_CAP`. Its bottom is
  `derived` from the cap depth and the level answer.
- **Pad footing** BM-1, 1800 × 1500, top −1.000. Its bottom is `derived` from a depth read by
  vision and the level answer; the depth is low confidence, so the point carries question Q-051.
- **Strip footing** SF1, 800 × 500. Start and end lie on its **top** centre line at −1.000, as the
  native handle requires (Q8). Their provenance is `derived` from the plan line and the level answer.
- **Polygonal cap** PC3: a hexagon for 3 piles, depth 900, top −0.700, class `8`. The CLI writes
  Name `PILE_CAP`.

```json
{
  "schema_version": "0.1",
  "project_id": "demo-house",
  "lot": 1,
  "units": "mm",
  "description": "Synthetic example: foundation lot with one pile, its pile cap, one pad footing, one strip footing and one 3-pile polygonal cap.",
  "members": [
    {
      "spec_id": "L1-P-C2-1",
      "type": "pile",
      "mark": "P1",
      "profile": {
        "value": "200*200",
        "provenance": {"file": "S-100.dxf", "sheet": "S-100", "revision": "A", "region": {"detail": "PILE SECTION"}, "method": "dxf_dimension_text"},
        "confidence": "high"
      },
      "material": {
        "value": "C25/30",
        "provenance": {"file": "S-001.pdf", "sheet": "S-001", "revision": "A", "region": {"page": 1, "detail": "GENERAL NOTES 2.1"}, "method": "engineer_answer", "question_id": "Q-012"},
        "confidence": "high"
      },
      "start": {
        "x": 3000,
        "y": 4000,
        "z": -1400,
        "provenance": {
          "file": "S-100.dxf",
          "sheet": "S-100",
          "revision": "A",
          "region": {"grid_ref": "C/2"},
          "method": "derived",
          "derived_from": [
            {"file": "S-100.dxf", "sheet": "S-100", "revision": "A", "method": "dxf_entity"},
            {"file": "S-101.dxf", "sheet": "S-101", "revision": "A", "region": {"detail": "PILE CAP PC1"}, "method": "dxf_dimension_text"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "high"
      },
      "end": {
        "x": 3000,
        "y": 4000,
        "z": -19400,
        "provenance": {
          "file": "S-001.pdf",
          "sheet": "S-001",
          "revision": "A",
          "region": {"page": 1, "detail": "PILE NOTES L=18m"},
          "method": "derived",
          "derived_from": [
            {"file": "S-001.pdf", "sheet": "S-001", "revision": "A", "region": {"page": 1, "detail": "PILE NOTES L=18m"}, "method": "pdf_text_layer"},
            {
              "file": "S-100.dxf",
              "sheet": "S-100",
              "revision": "A",
              "region": {"grid_ref": "C/2"},
              "method": "derived",
              "derived_from": [{"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}]
            }
          ]
        },
        "confidence": "medium"
      },
      "class": "2"
    },
    {
      "spec_id": "L1-PC-C2",
      "type": "pile_cap",
      "mark": "PC1",
      "profile": {
        "value": "1200*1200",
        "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "A", "region": {"detail": "PILE CAP PC1"}, "method": "dxf_dimension_text"},
        "confidence": "high"
      },
      "material": {"value": "C25/30", "provenance": {"file": "S-001.pdf", "sheet": "S-001", "revision": "A", "method": "engineer_answer", "question_id": "Q-012"}, "confidence": "high"},
      "start": {
        "x": 3000,
        "y": 4000,
        "z": -700,
        "provenance": {
          "file": "S-101.dxf",
          "sheet": "S-101",
          "revision": "A",
          "region": {"detail": "PILE CAP PC1"},
          "method": "derived",
          "derived_from": [
            {"file": "S-101.dxf", "sheet": "S-101", "revision": "A", "method": "dxf_entity"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "high"
      },
      "end": {
        "x": 3000,
        "y": 4000,
        "z": -1500,
        "provenance": {
          "file": "S-101.dxf",
          "sheet": "S-101",
          "revision": "A",
          "region": {"detail": "PILE CAP PC1"},
          "method": "derived",
          "derived_from": [
            {"file": "S-101.dxf", "sheet": "S-101", "revision": "A", "method": "dxf_dimension_text"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "high"
      },
      "rotation_deg": {"value": 0, "provenance": {"file": "S-100.dxf", "sheet": "S-100", "revision": "A", "method": "dxf_entity"}, "confidence": "high"},
      "class": "8"
    },
    {
      "spec_id": "L1-F-A1",
      "type": "pad_footing",
      "mark": "BM-1",
      "profile": {"value": "1800*1500", "provenance": {"file": "S-102.dxf", "sheet": "S-102", "revision": "B", "region": {"detail": "FOOTING SCHEDULE"}, "method": "table"}, "confidence": "medium"},
      "material": {"value": "C25/30", "provenance": {"file": "S-001.pdf", "sheet": "S-001", "revision": "A", "method": "engineer_answer", "question_id": "Q-012"}, "confidence": "high"},
      "start": {
        "x": 9000,
        "y": 4000,
        "z": -1000,
        "provenance": {
          "file": "S-102.dxf",
          "sheet": "S-102",
          "revision": "B",
          "region": {"grid_ref": "A/1"},
          "method": "derived",
          "derived_from": [
            {"file": "S-102.dxf", "sheet": "S-102", "revision": "B", "method": "dxf_entity"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "high"
      },
      "end": {
        "x": 9000,
        "y": 4000,
        "z": -1500,
        "provenance": {
          "file": "S-102.dxf",
          "sheet": "S-102",
          "revision": "B",
          "region": {"detail": "FOOTING SCHEDULE"},
          "method": "derived",
          "derived_from": [
            {"file": "S-102.dxf", "sheet": "S-102", "revision": "B", "region": {"detail": "FOOTING SCHEDULE"}, "method": "vision"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "low"
      },
      "class": "8",
      "question_ids": ["Q-051"]
    },
    {
      "spec_id": "L1-SF-D",
      "type": "strip_footing",
      "mark": "SF1",
      "profile": {"value": "800*500", "provenance": {"file": "S-102.dxf", "sheet": "S-102", "revision": "B", "region": {"detail": "SECTION 1-1"}, "method": "dxf_dimension_text"}, "confidence": "high"},
      "material": {"value": "C25/30", "provenance": {"file": "S-001.pdf", "sheet": "S-001", "revision": "A", "method": "engineer_answer", "question_id": "Q-012"}, "confidence": "high"},
      "start": {
        "x": 0,
        "y": 10000,
        "z": -1000,
        "provenance": {
          "file": "S-102.dxf",
          "sheet": "S-102",
          "revision": "B",
          "region": {"grid_ref": "D/1"},
          "method": "derived",
          "derived_from": [
            {"file": "S-102.dxf", "sheet": "S-102", "revision": "B", "method": "dxf_entity"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "high"
      },
      "end": {
        "x": 9000,
        "y": 10000,
        "z": -1000,
        "provenance": {
          "file": "S-102.dxf",
          "sheet": "S-102",
          "revision": "B",
          "region": {"grid_ref": "D/3"},
          "method": "derived",
          "derived_from": [
            {"file": "S-102.dxf", "sheet": "S-102", "revision": "B", "method": "dxf_entity"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "high"
      },
      "class": "8"
    }
  ],
  "polygonal_caps": [
    {
      "spec_id": "L1-PC3-E2",
      "mark": "PC3",
      "material": {"value": "C25/30", "provenance": {"file": "S-001.pdf", "sheet": "S-001", "revision": "A", "method": "engineer_answer", "question_id": "Q-012"}, "confidence": "high"},
      "thickness": {"value": 900, "provenance": {"file": "S-101.dxf", "sheet": "S-101", "revision": "A", "region": {"detail": "PILE CAP PC3"}, "method": "dxf_dimension_text"}, "confidence": "high"},
      "outline": [
        {
          "x": 13900,
          "y": 3400,
          "z": -700,
          "chamfer": "none",
          "provenance": {
            "file": "S-101.dxf",
            "sheet": "S-101",
            "revision": "A",
            "region": {"detail": "PILE CAP PC3"},
            "method": "derived",
            "derived_from": [
              {"file": "S-101.dxf", "sheet": "S-101", "revision": "A", "method": "dxf_entity"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        },
        {
          "x": 16100,
          "y": 3400,
          "z": -700,
          "chamfer": "none",
          "provenance": {
            "file": "S-101.dxf",
            "sheet": "S-101",
            "revision": "A",
            "region": {"detail": "PILE CAP PC3"},
            "method": "derived",
            "derived_from": [
              {"file": "S-101.dxf", "sheet": "S-101", "revision": "A", "method": "dxf_entity"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        },
        {
          "x": 16650,
          "y": 4350,
          "z": -700,
          "chamfer": "none",
          "provenance": {
            "file": "S-101.dxf",
            "sheet": "S-101",
            "revision": "A",
            "region": {"detail": "PILE CAP PC3"},
            "method": "derived",
            "derived_from": [
              {"file": "S-101.dxf", "sheet": "S-101", "revision": "A", "method": "dxf_entity"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        },
        {
          "x": 15550,
          "y": 6250,
          "z": -700,
          "chamfer": "none",
          "provenance": {
            "file": "S-101.dxf",
            "sheet": "S-101",
            "revision": "A",
            "region": {"detail": "PILE CAP PC3"},
            "method": "derived",
            "derived_from": [
              {"file": "S-101.dxf", "sheet": "S-101", "revision": "A", "method": "dxf_entity"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        },
        {
          "x": 14450,
          "y": 6250,
          "z": -700,
          "chamfer": "none",
          "provenance": {
            "file": "S-101.dxf",
            "sheet": "S-101",
            "revision": "A",
            "region": {"detail": "PILE CAP PC3"},
            "method": "derived",
            "derived_from": [
              {"file": "S-101.dxf", "sheet": "S-101", "revision": "A", "method": "dxf_entity"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        },
        {
          "x": 13350,
          "y": 4350,
          "z": -700,
          "chamfer": "none",
          "provenance": {
            "file": "S-101.dxf",
            "sheet": "S-101",
            "revision": "A",
            "region": {"detail": "PILE CAP PC3"},
            "method": "derived",
            "derived_from": [
              {"file": "S-101.dxf", "sheet": "S-101", "revision": "A", "method": "dxf_entity"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        }
      ],
      "class": "8"
    }
  ],
  "open_questions": ["Q-051"]
}
```

### 3.2 Slab with a stair opening; wall with a door opening (lot 4)

- **Slab** S1: the top face at +3.600 is the storey level (Q-010). The CLI builds the contour on
  that face, with the Depth that puts the 120 mm below it (Q8, C2). No half-thickness shift remains.
- **Wall** V1: base centre line at +3.600 on y = 9000, height 3480. The CLI uses the base line as
  the panel's reference line.
- **Door** D1:
  - It lies in the wall's centre plane y = 9000, counter-clockwise about n = Z × (+X) = +Y.
  - It is rectangular, so its cutter is a `Beam` along +Y through the door's centre, 300 mm long
    (200 + 100).
  - It touches the wall base, which rule (n) allows ("inside or on"). Its bottom edge is therefore
    pushed 50 mm below the base in the composed cutter (To verify C11).

```json
{
  "schema_version": "0.1",
  "project_id": "demo-house",
  "lot": 4,
  "units": "mm",
  "description": "Synthetic example: a 120 mm slab on level +3.600 with one stair opening, and a 200 mm wall with one door opening.",
  "members": [],
  "slabs": [
    {
      "spec_id": "L4-S-A1B2",
      "mark": "S1",
      "material": {"value": "C25/30", "provenance": {"file": "S-001.pdf", "sheet": "S-001", "revision": "A", "method": "engineer_answer", "question_id": "Q-012"}, "confidence": "high"},
      "thickness": {"value": 120, "provenance": {"file": "S-103.dxf", "sheet": "S-103", "revision": "A", "region": {"detail": "SLAB NOTE S=120"}, "method": "dxf_entity"}, "confidence": "high"},
      "outline": [
        {
          "x": 0,
          "y": 0,
          "z": 3600,
          "chamfer": "none",
          "provenance": {
            "file": "S-103.dxf",
            "sheet": "S-103",
            "revision": "A",
            "region": {"grid_ref": "A/1"},
            "method": "derived",
            "derived_from": [
              {"file": "S-103.dxf", "sheet": "S-103", "revision": "A", "method": "dxf_entity"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        },
        {
          "x": 6000,
          "y": 0,
          "z": 3600,
          "chamfer": "none",
          "provenance": {
            "file": "S-103.dxf",
            "sheet": "S-103",
            "revision": "A",
            "region": {"grid_ref": "A/2"},
            "method": "derived",
            "derived_from": [
              {"file": "S-103.dxf", "sheet": "S-103", "revision": "A", "method": "dxf_entity"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        },
        {
          "x": 6000,
          "y": 7500,
          "z": 3600,
          "chamfer": "none",
          "provenance": {
            "file": "S-103.dxf",
            "sheet": "S-103",
            "revision": "A",
            "region": {"grid_ref": "B/2"},
            "method": "derived",
            "derived_from": [
              {"file": "S-103.dxf", "sheet": "S-103", "revision": "A", "method": "dxf_entity"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        },
        {
          "x": 0,
          "y": 7500,
          "z": 3600,
          "chamfer": "none",
          "provenance": {
            "file": "S-103.dxf",
            "sheet": "S-103",
            "revision": "A",
            "region": {"grid_ref": "B/1"},
            "method": "derived",
            "derived_from": [
              {"file": "S-103.dxf", "sheet": "S-103", "revision": "A", "method": "dxf_entity"},
              {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
            ]
          },
          "confidence": "high"
        }
      ],
      "openings": [
        {
          "spec_id": "L4-S-A1B2-O1",
          "mark": "STAIR",
          "outline": [
            {
              "x": 1000,
              "y": 1000,
              "z": 3600,
              "chamfer": "none",
              "provenance": {"file": "S-103.dxf", "sheet": "S-103", "revision": "A", "region": {"detail": "STAIR OPENING"}, "method": "dxf_dimension_text"},
              "confidence": "high"
            },
            {
              "x": 3400,
              "y": 1000,
              "z": 3600,
              "chamfer": "none",
              "provenance": {"file": "S-103.dxf", "sheet": "S-103", "revision": "A", "region": {"detail": "STAIR OPENING"}, "method": "dxf_dimension_text"},
              "confidence": "high"
            },
            {
              "x": 3400,
              "y": 2200,
              "z": 3600,
              "chamfer": "none",
              "provenance": {"file": "S-103.dxf", "sheet": "S-103", "revision": "A", "region": {"detail": "STAIR OPENING"}, "method": "dxf_dimension_text"},
              "confidence": "high"
            },
            {
              "x": 1000,
              "y": 2200,
              "z": 3600,
              "chamfer": "none",
              "provenance": {"file": "S-103.dxf", "sheet": "S-103", "revision": "A", "region": {"detail": "STAIR OPENING"}, "method": "dxf_dimension_text"},
              "confidence": "high"
            }
          ]
        }
      ],
      "class": "5"
    }
  ],
  "walls": [
    {
      "spec_id": "L4-W-C-12",
      "mark": "V1",
      "material": {"value": "C25/30", "provenance": {"file": "S-001.pdf", "sheet": "S-001", "revision": "A", "method": "engineer_answer", "question_id": "Q-012"}, "confidence": "high"},
      "start": {
        "x": 0,
        "y": 9000,
        "z": 3600,
        "provenance": {
          "file": "S-104.dxf",
          "sheet": "S-104",
          "revision": "A",
          "region": {"grid_ref": "C/1"},
          "method": "derived",
          "derived_from": [
            {"file": "S-104.dxf", "sheet": "S-104", "revision": "A", "method": "dxf_entity"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "high"
      },
      "end": {
        "x": 4000,
        "y": 9000,
        "z": 3600,
        "provenance": {
          "file": "S-104.dxf",
          "sheet": "S-104",
          "revision": "A",
          "region": {"grid_ref": "C/2"},
          "method": "derived",
          "derived_from": [
            {"file": "S-104.dxf", "sheet": "S-104", "revision": "A", "method": "dxf_entity"},
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"}
          ]
        },
        "confidence": "high"
      },
      "thickness": {"value": 200, "provenance": {"file": "S-104.dxf", "sheet": "S-104", "revision": "A", "region": {"grid_ref": "C/1-2"}, "method": "dxf_dimension_text"}, "confidence": "high"},
      "height": {
        "value": 3480,
        "provenance": {
          "file": "S-201.dxf",
          "sheet": "S-201",
          "revision": "A",
          "method": "derived",
          "derived_from": [
            {"file": "S-201.dxf", "sheet": "S-201", "revision": "A", "method": "engineer_answer", "question_id": "Q-010"},
            {"file": "S-103.dxf", "sheet": "S-103", "revision": "A", "region": {"detail": "SLAB NOTE S=120"}, "method": "dxf_entity"}
          ]
        },
        "confidence": "high"
      },
      "openings": [
        {
          "spec_id": "L4-W-C-12-D1",
          "mark": "D1",
          "outline": [
            {
              "x": 1000,
              "y": 9000,
              "z": 3600,
              "chamfer": "none",
              "provenance": {"file": "S-104.dxf", "sheet": "S-104", "revision": "A", "region": {"detail": "WALL V1 ELEVATION"}, "method": "dxf_dimension_text"},
              "confidence": "high"
            },
            {
              "x": 1000,
              "y": 9000,
              "z": 5700,
              "chamfer": "none",
              "provenance": {"file": "S-104.dxf", "sheet": "S-104", "revision": "A", "region": {"detail": "WALL V1 ELEVATION"}, "method": "dxf_dimension_text"},
              "confidence": "high"
            },
            {
              "x": 1900,
              "y": 9000,
              "z": 5700,
              "chamfer": "none",
              "provenance": {"file": "S-104.dxf", "sheet": "S-104", "revision": "A", "region": {"detail": "WALL V1 ELEVATION"}, "method": "dxf_dimension_text"},
              "confidence": "high"
            },
            {
              "x": 1900,
              "y": 9000,
              "z": 3600,
              "chamfer": "none",
              "provenance": {"file": "S-104.dxf", "sheet": "S-104", "revision": "A", "region": {"detail": "WALL V1 ELEVATION"}, "method": "dxf_dimension_text"},
              "confidence": "high"
            }
          ]
        }
      ],
      "class": "6"
    }
  ],
  "open_questions": []
}
```

## 4. `docs/tekla-cli-contract.md` additions (apply after the ADR-0015 §4 diff, base 09274de)

> **Erratum (2026-11-11, review of P15-8).** The diff below was applied as accepted, and it dropped
> refusals that ADR-0016 and this section's own preamble require. The contract gained these
> sentences after the review; the diff is not rewritten.
> - M-2: rule 12 names both wall-cutter routes and refuses a non-rectangular wall opening until C2
>   and C12 pass (decision 6).
> - M-3: rule 12 requires checking each cut tag write and reading the tags back, exit `3` on
>   failure (decisions 6 and 7).
> - M-5: new rule 13 lists the gates C4, C5, C6, C7 or C8, C9, C2 and C12, and C1 for walls.
> - M-6: rule 11 refuses per (kind x material type) row, steel and the array kinds included
>   (decision 2).
> - m-4: rule 6 matches the reserved Names `PILE`/`PILE_CAP` only and compares Position for steel
>   and concrete members (decision 8).
> - m-5: the `rollback` row lists, not deletes, a cutter with this run's tags and no journal entry.
> - m-6: rule 12 says `update` never deletes; an `update` adding an opening in the C7-failed
>   fallback refuses (exit `5`), the engineer rolls back and rebuilds (engineer decision
>   2026-11-11).
> - m-7: rule 5 points to rule 12's one delete exception.
> - m-8: the exit `3` list names a failed cut tag write or read-back.
> - m-12: rules 7, 10 (both diffs) and 11 rewrapped, a blank line in Open questions removed.
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

No new subcommand and no new exit code. The new refusals map onto the existing codes:
- `1`:
  - a non-concrete material, or a composed profile not in the catalog (`validate`, nothing written);
  - a leftover cutter, a reserved-name mismatch, or any "differs" on resume;
- `3`: cut tags that cannot be written or read back;
- `4`: a wrong `Beam.Type`/`ContourPlate.Type` after `Insert`, or a part still bound to a level
  (stop, keep, journal);
- `5`:
  - an opening before C4 and C7/C8 pass;
  - a non-rectangular wall opening before C2/C12;
  - an opening change in `update` before C9;
  - a kind, concrete or steel, whose Position values are not yet in the table.

Rule 12 also records the one exception to rule 5 (engineer, 2026-11-11, OQ-D): in the fallback
only, `build` deletes the tagged cutter it just inserted, that GUID only, while it carries this
run's tags, and journals it. Rule 11 keys the Position table on (spec `type` × material type), so
steel beams and braces, both Tekla `BEAM`, get different rows (OQ-C).

```diff
--- a/docs/tekla-cli-contract.md
+++ b/docs/tekla-cli-contract.md
@@ -36,14 +36,14 @@
 
 | Subcommand | Class | Purpose |
 |---|---|---|
-| `info` | read | Tekla version, open model, catalogs available, tag UDA definitions (parts and `CatalogObjectTypeEnum.GRID`) |
-| `validate` | read | Check profiles/materials/components in a spec exist in the catalogs (members and poly members); poly member point count within `Contour.MAX_POLYBEAM_POINTS` |
-| `query` | read | Objects by `LOT` / `RUN_ID` / `SPEC_ID` / GUID; grids by enumerating every `Grid` and reading its tags (no UDA filter); untagged grids listed separately |
+| `info` | read | Tekla version, open model, catalogs available, tag UDA definitions for every (Tekla type × material type) pair a spec can produce, and `CatalogObjectTypeEnum.GRID` |
+| `validate` | read | Check profiles/materials/components in a spec exist in the catalogs (members, poly members, slabs, polygonal caps, walls, and the profiles the CLI composes for them and for opening cutters); poly member point count within `Contour.MAX_POLYBEAM_POINTS`, outline and opening point counts within `Contour.MAX_CONTOUR_POINTS`; material type `MATERIAL_CONCRETE` for footings, pile caps, piles, slabs, polygonal caps and walls |
+| `query` | read | Objects by `LOT` / `RUN_ID` / `SPEC_ID` / GUID; grids by enumerating every `Grid` and reading its tags (no UDA filter); untagged grids listed separately; opening cuts by enumerating each found slab's or wall's `GetBooleans()` and reading the cut's tags (no UDA filter) |
 | `selected` | read | Objects currently selected in the Tekla UI |
-| `export` | read | CSV + IFC of a lot or run (writes files, not the model; may change the UI selection, restores it afterwards). CSV adds one row per grid (frame), one per grid line or level and one per polybeam point; grids are not exported to IFC |
-| `build` | **write** | Create the objects of one lot from `spec.json`, tag them, one commit; resumes a stopped run. Lot 0 builds grids (levels are their Z planes); lots ≥ 1 build members and poly members |
-| `update` | **write** | Modify objects of one lot from a corrected spec; for lot 0 only additive while a member lot exists (rule 9) |
-| `rollback` | **write** | Delete all objects of a `RUN_ID`, grids included; run only on the engineer's request, never automatically; refused for lot 0 while a member lot exists (rule 9) |
+| `export` | read | CSV + IFC of a lot or run (writes files, not the model; may change the UI selection, restores it afterwards). CSV adds one row per grid (frame), one per grid line or level, one per polybeam point and one per slab, cap or opening contour point, and the profile, Position, cast unit type and name of each concrete part; grids are not exported to IFC, and IFC is a count check only for slabs, caps, walls and cuts |
+| `build` | **write** | Create the objects of one lot from `spec.json`, tag them, one commit; resumes a stopped run. Lot 0 builds grids (levels are their Z planes); lots ≥ 1 build members, poly members, slabs, polygonal caps and walls, each slab or wall followed by its opening cuts |
+| `update` | **write** | Modify objects of one lot from a corrected spec; for lot 0 only additive while a member lot exists (rule 9); an opening is modified in place (rule 12) |
+| `rollback` | **write** | Delete all objects of a `RUN_ID`, grids and opening cuts included (cuts before their parent), and the journalled cutters carrying this run's tags; run only on the engineer's request, never automatically; refused for lot 0 while a member lot exists (rule 9) |
 
 Any subcommand not listed as **read** is treated as a write by the guard hook (fail closed).
 Adding a read subcommand requires updating `READ_SUBCOMMANDS` in
@@ -84,10 +84,16 @@
    as amended by ADR-0015. The kind compared is the Tekla kind the spec item maps to (`brace`,
    `purlin`, `girt`, `rafter`, `other` are kind `beam`); a grid item matches only kind `grid`, a
    poly member only kind `polybeam` (its spec `type` is not compared); "differs" per ADR-0015
-   decision 9.
+   decision 9. Concrete parts and openings ([ADR-0016](decisions/0016-lot-spec-slabs-footings-piles-walls.md)
+   decision 8): a `pile` matches kind `column` named `PILE`, a `pile_cap` kind `pad_footing` named
+   `PILE_CAP`, a slab kind `slab` not named `PILE_CAP`, a polygonal cap kind `slab` named
+   `PILE_CAP`, a wall kind `panel`, an opening kind `cut` whose father is its parent's object; for
+   these kinds a different name is a conflict, and "differs" also covers the Position, the cast unit
+   type and the composed profile.
 7. Read the spec closed-world: any key or enum value outside the spec schema, at any nesting level
    the CLI interprets, refuses (exit `5`), so no spec item is ever skipped or misread silently.
-   `spec_id` is unique across `members`, `poly_members` and `grids`. A receipt whose
+   `spec_id` is unique across `members`, `poly_members`, `grids`, `slabs`, `polygonal_caps`,
+   `walls` and every nested opening. A receipt whose
    `rules_version` is below the CLI's minimum refuses (exit `5`).
 8. Lot 0 holds grids only and lots ≥ 1 hold no grids; anything else refuses (exit `5`). A grid
    with `rotation_deg` 0 is built in the global work plane with `Origin` = its origin plus its
@@ -114,10 +120,32 @@
    untagged grids, and `rollback` of lot 0 takes no such flag.
 10. Tekla 2026: parts are not bound to levels. A write command first checks that this CLI can read
     the level members; one built without them refuses on Tekla 2026 or later (exit `3`). The CLI
-    sets the unbound value (To verify T4); a part whose `StartLevelName` or `EndLevelName` is still
-    set after `Insert` stops the run as in rule 5 (keep, journal, exit `4`); one found in the
+    sets the unbound value (To verify T4); a part whose `StartLevelName` or `EndLevelName` (beams,
+    polybeams) or `LevelName` (contour plates) is still set after `Insert` stops the run as in rule 5 (keep, journal, exit `4`); one found in the
     snapshot when planning a resume differs from its spec item (exit `1`). If T4 shows that the API
     cannot unbind, no write route opens until a new ADR.
+11. Concrete parts (ADR-0016). Pad footings and pile caps are a `Beam` of type `PAD_FOOTING`, piles
+    of type `COLUMN` with Name `PILE`, strip footings of type `STRIP_FOOTING`, walls of type
+    `PANEL`; slabs and polygonal caps a `ContourPlate` (a polygonal cap with Name `PILE_CAP`, every
+    pile cap likewise). The reference line or contour is the spec's own (top line, top face, base
+    line, head to toe). Steel members: a beam's line is its top-of-steel centre line, a column's
+    and a brace's their centroid axis. The CLI sets the `Position` per (spec `type` × material
+    type) from one table whose values come from To verify C2, and refuses (exit `5`) a kind whose
+    values are not yet in the table. `CastUnitType` is `CAST_IN_PLACE` for concrete parts. After `Insert` the CLI reads back `Beam.Type`
+    and `ContourPlate.Type` (`SLAB`); any other value stops the run as in rule 5.
+12. Openings (ADR-0016). Each opening is a `BooleanPart` of type `BOOLEAN_CUT` whose father is its
+    parent's object, built right after the parent in the same command and tagged like a part.
+    Refused (exit `5`) until To verify C4 (cut tags persist) and C7 or C8 pass. The operative part
+    (class `BooleanPart.BooleanOperativeClassName`) is composed from the opening and its parent and
+    is never inserted (C7). Only if C7 fails and C8 passes: it is inserted with `LOT`, `RUN_ID` and
+    the reserved `SPEC_ID` `<opening spec_id>~CUT`, journalled with role `cutter`, and deleted
+    after the cut's `Insert`: the only delete inside `build`, an exception to rule 5 for that GUID
+    only, while it carries this run's tags, and journalled; one left by a stopped run is a
+    conflict on resume (exit `1`), never deleted by `build`. Cuts are looked up by enumerating each
+    found parent's `GetBooleans()` plus the journal GUIDs. `update` modifies an opening in place
+    through `BooleanPart.OperativePart` and `Modify`, keeping its GUID, whenever the composed
+    cutter changes; until To verify C9 passes, an `update` that changes an opening refuses
+    (exit `5`).
 
 ## Open questions
 
@@ -125,6 +153,11 @@
   rounds them, grid UDAs, polybeam arc read-back and point limit, 2026 level binding (first test on
   2026), string limits, rotated and one-direction grids, additive grid `Modify`, the model-wide
   `LOT` enumeration.
+- ADR-0016 To verify C1–C16 (`tekla/api-notes.md`): composed concrete profiles and their axes,
+  native-handle `Position` signs, contour read-back, UDAs on a cut, cut read-back, cascade delete,
+  operative part never inserted or tagged, opening modify in place, wall cutters, flush cuts,
+  work-plane side effects, UI copy of cuts, piles as columns, contour point limit, IFC entity of
+  polygonal caps.
 
 - Whether objects inserted before a crash, without `CommitChanges`, persist
   (`tekla/api-notes.md`, To verify #9).
```

## 5. `tekla/api-notes.md` additions ("To verify on the test model")

Every check runs with the global work plane set (ADR-0015 decision 2), unless it names another. Run
on the 2026 test model after ADR-0015's T4.
- **C1. Composed profiles.**
  - Does a concrete `ContourPlate` accept `Profile.ProfileString = "120"`, or does it need
    `"PL120"` (K1's example uses `PL200`)? Does `Select()` return the string as written?
  - Panel: is `"200*3480"` 200 thick and 3480 high (K11 says "thickness × height")?
  - Pad footing `"1800*1500"` at `rotation_deg` 0: which number lies along global X?
  - Strip footing `"800*500"`: which number is vertical?
  - Opening cutter `Beam` `"900*2150"`: which number is vertical?
  - Do round sections (`D1200`, or the company's round profile) work for caps and piles?
  - Does a Beam of type `PAD_FOOTING`, `STRIP_FOOTING`, `PANEL` or `COLUMN` with a concrete material
    keep its `Type` after `Insert`?
- **C2. Native-handle Position** (Q8). For each row of ADR-0016 decision 2, which Plane, Depth,
  Rotation and offsets put the solid on the stated side:
  - a horizontal slab or cap contour, counter-clockwise and clockwise seen from +Z: thickness below
    the face;
  - a concrete beam and a strip footing on their top line: below it, centred across;
  - a panel on its base line, in both line directions: above it, centred across the thickness;
  - a column, pad, cap and pile: centred, with K12's `MIDDLE`/`MIDDLE`/`FRONT` confirmed on 2026;
  - steel (OQ-C): a beam on its top-of-steel centre line, below it and centred across; a column and
    a brace on their centroid axis, centred.

  Also: with a work plane whose XY plane is a wall's centre plane (`SetCurrentTransformationPlane`,
  K19), does an operative `ContourPlate`'s thickness run along the wall normal? And does setting the
  global plane back leave the cut unchanged?
- **C3. Contour read-back.** Does `ContourPlate.Contour` after `Select()` return the same point
  count, order, start point and winding, the coordinates within 0.1 mm, and the same chamfer types?
  Does Tekla reverse a clockwise contour?
- **C4. UDAs on a cut.** Does `SetUserProperty("LOT", …)` on an inserted `BooleanPart` return true,
  persist after save and reopen, and read back? Which `objects.inp` section, if any, defines them?
  No `CatalogObjectTypeEnum` value covers booleans (K17).
- **C5. Cut read-back.**
  - Does `BooleanPart.Select()` give `Father`, `Type`, and an `OperativePart` whose contour or line,
    profile and Position can be read (K13: the copy "has the same identifier as the boolean part")?
    Check this both when the operative part was never inserted and when it was deleted after the
    cut.
  - Does the parent's `GetBooleans()` return the cut?
- **C6. Delete.** Does `Delete()` of a slab or wall also delete its cuts? Does `Delete()` of a cut
  restore the parent's solid?
- **C7. Operative part never inserted.** Does `SetOperativePart` + `Insert()` work with an operative
  `ContourPlate`, and with a `Beam`, that was never inserted (class `BooleanOperativeClassName`
  set)? If it does, no transient part is ever created.
- **C8. Tagged cutter (fallback).**
  - On an inserted operative part, do `LOT`, `RUN_ID` and `SPEC_ID` `<id>~CUT` (up to 64
    characters, with `~`) persist and read back?
  - Does the normal UDA lookup find it?
  - After the cut's `Insert` and the cutter's `Delete()`, is the cut intact?
- **C9. Opening modified in place.** Edit `BooleanPart.OperativePart`'s contour or profile and call
  `Modify` (K13). Is the GUID kept? Does the parent's solid update? Does the read-back show the new
  geometry?
- **C10. Rectangular wall opening.** Take a `Beam` operative part along the wall normal through the
  opening centre, length thickness + 100, profile width × height. Is the cut correct in both wall
  directions, and centred on the axis with Plane/Depth `MIDDLE`?
- **C11. Flush cutter faces.** A cutter face that coincides with the parent's edge (a door at the
  wall base, an opening at a slab edge): is the solid clean? Does the 50 mm outward extension
  change the result?
- **C12. Work-plane side effects** (with ADR-0015 T7). Does `SetCurrentTransformationPlane` change
  the work plane the engineer sees in the UI? What state is left if the CLI dies before setting the
  global plane back?
- **C13. UI copy.** When the engineer copies a tagged slab with a cut in the UI, do the cut's tags
  copy? Without an `objects.inp` section for booleans, `unique_attribute` cannot be set for them.
- **C14. Pile as a column.** Is a `COLUMN` with its start above its end (pile head to toe) accepted?
  How do its rotation convention and its drawings behave compared with a normal column?
- **C15. Contour point limit.** What is the value of `Contour.MAX_CONTOUR_POINTS` for slab, cap and
  opening outlines?
- **C16. IFC entity of a polygonal cap.** A `ContourPlate` slab named `PILE_CAP`: which IFC entity
  does the export write (`IfcSlab`, `IfcFooting`)? Can a per-part setting make it a footing?

## 6. CHANGELOG entry (Unreleased → Changed)

```markdown
- `spec.schema.json` (0.1, ADR-0016): `members[].type` gains `pad_footing`, `pile_cap`, `pile`,
  `strip_footing` (reference lines per type; `class` required and Names `PILE`/`PILE_CAP` reserved
  for piles and pile caps); new `slabs` (horizontal ContourPlate, top-face outline, thickness),
  `polygonal_caps` (ContourPlate pile caps, class required) and `walls` (straight PANEL, base centre
  line, thickness, height); slabs and walls carry nested `openings` (BooleanPart cuts, corners
  only, `spec_id` at most 60 characters); lots ≥ 1 may hold only slabs, caps or walls; lot 0 holds
  none.
```

## API facts relied on

Status as in `tekla/api-notes.md`:
- `nuget-metadata`: the shipped XML doc, read from the package;
- `doc`: a Trimble page fetched on 2026-11-10;
- `not-found`: looked for, and no primary source has it.

Packages, each from `https://api.nuget.org/v3-flatcontainer/<id>/<version>/`:
- **PKG24** = `Tekla.Structures.Model` 2024.0.4 (`lib/net48/Tekla.Structures.Model.xml`);
- **PKG26** = `Tekla.Structures.Model` 2026.0.3 (`lib/netstandard2.0/…xml`), the target version
  (Q1);
- **CAT24** and **CAT26** = `Tekla.Structures.Catalogs` 2024.0.4 and 2026.0.3.

The review re-checked these on 2026-11-11, and K12 and K13 are corrected below. ADR-0015's F1–F18
are reused as cited, in particular:
- F2: chamfers and `ContourPoint`;
- F3: no loops, and `MAX_CONTOUR_POINTS`;
- F5: the 2026 level members;
- F14: Trimble's `objects.inp` parser has no boolean section;
- F17 and F18: arc points.

| # | Fact | Version | Source | Status |
|---|---|---|---|---|
| K1 | `ContourPlate` "represents a part made with a contour, such as, a concrete slab"; example `CP.Profile.ProfileString = "PL200"`; `AddContourPoint` (false "if there is no more space"), `Contour`, `Insert` ("All the attributes must be set"), `Modify` ("The identifier must be set"), `Select`, `Delete`, `GetContourPolycurve` | 2024, 2026 | PKG24/PKG26 `T:Tekla.Structures.Model.ContourPlate` and members; https://developer.tekla.com/doc/tekla-structures/2026/contour-plate-class-71241 | nuget-metadata, doc |
| K2 | `ContourPlate.Type` is read-only: "In creation, the type is defined based on the material. If the material is concrete, the type will be slab, otherwise plate"; `ContourPlateTypeEnum` = `UNKNOWN, PLATE, SLAB` | 2024, 2026 | PKG24 `P:…ContourPlate.Type`, `T:…ContourPlateTypeEnum` | nuget-metadata |
| K3 | `Beam.BeamTypeEnum` = `BEAM, COLUMN, PANEL, STRIP_FOOTING, PAD_FOOTING`; "The strip and pad footings are valid only if the material type of the beam is concrete"; `Beam(BeamTypeEnum)` constructor; `Beam.Type` "read-only … default type for a new beam instance is beam" | 2024, 2026 | PKG24 `T:…Beam.BeamTypeEnum`, `M:…Beam.#ctor(…BeamTypeEnum)`, `P:…Beam.Type` | nuget-metadata |
| K4 | `PolyBeam.PolyBeamTypeEnum` = `BEAM, COLUMN, PANEL, STRIP_FOOTING`; `PolyBeam(PolyBeamTypeEnum)`; `PolyBeam.Type` read-only | 2024, 2026 | PKG24 `T:…PolyBeam.PolyBeamTypeEnum`, `P:…PolyBeam.Type` | nuget-metadata |
| K5 | No pile value in `ModelObjectEnum`, `BeamTypeEnum`, `PolyBeamTypeEnum` or `CatalogObjectTypeEnum` | 2024, 2026 | full enumerations in PKG24, PKG26, CAT24 | not-found |
| K6 | `Position`: `PlaneEnum` `LEFT/MIDDLE/RIGHT`, `DepthEnum` `FRONT/MIDDLE/BEHIND`, `RotationEnum` `FRONT/TOP/BACK/BELOW`, `PlaneOffset/DepthOffset/RotationOffset`; `Part.Position` "Defines the way the part is positioned in the model" | 2024, 2026 | PKG24 `T:…Position` and members, `P:…Part.Position` | nuget-metadata |
| K7 | UI depth: Middle "positioned in the middle of the reference line", Front "above the reference line", Behind underneath; "always relative to the part reference line between the part handles" | 2026 | https://help.trimble.com/topic/en/62066/74138/GUID-07B589BD-CFB6-4A1F-A759-37E290279A12 ("Part position depth") | doc |
| K8 | UI slab: pick corners; "the profile you select defines the thickness of the slab and the points you pick define the shape"; Position depth "always perpendicular to the work plane"; corners chamfered, round slab by Arc point; Level binds "the top face"; cast unit precast or cast in place; pour phase. No openings on the page | 2026 | https://help.trimble.com/doc/tekla-structures/2026/mod_creating_concrete_slab | doc |
| K9 | UI pad footing: "Pick a point"; Profile ("to create a circular pad footing, select a circular section"); Top/Bottom "in the global z direction"; level binding of the top face | 2026 | https://help.trimble.com/doc/tekla-structures/2026/mod_creating_pad_footing | doc |
| K10 | UI strip footing: "Pick the points you want the footing to go through"; "you cannot create a closed strip footing"; On plane, Rotation, At depth ("always perpendicular to the work plane") | 2026 | https://help.trimble.com/doc/tekla-structures/2026/mod_creating_strip_footing | doc |
| K11 | UI panel/wall: "passes through the points you pick"; "you cannot create a closed panel or wall structure"; Profile "thickness × height of the wall"; On plane, Rotation, At depth; Top/Bottom level binding; Wall layout tools | 2026 | https://help.trimble.com/doc/tekla-structures/2026/mod_creating_concrete_panel | doc |
| K12 | Open API exercise "Create pad footings" (updated 27 Mar 2024): `Beam`, Name `FOOTING`, Profile `"1500*1500"`, Material `"C50/60"`, Class `"8"`, EndPoint 500 mm below StartPoint, Position Rotation `FRONT`, Plane `MIDDLE`, Depth `MIDDLE`. The page shows **no** `BeamTypeEnum.PAD_FOOTING` constructor (the code is only in a download): the Position values are verified (doc); that pad footings are built as `Beam(PAD_FOOTING)` rests on K3 plus third-party code (secondary) | 2024 (page date) | https://developer.tekla.com/documentation/exercise-1-create-pad-footings | doc (Developer Center exercise) |
| K13 | `BooleanPart` "represents a part cut or an add … cut with a part instance to create a void to the father part. Typically the operative part is deleted after the boolean cut operation"; example: operative part `Class = BooleanPart.BooleanOperativeClassName`, `Insert`, `Father`, `SetOperativePart`, `Insert`, then the operative part's `Delete`; `BOOLEAN_CUT` default; `OperativePart` is "overwritten with a new part instance which is a copy … same identifier as the boolean part. Modifications (such as profile change) have to be made through the part instance"; `Modify`: "Currently it is not possible to modify the boolean part as there is nothing that can be modified for it. Calling this function will actually call modify for the operative part member"; `BooleanOperativeClassName` "must be used when inserting the operative part" | 2024, 2026 (member list unchanged) | PKG24 `T:…BooleanPart`, `M:…BooleanPart.Modify`, `P:…BooleanPart.OperativePart`, `F:…BooleanOperativeClassName` | nuget-metadata |
| K14 | `Boolean` is "an abstract base class for boolean operations such as a part cut, an add, a fitting or a cut plane", with `Father`; `BooleanPart : Boolean : ModelObject`, and `SetUserProperty`/`GetUserProperty` are "Inherited from ModelObject" | 2024 (XML); 2026 page (build string 2026.0.0-alpha) | PKG24 `T:…Boolean`, `P:…Boolean.Father`; https://developer.tekla.com/doc/tekla-structures/2026/boolean-part-class-71075 | nuget-metadata, doc |
| K15 | `Part.GetBooleans` "Returns an enumerator of all the connected boolean objects"; `Part.CastUnitType` with `CastUnitTypeEnum` `PRECAST, CAST_IN_PLACE`; `Part.PourPhase` | 2024, 2026 | PKG24/PKG26 `M:…Part.GetBooleans`, `P:…Part.CastUnitType`, `T:…Part.CastUnitTypeEnum` | nuget-metadata |
| K16 | `ChamferTypeEnum` also has `CHAMFER_LINE, CHAMFER_ROUNDING, CHAMFER_ARC, CHAMFER_SQUARE, CHAMFER_SQUARE_PARALLEL, CHAMFER_LINE_AND_ARC` (not used: spec chamfers stay `none`/`arc_point`, as ADR-0015) | 2024 | PKG24 `T:…Chamfer.ChamferTypeEnum` | nuget-metadata |
| K17 | `CatalogObjectTypeEnum` has `CONCRETE_BEAM, CONCRETE_COLUMN, CONCRETE_PAD_FOOTING, CONCRETE_STRIP_FOOTING, CONCRETE_PANEL, CONCRETE_SLAB, CONCRETE_LOFTED_SLAB`; no boolean or cut value | 2024, 2026 | CAT24, CAT26 `T:Tekla.Structures.Catalogs.CatalogObjectTypeEnum` | nuget-metadata |
| K18 | `MaterialItem.Type` with `MaterialItemTypeEnum` `MATERIAL_STEEL, MATERIAL_CONCRETE, MATERIAL_TIMBER, MATERIAL_MISC, MATERIAL_REBAR, …` | 2024 | CAT24 `T:…MaterialItem.MaterialItemTypeEnum` | nuget-metadata |
| K19 | `WorkPlaneHandler.SetCurrentTransformationPlane(TransformationPlane)` ("False on failure"); `TransformationPlane(Point, Vector, Vector)` "defined by the given origin and two vectors" | 2024, 2026 | PKG24 `M:…WorkPlaneHandler.SetCurrentTransformationPlane`, `M:…TransformationPlane.#ctor(…)` | nuget-metadata |
| K20 | Member diff of `ContourPlate, Beam, PolyBeam, Boolean, BooleanPart, Position, Part, Contour, ContourPoint, Chamfer, CutPlane, Fitting, WorkPlaneHandler, TransformationPlane, LoftedPlate` from 2024.0.4 to 2026.0.3: nothing removed; added only `Beam/PolyBeam.Start/EndLevelName/Offset` and `ContourPlate.LevelName/LevelOffset` ("Gets or sets the level name") | 2024 → 2026 | PKG24 vs PKG26 XML | nuget-metadata |
| K21 | `ModelObjectEnum` has `BEAM, POLYBEAM, CONTOURPLATE, BOOLEANPART, FITTING, CUTPLANE, LOFTED_PLATE` and already `STOREY, SPACE, BUILDING` in 2024.0.4; 2026.0.3 adds only `BUILDING_SITE` | 2024, 2026 | PKG24, PKG26 `F:…ModelObject.ModelObjectEnum.*` | nuget-metadata |

No source settles the following, so each is written as To verify and never asserted. C1–C16 above
include:
- which profile number runs along which axis;
- which Position puts each solid on its stated side;
- whether cut tags persist;
- whether an operative part needs to be inserted;
- whether deletes cascade;
- whether an opening can be modified in place.

No Trimble page found says how piles should be modelled (K5). `COLUMN` with Name `PILE` is the
engineer's choice (Q15).
