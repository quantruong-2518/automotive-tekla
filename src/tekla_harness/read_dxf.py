"""read_dxf: a deterministic probe of one DXF. Facts and open questions only, no inference.

`probe_dxf(path)` returns a dict that validates against `schemas/dxf-probe.schema.json`.
Units come from the header alone ($INSUNITS 0, missing or invalid is `unknown`, never metres) and
are never 'high' on their own: a plausibility check only ever raises questions.
Entity handles in the output are valid only for this conversion of the drawing, and are null when
the file stores none (R12-era files: ezdxf would synthesise numbers that mean nothing).
No section may crash the probe: a failing section becomes an entry in `section_errors`.
Text encodings are only hinted at here; converting them is a later slice.
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any

from ezdxf import units as dxf_units
from ezdxf.document import Drawing
from ezdxf.entities.dimension import Dimension
from ezdxf.entities.dxfentity import DXFEntity, DXFTagStorage
from ezdxf.entities.viewport import Viewport
from ezdxf.filemanagement import readfile
from ezdxf.layouts.blocklayout import BlockLayout
from ezdxf.tools.text import plain_mtext
from ezdxf.version import __version__ as EZDXF_VERSION

from tekla_harness.detect import sha256_file
from tekla_harness.encoding import font_hint, guess_encoding_from_font, scrub_surrogates
from tekla_harness.knowledge import FontEncodingRow, FontEncodingTable, default_font_encodings
from tekla_harness.readlog import timed_attempt

SCHEMA_VERSION = "0.1"
CONVERTER_CAPS = {"none": "high", "oda": "high", "libredwg": "medium"}  # ADR-0005
MAX_DIM_ROWS = 200
MAX_DIM_QUESTIONS = 500
MAX_NAMED_BLOCKS = 500
MAX_HANDLES = 5

BUILDING_UNITS = {"mm", "cm", "m", "in", "ft"}
_METRES_PER_UNIT = {"mm": 0.001, "cm": 0.01, "m": 1.0, "in": 0.0254, "ft": 0.3048}
_UNIT_SYSTEM = {"mm": "metric", "cm": "metric", "m": "metric", "in": "imperial", "ft": "imperial"}
_MEASUREMENT_SYSTEM = {0: "imperial", 1: "metric"}

# Heuristic, not a fact: the median modelspace linear dimension of a building drawing is expected between
# 5 cm and 100 m in the declared unit. Outside it the unit is doubted: a question, never a change.
MAGNITUDE_MIN_M = 0.01  # 0.05 flagged real mm connection details (median ~0.04 m) as suspect
MAGNITUDE_MAX_M = 100.0
MAGNITUDE_MIN_DIMS = 3

_NO_EXTENT = 1e19  # ezdxf / AutoCAD store +-1e20 when the drawing has no extents
_MAX_DECIMALS = 16
_SCALE_REL_TOL = 1e-4
_MEASURE_REL_TOL = 1e-6
_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
_CONTENT_OBJECTS = {
    "FIELD"
}  # raw-tag OBJECTS that can carry drawing content (computed text): worth a question
_NO_HANDLES_VERSION = "AC1015"  # R2000 and later: handles are mandatory

_ACIS_TYPES = {
    "3DSOLID", "BODY", "REGION", "SURFACE", "EXTRUDEDSURFACE", "LOFTEDSURFACE",
    "REVOLVEDSURFACE", "SWEPTSURFACE", "PLANESURFACE", "NURBSURFACE",
}  # fmt: skip
_OLE_TYPES = {"OLE2FRAME", "OLEFRAME"}
_DIM_TYPES = {
    0: "linear",
    1: "aligned",
    2: "angular",
    3: "diameter",
    4: "radius",
    5: "angular_3p",
    6: "ordinate",
}
_PLAIN_NUMBER = re.compile(r"^[+-]?(\d+(\.\d+)?|\.\d+)$")
_GROUP_5 = re.compile(rb"(?m)^[ \t]*5[ \t]*\r?\n[ \t]*[0-9A-Fa-f]+[ \t]*\r?$")
MAX_STYLES_LISTED = 10  # style names named in one knowledge question

TOLERANCE_RULE = (
    "Tolerance is half of the displayed precision: 0.5 * 10^-DIMDEC "
    "(DIMADEC for angular, DIMDEC when DIMADEC is -1), "
    "and at least DIMRND / 2 when DIMRND is set. Expected value is measured * DIMLFAC "
    "(angular: the measured angle in the DIMAUNIT unit: degrees, grads or radians)."
)

_FAILED: Any = object()  # a section that raised; the reason is in section_errors


def num(value: Any) -> float | None:
    """A finite float, or None. bool is not a number here; inf and nan never pass."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _int(value: Any) -> int | None:
    """An integral number as int, or None (bool, text, non-integral and non-finite are not integers)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, int):
        return value
    number = num(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _valid_insunits(raw: Any) -> int | None:
    """$INSUNITS if it is an integral code 0..20, else None (ezdxf wraps a negative code around its table)."""
    code = _int(raw)
    if code is None or not 0 <= code <= 20:
        return None
    return code


def _is_xref(block: BlockLayout) -> bool:
    return block.block is not None and block.block.is_xref


def _layer_of(entity: DXFEntity) -> str | None:
    if isinstance(entity, DXFTagStorage):  # raw tags: ezdxf has no DXF namespace for this type
        for tags in entity.xtags.subclasses:
            for tag in tags:
                if tag.code == 8:
                    return str(tag.value)
        return None
    return str(entity.dxf.get("layer", "0"))


# --- scan: one pass over every entity space ------------------------------------------


@dataclass
class _DimRef:
    dim: Dimension
    label: str  # layout name, or 'block:<name>' for a block definition
    is_model: bool
    in_block: bool


@dataclass
class _Scan:
    layout_counts: dict[str, Counter[str]] = field(default_factory=dict)
    layer_counts: dict[str, list[int]] = field(default_factory=lambda: defaultdict(lambda: [0, 0, 0]))
    layer_names: dict[str, str] = field(default_factory=dict)  # casefold -> first spelling seen
    inserts: Counter[str] = field(default_factory=Counter)
    inserts_with_attribs: set[str] = field(default_factory=set)
    blocks_with_attdef: set[str] = field(default_factory=set)
    dimensions: list[_DimRef] = field(default_factory=list)
    unreadable: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    objects: Counter[str] = field(default_factory=Counter)  # OBJECTS ezdxf keeps as raw tags, by type
    no_layer: int = 0


def _unreadable_kind(entity: DXFEntity) -> str | None:
    dxftype = entity.dxftype()
    if dxftype == "ACAD_PROXY_ENTITY":
        return "proxy"
    if dxftype == "ACAD_TABLE":
        return "acad_table"
    if dxftype in _OLE_TYPES:
        return "ole"
    if dxftype in _ACIS_TYPES:
        return "acis"
    if isinstance(entity, DXFTagStorage):
        return "unknown"  # ezdxf kept raw tags only: it cannot interpret this type
    return None


def _note_unreadable(scan: _Scan, kind: str, dxftype: str, layer: str | None, handle: str | None) -> None:
    row = scan.unreadable.setdefault(
        (kind, dxftype), {"kind": kind, "dxftype": dxftype, "count": 0, "by_layer": Counter(), "handles": []}
    )
    row["count"] += 1
    if layer is not None:
        row["by_layer"][layer] += 1
    if handle and len(row["handles"]) < MAX_HANDLES:
        row["handles"].append(handle)


def _scan_space(
    scan: _Scan, entities: Any, slot: int, layout: str | None, block: str | None, is_model: bool = False
) -> None:
    """slot: 0 modelspace, 1 paper-space layout, 2 block definition."""
    counts = scan.layout_counts.get(layout) if layout else None
    for entity in entities:
        dxftype = entity.dxftype()
        if counts is not None:
            counts[dxftype] += 1
        layer = _layer_of(entity)
        if layer is None:
            scan.no_layer += 1
        else:
            scan.layer_names.setdefault(layer.casefold(), layer)
            scan.layer_counts[layer.casefold()][slot] += 1
        if dxftype == "INSERT":
            key = str(entity.dxf.get("name", "")).casefold()
            scan.inserts[key] += 1
            if getattr(entity, "attribs", None):
                scan.inserts_with_attribs.add(key)
        elif dxftype == "ATTDEF" and block is not None:
            scan.blocks_with_attdef.add(block.casefold())
        elif dxftype == "DIMENSION" and isinstance(entity, Dimension):
            if layout is not None:
                scan.dimensions.append(_DimRef(entity, layout, is_model, False))
            elif block is not None:
                scan.dimensions.append(_DimRef(entity, f"block:{block}", False, True))
        kind = _unreadable_kind(entity)
        if kind:
            _note_unreadable(scan, kind, dxftype, layer, entity.dxf.get("handle"))


def _scan(doc: Drawing) -> _Scan:
    scan = _Scan()
    for name in doc.layout_names_in_taborder():
        scan.layout_counts[name] = Counter()
    for name in scan.layout_counts:
        layout = doc.layouts.get(name)
        _scan_space(scan, layout, 0 if layout.is_modelspace else 1, name, None, bool(layout.is_modelspace))
    for block in doc.blocks:
        if not block.is_any_layout and not _is_xref(block):
            _scan_space(scan, block, 2, None, block.name)
    for obj in doc.objects:
        dxftype = obj.dxftype()
        if dxftype == "ACAD_PROXY_OBJECT":
            _note_unreadable(scan, "proxy", dxftype, None, obj.dxf.get("handle"))
        elif isinstance(obj, DXFTagStorage):
            scan.objects[dxftype] += 1
            if dxftype in _CONTENT_OBJECTS:
                _note_unreadable(scan, "unknown", dxftype, None, obj.dxf.get("handle"))
    return scan


# --- handles -------------------------------------------------------------------------


def _has_group_5(path: Path) -> bool:
    data = path.read_bytes()
    if data.startswith(b"AutoCAD Binary DXF"):
        return True  # not scanned: the $HANDLING variable decides
    return _GROUP_5.search(data) is not None


def handles_reliable(doc: Drawing, path: Path) -> bool:
    """R2000+ always stores handles. Older files only when $HANDLING is on and group 5 tags exist.

    Otherwise ezdxf numbers the entities itself on load, and such numbers must not be reported.
    """
    if str(doc.dxfversion) >= _NO_HANDLES_VERSION:
        return True
    if not _int(doc.header.get("$HANDLING")):
        return False
    return _has_group_5(path)


def _handle(entity: DXFEntity, handles_ok: bool) -> str | None:
    handle = entity.dxf.get("handle")
    return str(handle) if handles_ok and handle else None


# --- sections -----------------------------------------------------------------------


def _units(
    doc: Drawing, cap: str, magnitudes: list[float] | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = doc.header.get("$INSUNITS")
    code = _valid_insunits(raw)
    if raw is None:
        evidence = ["header $INSUNITS is missing"]
    elif code is None:
        evidence = [f"header $INSUNITS = {raw!r} is not an integral code from 0 to 20: ignored"]
    else:
        evidence = [f"header $INSUNITS = {code}"]
    value = "unknown"
    if code is not None:
        try:
            name = dxf_units.decode(code)
        except IndexError:
            name = None
        evidence.append(f"ezdxf unit table: {name if name else 'no building unit for this code'}")
        if name in BUILDING_UNITS:
            value = name

    measurement_raw = doc.header.get("$MEASUREMENT")
    measurement = _int(measurement_raw)
    if measurement_raw is None:
        evidence.append("header $MEASUREMENT is missing")
    elif measurement in _MEASUREMENT_SYSTEM:
        evidence.append(f"header $MEASUREMENT = {measurement} ({_MEASUREMENT_SYSTEM[measurement]})")
    else:
        evidence.append(f"header $MEASUREMENT = {measurement_raw!r} is not 0 or 1: ignored")

    questions: list[dict[str, Any]] = []
    confidence = "low"
    if value == "unknown":
        questions.append(
            {
                "code": "units_unknown",
                "blocking": True,
                "message": "The DXF header does not give usable drawing units ($INSUNITS missing, 0, invalid "
                "or outside mm/cm/m/in/ft). In which unit are the coordinates drawn? Metres are not assumed.",
                "where": "header $INSUNITS",
                "found": "missing" if raw is None else str(raw),
            }
        )
    else:
        confidence = min(cap, "medium", key=_CONFIDENCE_ORDER.__getitem__)
        evidence.append("header units alone are never 'high': an independent check is needed to confirm them")
        questions.append(
            {
                "code": "units_confirm",
                "blocking": False,
                "message": f"The header declares {value}. Header units are not treated as confirmed; "
                "confirm the unit against a known dimension, a PDF or the engineer's knowledge.",
                "where": "header $INSUNITS",
                "found": f"{code} ({value})",
            }
        )
        degrade = False
        if measurement in _MEASUREMENT_SYSTEM and _MEASUREMENT_SYSTEM[measurement] != _UNIT_SYSTEM[value]:
            degrade = True
            questions.append(
                {
                    "code": "units_conflict",
                    "blocking": True,
                    "message": "The header unit and the header measurement system disagree. "
                    "Which unit are the coordinates drawn in?",
                    "where": "header $INSUNITS, $MEASUREMENT",
                    "found": f"$INSUNITS={code} ({value}, {_UNIT_SYSTEM[value]}) vs "
                    f"$MEASUREMENT={measurement} ({_MEASUREMENT_SYSTEM[measurement]})",
                }
            )
        suspect = _magnitude_check(value, magnitudes, evidence, questions)
        if degrade or suspect:
            confidence = "low"
    return {
        "value": value,
        "source": "header",
        "header_code": code,
        "confidence": confidence,
        "evidence": evidence,
        "dimension_median": dimension_median(magnitudes),
    }, questions


def dimension_median(magnitudes: list[float] | None) -> dict[str, Any] | None:
    """Median |length| of the modelspace linear and aligned dimensions in drawing units and how many there
    are; None when the audit is unavailable or fewer than MAGNITUDE_MIN_DIMS exist (the check is skipped)."""
    if magnitudes is None or len(magnitudes) < MAGNITUDE_MIN_DIMS:
        return None
    return {"value": float(statistics.median(magnitudes)), "count": len(magnitudes)}


def implausible_dimensions(median: dict[str, Any] | None, unit: str) -> str | None:
    """The units_suspect magnitude test for `unit` (not only the declared one): the evidence, in plain words,
    when the median modelspace linear dimension read in `unit` falls outside MAGNITUDE_MIN_M..MAGNITUDE_MAX_M;
    None when it is plausible, or when the median or the unit is unknown (nothing to test)."""
    factor = _METRES_PER_UNIT.get(unit)
    if median is None or factor is None:
        return None
    metres = median["value"] * factor
    if MAGNITUDE_MIN_M <= metres <= MAGNITUDE_MAX_M:
        return None
    return (
        f"median |linear dimension| {median['value']:g} drawing units = {metres:g} m in {unit} over "
        f"{median['count']} dimension(s); plausible range {MAGNITUDE_MIN_M:g} m to {MAGNITUDE_MAX_M:g} m"
    )


def _magnitude_check(
    value: str, magnitudes: list[float] | None, evidence: list[str], questions: list[dict[str, Any]]
) -> bool:
    """True when the median modelspace linear dimension is implausible for the declared unit."""
    if magnitudes is None:
        evidence.append("magnitude check skipped: the dimension audit is unavailable")
        return False
    if len(magnitudes) < MAGNITUDE_MIN_DIMS:
        evidence.append(
            f"magnitude check skipped: {len(magnitudes)} modelspace linear dimension(s), "
            f"{MAGNITUDE_MIN_DIMS} needed"
        )
        return False
    median = statistics.median(magnitudes)
    metres = median * _METRES_PER_UNIT[value]
    detail = (
        f"median |linear dimension| {median:g} {value} = {metres:g} m over {len(magnitudes)} dimension(s)"
    )
    evidence.append(f"{detail}; plausible range {MAGNITUDE_MIN_M:g} m to {MAGNITUDE_MAX_M:g} m")
    if MAGNITUDE_MIN_M <= metres <= MAGNITUDE_MAX_M:
        return False
    questions.append(
        {
            "code": "units_suspect",
            "blocking": True,
            "message": f"The declared unit {value} makes the typical linear dimension implausible for a "
            "building drawing. Is the unit declared in the header right?",
            "where": "header $INSUNITS, modelspace linear dimensions",
            "found": f"{detail}; thresholds {MAGNITUDE_MIN_M:g} m to {MAGNITUDE_MAX_M:g} m",
        }
    )
    return True


def _extents(doc: Drawing) -> dict[str, Any] | None:
    low, high = doc.header.get("$EXTMIN"), doc.header.get("$EXTMAX")
    if low is None or high is None:
        return None
    lo = [num(v) for v in tuple(low)[:3]]
    hi = [num(v) for v in tuple(high)[:3]]
    if len(lo) != 3 or len(hi) != 3 or None in lo or None in hi:
        return None
    lo_f, hi_f = [float(v) for v in lo if v is not None], [float(v) for v in hi if v is not None]
    if any(abs(v) >= _NO_EXTENT for v in lo_f + hi_f) or any(a > b for a, b in zip(lo_f, hi_f, strict=True)):
        return None
    return {"min": lo_f, "max": hi_f, "source": "header"}


def _viewport(vp: Viewport, is_overall: bool, handles_ok: bool) -> dict[str, Any]:
    view_height = num(vp.dxf.get("view_height"))
    scale: float | None = None
    note: str | None = None
    if view_height is None or view_height <= 0:
        note = f"view_height is {view_height}: scale cannot be computed"
    else:
        scale = num(vp.get_scale())
        if scale is None:
            note = "ezdxf returned no finite scale"
    target = [num(v) for v in tuple(vp.dxf.get("view_target_point", (0, 0, 0)))]
    return {
        "handle": _handle(vp, handles_ok),
        "id": _int(vp.dxf.get("id", 0)) or 0,
        "is_overall": is_overall,
        "scale": scale,
        "scale_note": note,
        "target": target if len(target) == 3 and None not in target else None,
        "view_height": view_height,
    }


def _layouts(doc: Drawing, scan: _Scan, handles_ok: bool) -> list[dict[str, Any]]:
    out = []
    for name, counts in scan.layout_counts.items():
        layout = doc.layouts.get(name)
        viewports = (
            []
            if layout.is_modelspace
            else [vp for vp in layout.query("VIEWPORT") if isinstance(vp, Viewport)]
        )
        # The first VIEWPORT of a paper-space layout is its overall viewport, whatever its id (converted DWGs
        # often store id 0). A first viewport with id >= 2 is a user viewport, so no overall one is assumed.
        first_is_overall = bool(viewports) and (_int(viewports[0].dxf.get("id", 0)) or 0) < 2
        out.append(
            {
                "name": name,
                "is_model": bool(layout.is_modelspace),
                "entity_total": sum(counts.values()),
                "entity_counts": dict(sorted(counts.items())),
                "viewports": [
                    _viewport(vp, first_is_overall and i == 0, handles_ok) for i, vp in enumerate(viewports)
                ],
            }
        )
    return out


def _layers(doc: Drawing, scan: _Scan) -> list[dict[str, Any]]:
    out, seen = [], set()
    for layer in doc.layers:
        name = str(layer.dxf.name)
        seen.add(name.casefold())
        out.append((name, True, layer.is_on(), layer.is_frozen(), layer.is_locked()))
    for key in sorted(scan.layer_counts.keys() - seen):
        out.append((scan.layer_names[key], False, None, None, None))
    rows = []
    for name, defined, on, frozen, locked in out:
        msp, lay, blk = scan.layer_counts.get(name.casefold(), [0, 0, 0])
        rows.append(
            {
                "name": name,
                "defined": defined,
                "on": on,
                "frozen": frozen,
                "locked": locked,
                "entities": {"modelspace": msp, "layouts": lay, "blocks": blk},
            }
        )
    return rows


def _dynamic_sources(doc: Drawing) -> dict[str, str]:
    """Anonymous dynamic-block copies ('*U..') -> source block name, from the block record's XDATA.

    Primary: AcDbBlockRepBTag, group 1005 = handle of the source BLOCK_RECORD.
    Fallback: AcDbDynamicBlockTrueName, group 1000 = the source block's name (what DWG-to-DXF converters
    write); it must name an existing block. Keys are casefolded.
    """
    sources: dict[str, str] = {}
    for block in doc.blocks:
        if not block.name.upper().startswith("*U"):
            continue
        record = block.block_record
        if record is None:
            continue
        if record.has_xdata("AcDbBlockRepBTag"):
            handles = [tag.value for tag in record.get_xdata("AcDbBlockRepBTag") if tag.code == 1005]
            target = doc.entitydb.get(str(handles[0])) if handles else None
            if target is not None and target.dxftype() == "BLOCK_RECORD":
                sources[block.name.casefold()] = str(target.dxf.name)
                continue
        if record.has_xdata("AcDbDynamicBlockTrueName"):
            names = [
                str(tag.value) for tag in record.get_xdata("AcDbDynamicBlockTrueName") if tag.code == 1000
            ]
            if names and names[0] in doc.blocks:
                sources[block.name.casefold()] = doc.blocks.get(names[0]).name
    return sources


def _blocks(doc: Drawing, scan: _Scan) -> dict[str, Any]:
    sources = _dynamic_sources(doc)
    inserts = Counter(scan.inserts)
    dynamic: Counter[str] = Counter()  # casefolded source name -> inserts reached through *U copies
    attribs = set(scan.inserts_with_attribs)
    anon_count = anon_inserts = attributed = unresolved = 0
    named_blocks = []
    for block in doc.blocks:
        if block.is_any_layout or _is_xref(block):
            continue
        key = block.name.casefold()
        if block.name.startswith("*"):
            anon_count += 1
            anon_inserts += scan.inserts[key]
            if key in sources:
                source_key = sources[key].casefold()
                dynamic[source_key] += scan.inserts[key]
                attributed += scan.inserts[key]
                if key in scan.inserts_with_attribs:
                    attribs.add(source_key)
            elif block.name.upper().startswith("*U"):
                unresolved += scan.inserts[key]
            continue
        named_blocks.append(block.name)
    named = [
        {
            "name": name,
            "insert_count": inserts[name.casefold()] + dynamic[name.casefold()],
            "dynamic_insert_count": dynamic[name.casefold()],
            "has_attdef": name.casefold() in scan.blocks_with_attdef,
            "has_attrib": name.casefold() in attribs,
        }
        for name in named_blocks
    ]
    named.sort(key=lambda b: (-b["insert_count"], b["name"]))
    return {
        "named": named[:MAX_NAMED_BLOCKS],
        "named_total": len(named),
        "truncated": len(named) > MAX_NAMED_BLOCKS,
        "anonymous": {
            "count": anon_count,
            "insert_count": anon_inserts,
            "attributed_dynamic": attributed,
            "unresolved_dynamic": unresolved,
        },
    }


def _xrefs(
    doc: Drawing, folder: Path, original_folder: bool = False
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows, questions = [], []
    place = "in the folder of the original drawing" if original_folder else "next to the DXF"
    for block in doc.blocks:
        if block.block is None or not block.block.is_xref:
            continue
        stored = str(block.block.dxf.get("xref_path", ""))
        base = PureWindowsPath(stored).name  # handles both '/' and '\' separators
        candidates = [base] if base else []
        stem, suffix = Path(base).stem, Path(base).suffix.lower()
        if suffix == ".dwg":
            candidates.append(f"{stem}.dxf")  # the converted sibling
        elif suffix == ".dxf":
            candidates.append(f"{stem}.dwg")
        resolved = any((folder / name).is_file() for name in candidates)
        rows.append({"name": block.name, "path": stored, "resolved": resolved, "checked": candidates})
        if not resolved:
            questions.append(
                {
                    "code": "xref_unresolved",
                    "blocking": True,
                    "message": f"External reference '{block.name}' was not found {place}. "
                    "Provide the referenced file or confirm that the drawing is complete without it.",
                    "where": f"xref {block.name}",
                    "found": stored,
                }
            )
    return rows, questions


_PROPOSED_MESSAGE = (
    "A text style matches a PROPOSED row of the font-encoding knowledge table "
    "(knowledge/font-encodings.csv). "
    "A proposed row changes nothing: the text of this style is still read as 'unknown'. Check the "
    "evidence, then approve or reject the row (edit its status in a reviewed commit)."
)
_CONFLICT_MESSAGE = (
    "A text style matches approved rows of the font-encoding knowledge table that disagree on the "
    "encoding. Nothing is decoded for this style. Fix or reject one of the rows."
)


def _style_names(names: list[str]) -> str:
    shown = ", ".join(names[:MAX_STYLES_LISTED])
    return shown + (f" (+{len(names) - MAX_STYLES_LISTED} more)" if len(names) > MAX_STYLES_LISTED else "")


def text_style_family(style: Any) -> str:
    """TrueType family of a text style from its ACAD XDATA; '' when there is none.

    ezdxf's `Textstyle.get_extended_font_data()` returns '' without ACAD XDATA, and also when the XDATA
    holds the family tag (1000) without the flags tag (1071) after it (ezdxf 1.4.5: it reads both or
    neither). ezdxf calls this data optional and not reliable: it is a naming hint like the others."""
    return str(style.get_extended_font_data()[0]) if style.has_xdata("ACAD") else ""


def _text_styles(
    doc: Drawing, table: FontEncodingTable
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Text styles, one hint row per legacy-looking style, and the questions about them.

    The rules are `encoding.font_hint(style name, font file, TrueType family)` (the same call
    `extract_text` makes); the knowledge table is consulted only when that returns "unknown", and only
    approved rows decide.
    """
    styles, hints, questions = [], [], []
    proposed: dict[int, tuple[FontEncodingRow, list[str]]] = {}
    for style in doc.styles:
        name = str(style.dxf.name)
        font = str(style.dxf.get("font", ""))
        bigfont = str(style.dxf.get("bigfont", ""))
        family = text_style_family(style)
        shx = any(f.lower().endswith(".shx") for f in (font, bigfont))
        hint = font_hint(name, font or None, family or None)
        capital = hint.capital_font
        encoding, source, pattern = hint.encoding, "font_hint", None
        matched = [
            {"field": field_name, "value": value}
            for field_name, value in (("name", name), ("font", font), ("family", family))
            if value and guess_encoding_from_font(value) == encoding
        ]  # empty when the encoding is "unknown"
        if encoding == "unknown":
            found = table.match(name, font or None)
            if found.conflict:
                questions.append(
                    {
                        "code": "font_encoding_conflict",
                        "blocking": False,
                        "message": _CONFLICT_MESSAGE,
                        "where": f"text style {name}",
                        "found": "; ".join(f"{r.cite()} [{r.source}]" for r in found.conflict),
                    }
                )
            if found.encoding is not None:
                encoding, source, pattern = found.encoding, "knowledge_table", found.patterns[0]
                capital = capital if capital is not None else found.capital_font
                matched = [
                    {"field": "name", "value": name}
                    if found.rows[0].applies_to == "style_name"
                    else {"field": "font", "value": font}
                ]
            for row_ in found.proposed:
                proposed.setdefault(row_.line, (row_, []))[1].append(name)
        styles.append(
            {
                "name": name,
                "font": font,
                "bigfont": bigfont,
                "family": family,
                "is_shx_like": shx,
                "capital_font": capital,
            }
        )
        if encoding in ("tcvn3", "vni"):
            hints.append(
                {
                    "style": name,
                    "encoding_hint": encoding,
                    "capital_font": capital,
                    "source": source,
                    "knowledge_pattern": pattern,
                    "matched": matched,
                    "kind": "hint",
                }
            )
            by = "the font name" if source == "font_hint" else f"approved knowledge row '{pattern}'"
            questions.append(
                {
                    "code": "text_encoding_hint",
                    "blocking": False,
                    "message": f"Text style '{name}' looks like a legacy Vietnamese font "
                    f"({encoding.upper()}) according to {by}. Text in this style may need converting; "
                    "this is a hint, not a finding.",
                    "where": f"text style {name}, {matched[0]['field']}",
                    "found": matched[0]["value"],
                }
            )
    for _line, (row_, names) in sorted(proposed.items()):
        questions.append(
            {
                "code": "font_encoding_proposed",
                "blocking": False,
                "message": _PROPOSED_MESSAGE,
                "where": f"knowledge row {row_.cite()}; text style(s) {_style_names(names)}",
                "found": f"{row_.evidence} [source: {row_.source}]",
            }
        )
    return styles, hints, questions


