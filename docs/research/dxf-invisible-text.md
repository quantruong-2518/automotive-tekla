# Research note: when is DXF text not shown on a printed drawing?

Date: 2026-11-10. Purpose: facts with primary sources so the text extractor can stop reading hidden
text as visible (EVAL found 232 hidden ATTRIB entries in one drawing read as real levels and marks).
This note reports facts and one proposed rule; nothing in the repo was changed.

## Method and reliability

- **Versions.** Autodesk DXF Reference, cloudhelp editions 2016 and 2024 (the 2016 pages are the
  oldest the Autodesk site serves; the 2024 pages were re-read for group 60, ATTRIB group 70 and
  LAYER 62/70/290 and are identical). The drawings in question are AC1021 (AutoCAD 2007 and later);
  the Autodesk reference has no separate AC1021 page, so "applies to" below means "these editions
  of the reference, which cover AC1021". ezdxf **1.4.5** (`uv run python -c "import ezdxf"` in the
  repo `.venv`; file `.venv/lib/python3.12/site-packages/ezdxf/__init__.py`).
- **How read.** Autodesk and ezdxf web pages were read through a summarizing fetch tool. Quotes
  below were returned by that tool, not read by me raw: re-check before quoting in an ADR.
  ezdxf source lines were read directly. Paths below are relative to
  `.venv/lib/python3.12/site-packages/ezdxf/` (abbreviated `ezdxf/`).
- **Introspection** (`DXFATTRIBS`, `dir()`) was run on classes only. No drawing under
  `dwg-lab/samples/` was opened.
- **Could not run the ezdxf renderer.** `ezdxf.addons.drawing` imports `PIL`, which is not installed
  in the repo `.venv`. The renderer behaviour below is therefore taken from reading its source, not
  from running it. ezdxf's renderer is not Autodesk; where Autodesk is silent, ezdxf is evidence of
  one implementer's reading, not of AutoCAD behaviour.
- Status tags: `verified` (primary page or source line read), `derived` (my deduction from verified
  facts), `uncertain`.

---

## 1. Problems first

| # | Rank | Problem | Reason | Fix (proposal) |
|---|---|---|---|---|
| P1 | Major | Current `src/tekla_harness/extract_text.py` checks only ATTRIB `flags & 1` (lines 935, 1032) for the "invisible" signal. `grep` finds no use of group 60 (`dxf.invisible`), the layer plot flag (`dxf.plot`) or viewport-frozen layers in that file. Layer off/frozen flags are consumed in `levels.py:397` and `sheets.py:739`, where they are produced was not traced. | Group 60 can hide any text-bearing entity; layer plot = 0 and VP freeze hide text on the sheet. All are `verified` below. | Add the signals in section 8, each as its own flag, so the reader can tell the causes apart. |
| P2 | Major | Autodesk's DXF Reference is silent on whether an invisible INSERT hides its ATTRIBs and block contents. | Only the ezdxf renderer says it does (section 2). | Treat as `uncertain`; flag, do not drop (section 8). |
| P3 | Major | Which layouts are "the printed sheet" cannot be read from the DXF alone. | A layout with content is a possible sheet; model space is shown only through viewports (section 6). | Do not drop text because its layout is "unused". Emit a flag and ask. |
| P4 | Minor | The ezdxf renderer ignores `$ATTMODE` (ATTDISP). `grep ATTMODE ezdxf/addons/drawing/*.py` finds nothing. | AutoCAD lets `ATTDISP` override per-attribute invisibility (section 3). | The extractor should read `$ATTMODE` from the header and report it (section 3). |

---

## 2. Common entity group code 60 (visibility)

**Autodesk.** Common Group Codes for Entities, 2016 and 2024 editions:
<https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-DXF/files/GUID-3610039E-27D1-4E23-B6D3-7E60B22BB5BD.htm>
(2024: same GUID under `/cloudhelp/2024/`). Verbatim row (relayed): `60 | Object visibility (optional):
0 = Visible; 1 = Invisible | default 0`. The intro says: "The following table shows group codes that
apply to virtually all graphical objects", and the codes are also present in the per-entity lists
("keep in mind that the codes shown here are also present") (relayed, `verified`). Autodesk adds
that some of these codes are written "only if the entity has non-default values", so a missing 60
means visible.