def _unreadable(scan: _Scan, handles_ok: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows, questions = [], []
    for (kind, dxftype), row in sorted(scan.unreadable.items()):
        by_layer = dict(sorted(row["by_layer"].items()))
        rows.append({**row, "by_layer": by_layer, "handles": row["handles"] if handles_ok else []})
        questions.append(
            {
                "code": "unreadable_objects",
                "blocking": False,
                "message": f"{row['count']} {dxftype} object(s) cannot be interpreted by the DXF reader and "
                "are not part of the extracted data. Provide a PDF or a simplified DXF if they matter.",
                "where": "layers " + ", ".join(by_layer) if by_layer else "OBJECTS section or no layer",
                "found": f"{row['count']} x {dxftype} ({kind})",
            }
        )
    return rows, questions


def _unparsed_objects(scan: _Scan) -> list[dict[str, Any]]:
    return [{"dxftype": t, "count": n} for t, n in sorted(scan.objects.items())]


# --- dimensions ---------------------------------------------------------------------


def _text_rule(text: str) -> str:
    if text in ("", "<>"):
        return "measured"
    if text == " ":
        return "suppressed"
    return "measured_with_text" if "<>" in text else "override"


def _dimtype(dim: Dimension) -> int | None:
    value = _int(dim.dimtype)
    return None if value is None else value & 7


def _dim_type_name(dimtype: int | None) -> str:
    return "unknown" if dimtype is None else _DIM_TYPES.get(dimtype, f"type_{dimtype}")


def _decimals(style: Any, angular: bool) -> tuple[int | None, str]:
    """Displayed decimals and the variable they came from; None when the value is unusable."""
    dec = _int(style.get("dimdec", 2))
    adec = _int(style.get("dimadec", -1)) if angular else None
    name, value = ("DIMADEC", adec) if angular and adec is not None and adec >= 0 else ("DIMDEC", dec)
    if value is None or not 0 <= value <= _MAX_DECIMALS:
        return None, name
    return value, name


def _angle_factor(aunit: int | None) -> tuple[float | None, str | None]:
    """(factor from degrees to the DIMAUNIT unit, reason when it cannot be compared)."""
    if aunit == 0:
        return 1.0, None
    if aunit == 2:
        return 400.0 / 360.0, None  # grads
    if aunit == 3:
        return math.pi / 180.0, None  # radians
    if aunit == 1:
        return None, "DIMAUNIT 1 is degrees/minutes/seconds, not a decimal number"
    if aunit == 4:
        return None, "DIMAUNIT 4 is surveyor's units, not a decimal number"
    return None, f"DIMAUNIT {aunit} is not a known angular unit"


def _not_compared(row: dict[str, Any], note: str) -> dict[str, Any]:
    row.update(status="not_compared", note=note)
    return row


def _audit_dimension(ref: _DimRef, seq: int, handles_ok: bool) -> dict[str, Any]:
    dim = ref.dim
    text = str(dim.dxf.get("text", ""))
    rule = _text_rule(text)
    dimtype = _dimtype(dim)
    angular = dimtype in (2, 5)
    row: dict[str, Any] = {
        "seq": seq,
        "handle": _handle(dim, handles_ok),
        "layout": ref.label,
        "dim_type": _dim_type_name(dimtype),
        "text_rule": rule,
        "text": text,
        "measured": None,
        "actual_measurement": None,
        "measurement_agrees": None,
        "expected_text_value": None,
        "override_value": None,
        "tolerance": None,
        "status": "ok",
        "note": None,
    }
    measurement = dim.get_measurement()
    measured = num(measurement) if isinstance(measurement, int | float) else None
    actual = num(dim.dxf.get("actual_measurement"))  # group 42, in radians for angular dimensions
    style = dim.override()
    lfac = None if angular else num(style.get("dimlfac", 1.0))
    agrees: bool | None = None
    raw_only = False  # group 42 is the unscaled geometry although a positive DIMLFAC other than 1 is in force
    if measured is not None and actual is not None:
        reference = math.radians(measured) if angular else measured
        abs_tol = 1e-5 if angular else _MEASURE_REL_TOL
        is_raw = math.isclose(actual, reference, rel_tol=_MEASURE_REL_TOL, abs_tol=abs_tol)
        scaled = lfac is not None and lfac > 0 and lfac != 1.0
        # Real files store group 42 either as the geometry or as geometry * DIMLFAC: both are consistent
        is_scaled = scaled and math.isclose(
            actual, reference * (lfac or 1.0), rel_tol=_MEASURE_REL_TOL, abs_tol=abs_tol
        )
        agrees = is_raw or is_scaled
        raw_only = bool(is_raw and scaled and not is_scaled)
    row.update(measured=measured, actual_measurement=actual, measurement_agrees=agrees)
    if rule != "override":
        return row

    stripped = "".join(plain_mtext(text)).strip()
    if not _PLAIN_NUMBER.match(stripped):
        row["status"] = "not_numeric"
        return row
    value = num(stripped)
    if value is None:
        row.update(status="not_numeric", note="the number is out of range")
        return row
    row["override_value"] = value
    if dimtype == 6 or measured is None:
        return _not_compared(row, "no scalar measurement to compare with")
    if agrees is False:
        return _not_compared(
            row,
            f"group 42 actual measurement {actual:g} disagrees with the geometry measurement "
            f"{measured:g}{' (degrees)' if angular else ''}; the reading is not trusted",
        )
    if raw_only:
        return _not_compared(
            row,
            f"group 42 ({actual:g}) is the unscaled geometry although DIMLFAC is {lfac:g}: "
            "unclear which value the text should show",
        )

    note: str | None = None
    if angular:
        unit_factor, reason = _angle_factor(_int(style.get("dimaunit", 0)))
        if unit_factor is None:
            return _not_compared(row, reason or "angular unit not comparable")
        factor = unit_factor
    else:
        lunit = _int(style.get("dimlunit", 2))
        if lunit != 2:
            return _not_compared(row, f"DIMLUNIT {style.get('dimlunit')} is not decimal")
        if lfac is None or lfac == 0:
            return _not_compared(row, f"DIMLFAC {style.get('dimlfac')} is not a usable factor")
        factor = lfac
        if lfac < 0:
            # A negative DIMLFAC is a paper-space-only factor. In modelspace the factor is 1, which only
            # group 42 can prove (it equals the geometry measurement); otherwise do not interpret it.
            if not (ref.is_model and actual is not None and agrees):
                return _not_compared(
                    row,
                    f"DIMLFAC {lfac:g} is negative (paper-space only); factor 1 in modelspace "
                    "cannot be proven without group 42",
                )
            factor = 1.0
            note = f"DIMLFAC {lfac:g} is negative: factor 1 used, proven by group 42 ({actual:g})"
    decimals, decimals_name = _decimals(style, angular)
    if decimals is None:
        return _not_compared(row, f"{decimals_name} is not an integer from 0 to {_MAX_DECIMALS}")
    tolerance = 0.5 * 10.0**-decimals
    rounding = num(style.get("dimrnd", 0.0)) or 0.0
    if rounding > 0:
        tolerance = max(tolerance, rounding / 2)
    expected = num(measured * factor)
    if expected is None:
        return _not_compared(row, "the expected value is out of range")
    row.update(expected_text_value=expected, tolerance=tolerance, note=note)
    if abs(value - expected) > tolerance + 1e-9:
        row["status"] = "override_differs"
    return row


def _measured_row(ref: _DimRef, seq: int, handles_ok: bool) -> dict[str, Any]:
    """The audit row of one dimension; a dimension that raises becomes an 'error' row, never dropped."""
    dim = ref.dim
    try:
        return _audit_dimension(ref, seq, handles_ok)
    except Exception as exc:  # reported on the row, never dropped
        text = str(dim.dxf.get("text", ""))
        try:
            dim_type = _dim_type_name(_dimtype(dim))
        except Exception:
            dim_type = "unknown"
        return {
            "seq": seq,
            "handle": _handle(dim, handles_ok),
            "layout": ref.label,
            "dim_type": dim_type,
            "text_rule": _text_rule(text),
            "text": text,
            "measured": None,
            "actual_measurement": None,
            "measurement_agrees": None,
            "expected_text_value": None,
            "override_value": None,
            "tolerance": None,
            "status": "error",
            "note": f"{type(exc).__name__}: {exc}",
        }


def measure_dimension(
    dim: Dimension,
    *,
    layout: str = "",
    is_model: bool = False,
    in_block: bool = False,
    handles_ok: bool = False,
) -> dict[str, Any]:
    """What one DIMENSION measures and prints, by the dimension_audit rules of the probe: its row without
    `seq` (handle, layout, dim_type, text_rule, text, measured, actual_measurement, measurement_agrees,
    expected_text_value, override_value, tolerance, status, note). Values in drawing units, never converted.

    `layout`: the name to report. `is_model`: the dimension is in modelspace, where a negative DIMLFAC means
    factor 1 when group 42 proves it (False: never assumed). `handles_ok`: the file's handles are reliable
    (False: handle null). The defaults are the conservative ones. A dimension that raises is an 'error'
    row."""
    row = _measured_row(_DimRef(dim, layout, is_model, in_block), 0, handles_ok)
    del row["seq"]
    return row


@dataclass
class _Audit:
    rows: list[dict[str, Any]]  # every dimension, in file order
    dimscales: list[float]
    warnings: list[str]
    magnitudes: list[float]  # modelspace linear/aligned dimension lengths, for the unit plausibility check


def _audit_all(scan: _Scan, handles_ok: bool) -> _Audit:
    rows: list[dict[str, Any]] = []
    dimscales: list[float] = []
    warnings: list[str] = []
    magnitudes: list[float] = []
    for seq, ref in enumerate(scan.dimensions, start=1):
        dim = ref.dim
        row = _measured_row(ref, seq, handles_ok)
        rows.append(row)
        if ref.is_model and row["dim_type"] in ("linear", "aligned"):
            length = row["actual_measurement"] if row["actual_measurement"] is not None else row["measured"]
            if length is not None:
                magnitudes.append(abs(length))
        if ref.in_block:
            continue  # block dimensions are audited, but their scale is not pooled with the drawing's
        try:
            scale = num(dim.override().get("dimscale", 1.0))
        except Exception as exc:  # reported, not dropped
            warnings.append(f"dimension {row['handle'] or '#' + str(seq)}: DIMSCALE unreadable ({exc})")
            continue
        if scale is None:
            warnings.append(f"dimension {row['handle'] or '#' + str(seq)}: DIMSCALE is not a finite number")
        else:
            dimscales.append(scale)
    return _Audit(rows, dimscales, warnings, magnitudes)


def _dimension_audit(audit: _Audit) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    rows, warnings = audit.rows, list(audit.warnings)
    by_status = Counter(r["status"] for r in rows)
    flagged = [r for r in rows if r["status"] in ("override_differs", "error")]
    rest = [r for r in rows if r["status"] not in ("override_differs", "error")]
    listed = (flagged + rest)[:MAX_DIM_ROWS]
    in_blocks = sum(1 for r in rows if r["layout"].startswith("block:"))
    if by_status["error"]:
        warnings.append(
            f"{by_status['error']} dimension(s) could not be audited; see rows with status 'error'."
        )
    disagree = sum(1 for r in rows if r["measurement_agrees"] is False)
    if disagree:
        warnings.append(
            f"{disagree} dimension(s): group 42 (actual measurement) disagrees with the geometry "
            "measurement; override text on those dimensions is not compared."
        )
    if in_blocks:
        warnings.append(
            f"{in_blocks} dimension(s) are inside block definitions: audited once per definition (layout "
            "'block:<name>'), not once per INSERT, and left out of the DIMSCALE count."
        )
    audit_section = {
        "total": len(rows),
        "in_blocks": in_blocks,
        "by_status": dict(sorted(by_status.items())),
        "by_text_rule": dict(sorted(Counter(r["text_rule"] for r in rows).items())),
        "tolerance_rule": TOLERANCE_RULE,
        "max_rows": MAX_DIM_ROWS,
        "truncated": len(rows) > MAX_DIM_ROWS,
        "rows": listed,
    }
    differing = [r for r in rows if r["status"] == "override_differs"]
    questions = [
        {
            "code": "dimension_override_differs",
            "blocking": False,
            "message": "Dimension text was typed over and differs from the measured value. "
            "Which one is right: the text or the geometry?",
            "where": f"{r['layout']}, DIMENSION " + (r["handle"] or f"#{r['seq']} (no handle)"),
            "found": r["text"],
        }
        for r in differing[:MAX_DIM_QUESTIONS]
    ]
    if len(differing) > MAX_DIM_QUESTIONS:
        warnings.append(
            f"{len(differing)} dimensions have typed-over text that differs from the geometry; "
            f"only the first {MAX_DIM_QUESTIONS} are raised as questions."
        )
    if audit_section["truncated"]:
        warnings.append(
            f"Dimension rows truncated to {MAX_DIM_ROWS} of {len(rows)}; flagged rows are listed first."
        )
    return audit_section, questions, warnings


def _group_scales(values: Iterable[float]) -> list[dict[str, Any]]:
    """Group scale values equal within a relative tolerance of 1e-4; a value and its reciprocal
    (1:N and N) count as the same scale. Each group lists its distinct raw values as `members`."""
    counts = Counter(values)
    groups: list[dict[str, Any]] = []
    for value in sorted(counts):
        for group in groups:
            rep = group["value"]
            same = math.isclose(value, rep, rel_tol=_SCALE_REL_TOL)
            if not same and rep != 0 and value != 0:
                same = math.isclose(value, 1.0 / rep, rel_tol=_SCALE_REL_TOL)
            if same:
                group["count"] += counts[value]
                group["members"].append(value)
                break
        else:
            groups.append({"value": value, "count": counts[value], "members": [value]})
    return groups


def _scales(
    doc: Drawing, layouts: list[dict[str, Any]], dimscales: list[float]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    viewport_values = [
        vp["scale"]
        for layout in layouts
        for vp in layout["viewports"]
        if not vp["is_overall"] and vp["scale"] is not None
    ]
    dim_groups, vp_groups = _group_scales(dimscales), _group_scales(viewport_values)
    dimstyles = [
        {"name": str(s.dxf.name), "dimscale": num(s.dxf.get("dimscale", 1.0))} for s in doc.dimstyles
    ]
    multi_dim, multi_vp = len(dim_groups) > 1, len(vp_groups) > 1
    questions = []
    for flag, label, groups in (
        (multi_dim, "DIMSCALE of dimensions", dim_groups),
        (multi_vp, "viewport scales", vp_groups),
    ):
        if flag:
            questions.append(
                {
                    "code": "multiple_scales",
                    "blocking": False,
                    "message": f"More than one distinct {label} is used. Which scale applies to which "
                    "part of the drawing?",
                    "where": label,
                    "found": ", ".join(f"{g['value']:.6g}" for g in groups),
                }
            )
    scales = {
        "dimscale": dim_groups,
        "dimstyles": dimstyles,
        "viewport_scales": vp_groups,
        "multiple_dimscale": multi_dim,
        "multiple_viewport_scales": multi_vp,
        "multiple_scales": multi_dim or multi_vp,
    }
    return scales, questions


# --- entry point --------------------------------------------------------------------


def _run(errors: list[dict[str, str]], section: str, fn: Callable[..., Any], *args: Any) -> Any:
    """Run one section. A failure becomes a section_errors entry and _FAILED, never an exception."""
    try:
        return fn(*args)
    except Exception as exc:
        errors.append({"section": section, "error": f"{type(exc).__name__}: {exc}"})
        return _FAILED


def _skip(errors: list[dict[str, str]], section: str, because: str) -> None:
    errors.append({"section": section, "error": f"not computed: {because} failed"})


def probe_dxf(
    path: str | Path,
    converter: str = "none",
    xref_dir: str | Path | None = None,
    knowledge: FontEncodingTable | None = None,
) -> dict[str, Any]:
    """Read one DXF and report. Raises OSError if the file cannot be hashed; ValueError for a bad converter;
    KnowledgeError if the knowledge table is malformed (never swallowed into `section_errors`).

    `xref_dir`: folder where external references are looked for, instead of the DXF's own folder. Pass the
    folder of the original drawing when the DXF is a conversion in a work folder.
    `knowledge`: font-encoding table; default is the shipped `knowledge/font-encodings.csv`.

    A DXF that ezdxf cannot open is reported as `status: "unreadable"` with the error, not raised.
    A section that fails is reported in `section_errors` with `status: "partial"`; the others are kept.
    """
    result = _probe_dxf(path, converter, xref_dir, knowledge)
    clean, scrubbed = scrub_surrogates(result)
    if scrubbed and "warnings" in clean:
        clean["warnings"].append(
            f"{scrubbed} character(s) in names or text were bytes that are not valid UTF-8 (a damaged or "
            "mis-converted file): replaced by U+FFFD."
        )
    return clean


def _probe_dxf(
    path: str | Path,
    converter: str = "none",
    xref_dir: str | Path | None = None,
    knowledge: FontEncodingTable | None = None,
) -> dict[str, Any]:
    """The probe itself; `probe_dxf` adds the UTF-8 scrub."""
    if converter not in CONVERTER_CAPS:
        raise ValueError(f"unknown converter '{converter}'; choose from {', '.join(CONVERTER_CAPS)}")
    path = Path(path)
    cap = CONVERTER_CAPS[converter]
    table = knowledge if knowledge is not None else default_font_encodings()
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "file": {
            "path": str(path),
            "sha256": sha256_file(path),
            "ezdxf_version": EZDXF_VERSION,
            "dxf_version": None,
            "converter": converter,
            "confidence_cap": cap,
            "handles_reliable": False,
        },
    }
    doc: Drawing | None = None
    with timed_attempt("ezdxf", EZDXF_VERSION) as attempt:
        try:
            doc = readfile(str(path))
        except Exception as exc:  # recorded as a failed attempt and returned as JSON
            attempt.fail(f"{type(exc).__name__}: {exc}")
    result["attempts"] = [attempt.as_dict()]
    if doc is None:
        result.update(status="unreadable", error=attempt.error)
        return result

    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    version = doc.header.get("$ACADVER")
    result["file"]["dxf_version"] = str(version) if version else None
    handles = _run(errors, "handles", handles_reliable, doc, path)
    handles_ok = handles is not _FAILED and bool(handles)
    result["file"]["handles_reliable"] = handles_ok
    if not handles_ok:
        warnings.append(
            "This DXF stores no usable entity handles (R12-era): handle fields are null; "
            "rows are identified by their position in the file."
        )

    scan = _run(errors, "scan", _scan, doc)
    audit: Any = _FAILED
    if scan is _FAILED:
        for section in (
            "layouts", "layers", "blocks", "unreadable_objects", "unparsed_objects",
            "entities_without_layer", "dimension_audit", "scales",
        ):  # fmt: skip
            _skip(errors, section, "scan")
    else:
        audit = _run(errors, "dimension_audit", _audit_all, scan, handles_ok)

    questions: list[dict[str, Any]] = []
    magnitudes = None if audit is _FAILED else audit.magnitudes
    units = _run(errors, "units", _units, doc, cap, magnitudes)
    if units is not _FAILED:
        result["units"], unit_questions = units
        questions += unit_questions
    extents = _run(errors, "extents", _extents, doc)
    if extents is not _FAILED:
        result["extents"] = extents

    layouts: Any = _FAILED
    if scan is not _FAILED:
        layouts = _run(errors, "layouts", _layouts, doc, scan, handles_ok)
        if layouts is not _FAILED:
            result["layouts"] = layouts
        layers = _run(errors, "layers", _layers, doc, scan)
        if layers is not _FAILED:
            result["layers"] = layers
        blocks = _run(errors, "blocks", _blocks, doc, scan)
        if blocks is not _FAILED:
            result["blocks"] = blocks
            if blocks["truncated"]:
                warnings.append(
                    f"blocks.named truncated to {MAX_NAMED_BLOCKS} of {blocks['named_total']} named blocks."
                )
            if blocks["anonymous"]["unresolved_dynamic"]:
                warnings.append(
                    f"{blocks['anonymous']['unresolved_dynamic']} insert(s) of anonymous dynamic blocks (*U) "
                    "could not be attributed to a source block; their counts are kept under anonymous."
                )
        unreadable = _run(errors, "unreadable_objects", _unreadable, scan, handles_ok)
        unreadable_questions: list[dict[str, Any]] = []
        if unreadable is not _FAILED:
            result["unreadable_objects"], unreadable_questions = unreadable
        result["unparsed_objects"] = _unparsed_objects(scan)
        result["entities_without_layer"] = scan.no_layer
        if scan.no_layer:
            warnings.append(
                f"{scan.no_layer} entity/entities without a layer (group 8): not counted on any layer."
            )
    else:
        unreadable_questions = []

    xref_folder = Path(xref_dir).resolve() if xref_dir is not None else path.resolve().parent
    xrefs = _run(errors, "xrefs", _xrefs, doc, xref_folder, xref_dir is not None)
    xref_questions: list[dict[str, Any]] = []
    if xrefs is not _FAILED:
        result["xrefs"], xref_questions = xrefs

    styles = _run(errors, "text_styles", _text_styles, doc, table)
    hint_questions: list[dict[str, Any]] = []
    if styles is not _FAILED:
        result["text_styles"], result["text_encoding_hints"], hint_questions = styles

    dim_questions: list[dict[str, Any]] = []
    scale_questions: list[dict[str, Any]] = []
    if audit is not _FAILED:
        section = _run(errors, "dimension_audit", _dimension_audit, audit)
        if section is not _FAILED:
            result["dimension_audit"], dim_questions, dim_warnings = section
            warnings += dim_warnings
        if layouts is not _FAILED:
            scales = _run(errors, "scales", _scales, doc, layouts, audit.dimscales)
            if scales is not _FAILED:
                result["scales"], scale_questions = scales
        elif scan is not _FAILED:
            _skip(errors, "scales", "layouts")
    elif scan is not _FAILED:
        _skip(errors, "scales", "dimension_audit")

    if converter == "libredwg":
        warnings.append("DXF produced by the fallback converter (libredwg): confidence capped at medium.")
    failed = [
        {
            "code": "probe_section_failed",
            "blocking": True,
            "message": f"The probe could not compute the '{e['section']}' section; nothing may rely on it. "
            "Report this as a probe bug and read the drawing another way.",
            "where": f"probe section {e['section']}",
            "found": e["error"],
        }
        for e in errors
    ]
    result.update(
        questions=questions
        + xref_questions
        + unreadable_questions
        + dim_questions
        + scale_questions
        + hint_questions
        + failed,
        warnings=warnings,
    )
    if errors:
        result.update(status="partial", section_errors=errors)
    return result