**Which entities.** Autodesk gives no per-entity list: the common table applies to all graphical
entities, so TEXT, MTEXT, ATTRIB, ATTDEF, INSERT, MULTILEADER and DIMENSION all can carry 60.
The per-entity pages for ATTRIB and ATTDEF (group 70) and INSERT (group 66) have no group 60 row of
their own (relayed), which is consistent with 60 coming only from the common table.
ezdxf 1.4.5 confirms: `DXFGraphic.DXFATTRIBS` has `"invisible": DXFAttr(60, default=0,
dxfversion=DXF2000, optional=True)` (`ezdxf/entities/dxfgfx.py:111-112`). Introspection result:
`'invisible' in cls.DXFATTRIBS` is `True` for `Text`, `MText`, `Attrib`, `AttDef`, `Insert`,
`MultiLeader`, `MLeader`, `Dimension`, `Viewport`. It is **not** in `Layer.DXFATTRIBS`. The ezdxf
docs say "1 for invisible, 0 for visible; default value is 0; (requires DXF R2000)"
(<https://ezdxf.readthedocs.io/en/stable/dxfentities/dxfgfx.html>, relayed). Read it as
`entity.dxf.get("invisible", 0)`; ezdxf has no `is_invisible` property for group 60.

**Does an invisible INSERT hide its ATTRIBs and block contents?**
- Autodesk: **not documented** in the pages read (`not-found`).
- ezdxf renderer, `ezdxf/addons/drawing/properties.py:652-676`: for an `Insert`, visibility
  "depends only on the invisible flag, the layer state has no effect!" (comment at line 659).
  `draw_composite_entity` (`ezdxf/addons/drawing/frontend.py:881-917`) draws the block's virtual
  entities and then `insert.attribs` only when the INSERT itself was drawn, so an invisible INSERT
  hides its contents **and** its ATTRIBs (`verified` as ezdxf behaviour, from source; not run).
- Two details worth keeping: (a) the INSERT's *own layer* being off does not hide the INSERT in
  ezdxf (comment at line 659); the block's child entities and the ATTRIBs are each tested against
  their own layers. (b) Whether AutoCAD does the same is `uncertain`.

---

## 3. ATTRIB / ATTDEF flags (group 70)

**Autodesk.** ATTRIB (DXF): <https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-DXF/files/GUID-7DD8B495-C3F8-48CD-A766-14F9D7D0DD9B.htm>
(2024 edition re-read, same text). ATTDEF (DXF):
<https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-DXF/files/GUID-F0EA099B-6F88-4BCC-BEC7-247BA64838A4.htm>.
Verbatim (relayed, both pages):

```
Attribute flags:
1 = Attribute is invisible (does not appear)
2 = This is a constant attribute
4 = Verification is required on input of this attribute
8 = Attribute is preset (no prompt during insertion)
```

So **bit 1 (value 1)** is "invisible". ezdxf: `const.ATTRIB_INVISIBLE = 1`
(`ezdxf/lldxf/const.py:569`), `BaseAttrib.is_invisible` property = `bool(dxf.flags & ATTRIB_INVISIBLE)`
(`ezdxf/entities/attrib.py:262-264`), and the `flags` attribute is group 70 (`attrib.py:92-96`).
`is_invisible` exists on both `Attrib` and `AttDef` (introspection: `['is_invisible']`).

**Does it hide the attribute on plot?** Yes. Autodesk, Attribute Definition dialog (AutoCAD LT 2026
help, <https://help.autodesk.com/cloudhelp/2026/ENU/AutoCAD-LT/files/GUID-92A7CE9D-2E1C-415E-A1BF-5CB35D5E2D38.htm>):
Invisible mode "Specifies that attribute values are not displayed or printed when you insert the
block. The ATTDISP command overrides the Invisible mode." (relayed). The .NET developer guide
(<https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-NET/files/GUID-2107599E-9405-4D8B-A6DD-83D603B41568.htm>)
repeats the same sentence (relayed).

**ATTDISP override.** ATTDISP (Command) (<https://help.autodesk.com/cloudhelp/2018/ENU/AutoCAD-LT/files/GUID-BCFF32DB-6860-4812-BEF1-3BB658126B26.htm>):
Normal "Restores the defined visibility settings of each attribute. Visible attributes are displayed.
Invisible attributes are not displayed"; On "Makes all attributes visible, overriding the original
visibility settings"; Off "Makes all attributes invisible, overriding the original visibility
settings" (relayed). The DXF header variable `$ATTMODE` (group 70) stores it: "Attribute
visibility: 0 = None, 1 = Normal, 2 = All"
(<https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-DXF/files/GUID-A85E8E67-27CD-4C59-BE61-4DC9FADBE74A.htm>,
relayed). Consequence (`derived`): with `$ATTMODE` = 0 no attribute plots; with 2 all do, even flag-1
ones. `$ATTMODE` = 1 is the normal case.

**ATTDEF versus ATTRIB.** An ATTDEF is the template inside a block definition; each INSERT gets its
own ATTRIB (<.NET guide above>; INSERT group 66 "a series of attribute entities is expected to
follow the insert", ending with SEQEND, relayed from the INSERT (DXF) page
<https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-DXF/files/GUID-28FA4CFB-9D5E-4880-9F11-36C97578252F.htm>).
Autodesk does not say in the pages read that an ATTDEF inside a block is hidden when the block is
inserted (`not-found`). `derived` and consistent with the above: the visible text of an inserted
block is its ATTRIB entities and the block's TEXT/MTEXT; the ATTDEF only supplies defaults.
The instance flag on the ATTRIB (and its own group 60) is what counts; the ATTDEF flag only seeds it.

---

## 4. Layer state: off, frozen, plot flag, viewport freeze

**LAYER table (DXF).** <https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-DXF/files/GUID-D94802B0-8BE8-4AC9-8054-17197688AFDB.htm>
(2024 edition identical). Verbatim (relayed):
- Group 62: "Color number (if negative, layer is off)".
- Group 70 standard flags: "1 = Layer is frozen; otherwise layer is thawed", "2 = Layer is frozen
  by default in new viewports", "4 = Layer is locked", plus 16/32/64 for xref state.
- Group 290: "Plotting flag. If set to 0, do not plot this layer".

**Which keep text off a printed sheet.** AutoCAD, Layer Properties Manager
(<https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-LT/files/GUID-B297EBD9-D68C-47E1-87CE-1B3798496599.htm>,
relayed):
- Off: "When a layer is off, it is invisible and not plotted, even if the setting in the Plot column
  is turned on."
- Frozen: "Objects on frozen layers are not displayed, plotted, or regenerated."
- Plot: "If you turn off plotting for a layer, the objects on that layer are still displayed." and
  "Layers that are off or frozen are not plotted, regardless of the Plot setting."

| Signal | DXF | Shown on screen | Printed |
|---|---|---|---|
| layer off | LAYER group 62 < 0 | no | no |
| layer frozen | LAYER group 70 bit 1 | no | no |
| layer plot = 0 | LAYER group 290 = 0 | **yes** | **no** |
| layer frozen by default in new viewports | group 70 bit 2 (value 2) | only a default for *new* viewports; it says nothing about existing ones | not by itself (`verified` only as a default; see below) |
| layer locked | group 70 bit 4 | yes | yes |

Group 70 bit 2 is documented only as "Layer is frozen by default in new viewports". Do not treat it
as "frozen" (`verified` wording; consequence `derived`).

**Viewport-frozen layers (VP freeze).**
- AutoCAD: VP Freeze "Freezes selected layers only in the current layout viewport"; a layer already
  frozen or off in the drawing cannot be thawed per viewport (Layer Properties Manager page above,
  relayed).
- Storage: VIEWPORT (DXF) group 331 "Frozen layer object ID/handle (multiple entries may exist)
  (optional)" (<https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-DXF/files/GUID-2602B0FB-02E4-4B9A-B03C-B1D904753D34.htm>,
  relayed). The VPORT table page describes the same as "Soft or hard-pointer ID/handle to frozen
  layer objects; repeats for each frozen layers" (group 331 or 441,
  <https://help.autodesk.com/cloudhelp/2019/ENU/AutoCAD-DXF/files/GUID-8CE7CC87-27BD-4490-89DA-C21F516415A9.htm>,
  relayed). ezdxf reads group 331 (`ezdxf/entities/viewport.py:250` `FROZEN_LAYER_GROUP_CODE = 331`;
  loader at `viewport.py:345-349`) and resolves the handles to layer names after load
  (`viewport.py:post_load_hook`, around lines 333-343). In R12-style files the names are in XDATA
  (1003 inside a 1002 `{ }` list, `viewport.py:515-530`); not relevant to AC1021.
- Scope: this hides the layer **inside that viewport only**. Text on that layer in model space is
  invisible through that viewport but can be visible through another viewport that does not freeze
  it, and paper-space text on the layer is not affected by a viewport freeze (`derived`; Autodesk
  says "only in the current layout viewport").
- Per-viewport colour/linetype overrides are a different mechanism: stored in the LAYER entity and
  keyed by the viewport handle (ezdxf tutorial, <https://ezdxf.readthedocs.io/en/stable/tutorials/psp_viewports.html>,
  relayed). They change appearance, not visibility.

---

## 5. How ezdxf 1.4.5 exposes each

All introspected with `uv run python -c ...` (`ezdxf.__version__ == "1.4.5"`).

| Concept | ezdxf name | Source / docs |
|---|---|---|
| group 60 on any `DXFGraphic` | `entity.dxf.invisible` (int, default 0; `entity.dxf.get("invisible", 0)`) | `ezdxf/entities/dxfgfx.py:111-112` |
| ATTRIB/ATTDEF flags (group 70) | `entity.dxf.flags` (int, default 0) | `ezdxf/entities/attrib.py:92-96` |
| ATTRIB/ATTDEF invisible bit | `entity.is_invisible` (property, get/set); constant `ezdxf.lldxf.const.ATTRIB_INVISIBLE == 1` | `attrib.py:262-267`, `lldxf/const.py:569` |
| other bits | `is_const` (2), `is_verify` (4); preset (8) has `const.ATTRIB_IS_PRESET` only | `attrib.py`, `const.py:570-572` |
| layer off | `Layer.is_off()` = `dxf.color < 0`; `is_on()`; `Layer.get_color()` is `abs(color)` | `ezdxf/entities/layer.py:211-213` |
| layer frozen | `Layer.is_frozen()` = `dxf.flags & Layer.FROZEN` (bit 1) | `layer.py:183-185`, `FROZEN = 0b1` at `layer.py:129` |
| layer locked | `Layer.is_locked()` (bit 4) | `layer.py:195` |
| layer plot flag | `Layer.dxf.plot` (group 290, default 1, optional). No `is_plot()` method. Docs: "Whether entities belonging to this layer should be drawn when the document is exported (plotted) to pdf" | `layer.py:90-98`; <https://ezdxf.readthedocs.io/en/stable/tables/layer_table_entry.html> (relayed) |
| viewport-frozen layers | `Viewport.frozen_layers` (list of layer names), `Viewport.is_frozen(name)`; `Viewport.dxf.status` (68) and `dxf.id` (69) | `ezdxf/entities/viewport.py:274-296`, `:70,:79` |
| `LAYER` has no `invisible` | `'invisible' in Layer.DXFATTRIBS` is `False` | introspection |

Caveats from the ezdxf renderer (source only; not executed because `PIL` is missing):
`LayerProperties.is_visible = layer.is_on() and not layer.is_frozen()` and, **only in
`export_mode`**, `&= bool(layer.dxf.plot)` (`ezdxf/addons/drawing/properties.py:522-524`). So a
"printed" view needs `export_mode=True`; the plot flag is ignored for a "screen" view. Viewport
freeze is applied in `_setup_vp_layers` (`properties.py:446-462`). Entity visibility is
`not dxf.invisible` (plus `not entity.is_invisible` for `Attrib`, `properties.py:674`).

---

## 6. Anything else that hides text on plot

Items marked `derived` need the engineer's confirmation in AutoCAD before they become rules.

1. **Text in a block definition that is never inserted.** The DXF BLOCKS section holds definitions;
   Autodesk: "Three empty definitions always appear in the BLOCKS section. They are titled
   *Model_Space, *Paper_Space and *Paper_Space0"
   (<https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-DXF/files/GUID-66D32572-005A-4E23-8B8B-8726E8C14302.htm>,
   relayed). Block definition content is drawn only through an INSERT; the ezdxf renderer draws the
   layout entities and expands blocks only via `Insert` (`frontend.py:881-917`). `derived`: a
   definition no INSERT references is not on any sheet. In practice there are many unused
   definitions (title-block templates, purged-later symbols). The extractor must not emit them as
   sheet text.
2. **ATTDEF text inside a block definition.** The ATTDEF entity is a template, not sheet text (§3).
   The sheet shows the INSERT's ATTRIBs. `derived`.
3. **Layouts.** Per ezdxf internals: the entities of model space and the *active* paper space are
   in the ENTITIES section; "the content of the inactive paperspace layouts are stored in their
   BLOCK definition in the BLOCKS section"
   (<https://ezdxf.readthedocs.io/en/stable/dxfinternals/sections/blocks_section.html>, relayed).
   Group 67 distinguishes paper space (1) from model space (0/absent)
   (<https://help.autodesk.com/cloudhelp/2016/ENU/AutoCAD-DXF/files/GUID-3610039E-27D1-4E23-B6D3-7E60B22BB5BD.htm>,
   relayed). Whether an inactive layout is "unused" cannot be decided from the file: any layout can
   be plotted. `uncertain`; do not drop, flag.
4. **Model-space text with no viewport showing it.** Model space is printed through paper-space
   viewports (or the model tab itself). Text outside every viewport window, or in a viewport that is
   off (`VIEWPORT` group 68: "0 = Off", relayed) is not on that sheet. `derived`; would need
   viewport geometry. `uncertain`.
5. **Viewport status.** Group 68: "-1 = On, but is fully off screen, or is one of the viewports that
   is not active; 0 = Off; positive = On and active" (VIEWPORT page, relayed). An off viewport shows
   no model content.
6. **Appearance traps (not verified, listed so they are not forgotten):** text height 0 or a very
   small height, text colour equal to the sheet colour, entity transparency 100% (ezdxf docs call
   100% transparency "invisible", `ezdxf/entities/dxfgfx.py:253,266`), plot style table forcing no
   output, a clipped block (XCLIP), text on the `Defpoints` layer (AutoCAD never plots it; I did not
   find an Autodesk page in this session). None is a DXF flag; treat as `uncertain`.

---

## 7. What I could not verify

- Whether AutoCAD hides the ATTRIBs of an invisible INSERT (only ezdxf renderer source says so).
- Whether a layer being off hides an INSERT's *children on layer 0*, or only the INSERT's own layer
  (ezdxf: children inherit the INSERT's layer when their own layer is `"0"`,
  `properties.py` `resolve_layer`; AutoCAD behaviour not read).
- The Autodesk DXF Reference has no AC1021-specific page; 2016 and 2024 editions were used and agree.
- ezdxf doc URLs for `attrib.html`, `attdef.html` and `insert.html` returned 404 under the guessed
  paths; the source lines above are the evidence for those.
- `Defpoints` layer, transparency, zero-height text and plot-style effects (section 6.6).
- The ezdxf renderer could not be run (`PIL` missing from `.venv`), so its behaviour is read from source.

---

## 8. Rule for the extractor

1. Not printed (hard drop, or flag `not_printed` with the cause): `Layer.is_off()` (colour < 0),
   `Layer.is_frozen()` (flags bit 1), `Layer.dxf.plot == 0`, `Attrib.is_invisible` (group 70 bit 1),
   `entity.dxf.get("invisible", 0) == 1` (group 60) on TEXT/MTEXT/ATTRIB/MULTILEADER/DIMENSION.
2. ATTRIBs of an INSERT whose own group 60 is 1 are not printed (ezdxf renderer source only,
   Autodesk silent: mark `uncertain`, flag rather than drop); the INSERT's layer being off is
   *not* evidence for dropping its block contents.
3. Report `$ATTMODE` from the header: 0 means no attribute prints, 2 means all do even flag-1
   ones, 1 is normal; if it is not 1, lower confidence on every attribute decision.
4. Layer bit 2 ("frozen by default in new viewports") is NOT frozen; viewport-frozen layers
   (VIEWPORT group 331, `Viewport.frozen_layers`) hide text only inside that viewport, so flag
   `viewport_frozen` per viewport rather than dropping model-space text.
5. Uncertain, flag and ask: block definitions never inserted (drop from sheet text as definitions,
   but record), ATTDEF text, inactive layouts, text outside every viewport, `Defpoints`, zero
   height/colour/transparency traps.
