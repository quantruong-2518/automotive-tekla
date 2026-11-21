"""render: `harness render`, one region of a drawing as a PNG with a known pixel <-> drawing transform.

The world is `_dxf_fixtures.build_set` (two framed model sheets) plus, invented here, circles at known places
far left of and below both sheets: one per layer, a block with a layer 0 circle placed mirrored (xscale -1 and
an extrusion of (0, 0, -1)) and one circle far outside every region asked for. PNGs are decoded with zlib
and struct only (no image library in the tests either)."""

from __future__ import annotations

import json
import math
import shutil
import struct
import zlib
from pathlib import Path
from typing import Any

import pytest
from ezdxf.filemanagement import new as new_doc
from ezdxf.filemanagement import readfile
from ezdxf.math import Vec3

from _callout_fixtures import PROPOSED_FONT_TABLE, REL, write_structure
from _dxf_fixtures import build_set
from tekla_harness import render as render_mod
from tekla_harness.cli import main
from tekla_harness.intake import run_intake
from tekla_harness.render import render
from tekla_harness.schemas import validate
from tekla_harness.sheet_text import ReaderError

LAYER_A, LAYER_B = "R-A", "R-B"
CIRCLE_A = (-30000.0, -30000.0)  # on layer R-A
CIRCLE_B = (-30000.0, -27000.0)  # on layer R-B
MIRRORED = (-26000.0, -30000.0)  # block circle (1000, 0) of an INSERT at (-25000, -30000), xscale -1
EXTRUDED = (-22000.0, -30000.0)  # the same block with extrusion (0, 0, -1) at OCS x 21000
FAR = (900000.0, 900000.0)
RADIUS = 500.0
REGION = (-35000.0, -35000.0, -15000.0, -25000.0)  # 20000 x 10000, holds every circle but FAR


def build_render_dxf(base: Path) -> Path:
    root = base / "input"
    (root / "plans").mkdir(parents=True)
    doc = readfile(str(build_set(base, "src.dxf")))
    doc.layers.add(LAYER_A)
    doc.layers.add(LAYER_B)
    msp = doc.modelspace()
    msp.add_circle(CIRCLE_A, RADIUS, dxfattribs={"layer": LAYER_A})
    msp.add_circle(CIRCLE_B, RADIUS, dxfattribs={"layer": LAYER_B})
    blk = doc.blocks.new("MIRROR_ME")
    blk.add_circle((1000.0, 0.0), 300.0, dxfattribs={"layer": "0"})
    msp.add_blockref("MIRROR_ME", (-25000.0, -30000.0), dxfattribs={"layer": LAYER_A, "xscale": -1.0})
    # an extrusion of (0, 0, -1) mirrors x: the insert point is stored in OCS, the WCS x is its negative
    msp.add_blockref("MIRROR_ME", (21000.0, -30000.0), dxfattribs={"layer": LAYER_A, "extrusion": (0, 0, -1)})
    msp.add_circle(FAR, RADIUS, dxfattribs={"layer": LAYER_A})
    doc.saveas(root / REL)
    return root


@pytest.fixture(scope="module")
def base(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("render")
    inp = build_render_dxf(root)
    work = root / "work"
    run_intake(inp, work, "demo-render", knowledge=PROPOSED_FONT_TABLE)
    write_structure(inp, work)
    return root


def run(base: Path, capsys, *args: str) -> tuple[int, dict[str, Any], str]:
    capsys.readouterr()
    code = main(["render", str(base / "work"), REL, "--input-dir", str(base / "input"), *args])
    out, err = capsys.readouterr()
    return code, (json.loads(out) if out.strip() else {}), err


def bbox_args(region=REGION) -> list[str]:
    return ["--bbox", *(str(v) for v in region)]


def decode_png(path: Path) -> tuple[int, int, list[bytes], int]:
    """(width, height, unfiltered rows, bytes per pixel) of an 8-bit non-interlaced RGB or RGBA PNG."""
    return decode_png_bytes(path.read_bytes())


def decode_png_bytes(data: bytes) -> tuple[int, int, list[bytes], int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w = 8, b"", 0
    h = bpp = 0
    while pos < len(data):
        (n,) = struct.unpack(">I", data[pos : pos + 4])
        kind, body = data[pos + 4 : pos + 8], data[pos + 8 : pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            assert (depth, interlace) == (8, 0) and ctype in (2, 6)
            bpp = 3 if ctype == 2 else 4
        elif kind == b"IDAT":
            idat += body
    raw = zlib.decompress(idat)
    stride, rows, prev = w * bpp, [], bytes(w * bpp)
    for y in range(h):
        ft, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], (prev[i - bpp] if i >= bpp else 0)
            if ft == 1:
                line[i] = (line[i] + a) & 255
            elif ft == 2:
                line[i] = (line[i] + b) & 255
            elif ft == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 255
        rows.append(bytes(line))
        prev = bytes(line)
    return w, h, rows, bpp


def ink_at(rows: list[bytes], bpp: int, t: dict[str, Any], x: float, y: float, reach: int = 2) -> bool:
    """True when a pixel within `reach` px of the drawing point (x, y) is lit, by the transform `t`."""
    px = t["left_margin_px"] + (x - t["x0"]) / t["units_per_px"]
    py = t["top_margin_px"] + (t["y1"] - y) / t["units_per_px"]
    cx, cy = round(px), round(py)
    for yy in range(cy - reach, cy + reach + 1):
        for xx in range(cx - reach, cx + reach + 1):
            inside = 0 <= yy < len(rows) and 0 <= xx * bpp < len(rows[yy])
            if inside and max(rows[yy][xx * bpp : xx * bpp + 3]) > 60:
                return True
    return False


def ink_near(image: dict[str, Any], x: float, y: float, reach: int = 2) -> bool:
    """True when a pixel within `reach` px of the drawing point (x, y) is lit, by the document's transform."""
    _, _, rows, bpp = decode_png(Path(image["path"]))
    return ink_at(rows, bpp, image["transform"], x, y, reach)


def right_point(centre: tuple[float, float], r: float = RADIUS) -> tuple[float, float]:
    return centre[0] + r, centre[1]


def test_image_fits_the_budget_and_the_document_is_valid(base, capsys):
    code, doc, err = run(base, capsys, *bbox_args())
    assert code == 0 and validate("render", doc) == []
    assert doc["project_id"] == "demo-render" and doc["file"] == REL
    assert doc["units"] == {"declared": "mm", "answered": None, "converted": False}
    (img,) = doc["images"]
    w, h, _, _ = decode_png(Path(img["path"]))
    assert (w, h) == (img["width_px"], img["height_px"])
    assert max(w, h) <= 1568 and w * h <= 1_150_000
    assert img["est_image_tokens"] == math.ceil(w * h / 750)
    assert Path(img["path"]).is_absolute() and Path(img["path"]).parent == base / "work" / "renders"
    assert "elapsed" in err


@pytest.mark.parametrize(
    "extra", [["--max-px", "400"], ["--no-overlay"], ["--max-px", "900", "--no-overlay"]]
)
def test_max_px_and_overlay_stay_in_the_budget(base, capsys, extra):
    code, doc, _ = run(base, capsys, *bbox_args(), *extra)
    assert code == 0
    (img,) = doc["images"]
    limit = int(extra[1]) if "--max-px" in extra else 1568
    assert max(img["width_px"], img["height_px"]) <= limit
    assert img["width_px"] * img["height_px"] <= 1_150_000
    if "--no-overlay" in extra:
        t = img["transform"]
        assert t["left_margin_px"] == t["top_margin_px"] == 0


def test_a_tall_region_stays_inside_the_long_edge_budget(base, capsys):
    code, doc, _ = run(base, capsys, "--bbox", "-35000", "-40000", "-30000", "-25000", "--no-overlay")
    (img,) = doc["images"]
    assert code == 0 and img["height_px"] == 1568 and img["width_px"] * img["height_px"] <= 1_150_000


def test_a_square_region_is_held_by_the_area_budget(base, capsys):
    # 1568 x 1568 would be 2.5 MP: the area cap, not the long edge, sets the size
    code, doc, _ = run(base, capsys, "--bbox", "-35000", "-35000", "-25000", "-25000", "--no-overlay")
    (img,) = doc["images"]
    assert code == 0 and 1_000_000 < img["width_px"] * img["height_px"] <= 1_150_000
    assert max(img["width_px"], img["height_px"]) < 1568


def test_transform_puts_a_known_circle_on_its_pixel(base, capsys):
    code, doc, _ = run(base, capsys, *bbox_args())
    (img,) = doc["images"]
    assert code == 0 and img["region"] == list(REGION)
    assert ink_near(img, *right_point(CIRCLE_A))
    assert ink_near(img, CIRCLE_A[0], CIRCLE_A[1] + RADIUS)
    assert not ink_near(img, *CIRCLE_A, reach=3)  # the centre is empty
    assert not ink_near(img, CIRCLE_A[0] + 7000, CIRCLE_A[1] + 3000)  # nothing is drawn there


def test_a_mirrored_insert_lands_at_its_wcs_position(base, capsys):
    _, doc, _ = run(base, capsys, *bbox_args())
    (img,) = doc["images"]
    assert ink_near(img, MIRRORED[0] + 300, MIRRORED[1])  # xscale -1: block (1000, 0) -> WCS -26000
    assert not ink_near(img, -24000.0 - 300, MIRRORED[1])  # not at the unmirrored place (-24000)
    assert ink_near(img, EXTRUDED[0] - 300, EXTRUDED[1])  # extrusion (0, 0, -1)


def test_layer_filter_keeps_only_the_effective_layer(base, capsys):
    _, everything, _ = run(base, capsys, *bbox_args())
    _, only_b, _ = run(base, capsys, *bbox_args(), "--layer", LAYER_B.lower())
    _, only_a, _ = run(base, capsys, *bbox_args(), "--layer", LAYER_A)
    (b,), (a,), (every,) = only_b["images"], only_a["images"], everything["images"]
    assert only_b["query"]["layers"] == [LAYER_B.lower()]
    assert b["entities_drawn"] == 1 < a["entities_drawn"] < every["entities_drawn"]
    assert ink_near(b, *right_point(CIRCLE_B)) and not ink_near(b, *right_point(CIRCLE_A))
    # layer 0 inside the block follows the INSERT (layer R-A): drawn for R-A, not for R-B
    assert ink_near(a, MIRRORED[0] + 300, MIRRORED[1]) and not ink_near(b, MIRRORED[0] + 300, MIRRORED[1])
    assert ink_near(a, *right_point(CIRCLE_A)) and not ink_near(a, *right_point(CIRCLE_B))


def test_entities_outside_the_region_are_pruned_not_drawn(base, capsys):
    _, small, _ = run(base, capsys, *bbox_args())
    _, wide, _ = run(base, capsys, "--bbox", "-35000", "-35000", "1000000", "1000000", "--no-overlay")
    (s,), (w,) = small["images"], wide["images"]
    assert s["entities_pruned"] >= 1 and s["entities_drawn"] == 4  # two circles, two block circles
    assert w["entities_drawn"] > s["entities_drawn"]
    assert w["entities_pruned"] < s["entities_pruned"]


def test_tiles_split_the_region_into_abutting_images(base, capsys):
    code, doc, _ = run(base, capsys, *bbox_args(), "--tiles", "2x1")
    assert code == 0 and validate("render", doc) == []
    left, right = doc["images"]
    assert left["region"][2] == right["region"][0] == (REGION[0] + REGION[2]) / 2
    assert left["region"][1] == right["region"][1] == REGION[1]
    assert left["region"][3] == right["region"][3] == REGION[3]
    assert left["path"] != right["path"] and doc["query"]["tiles"] == [2, 1]
    # CIRCLE_A (x -30000) is in the left tile, EXTRUDED (x -22000) in the right one
    assert ink_near(left, *right_point(CIRCLE_A)) and ink_near(right, EXTRUDED[0] - 300, EXTRUDED[1])
    assert not ink_near(right, *right_point(CIRCLE_A))
    for img in (left, right):
        assert max(img["width_px"], img["height_px"]) <= 1568


def test_file_names_are_stable_and_follow_the_options(base, capsys):
    _, first, _ = run(base, capsys, *bbox_args())
    before = Path(first["images"][0]["path"]).read_bytes()
    _, again, _ = run(base, capsys, *bbox_args())
    assert again["images"][0]["path"] == first["images"][0]["path"]
    assert Path(again["images"][0]["path"]).read_bytes() == before
    name = Path(first["images"][0]["path"]).name
    assert name.startswith("bbox-") and name.endswith(".png") and len(name) == len("bbox-") + 10 + 4
    _, other, _ = run(base, capsys, *bbox_args(), "--no-overlay")
    assert other["images"][0]["path"] != first["images"][0]["path"]


def test_a_sheet_is_drawn_from_its_detector_bbox(base, capsys, tmp_path):
    out = tmp_path / "pics"
    code, doc, _ = run(base, capsys, "--sheet", "model#01", "--out-dir", str(out))
    sheets = json.loads((base / "work" / "structure" / f"{REL}.sheets.json").read_text(encoding="utf-8"))[
        "sheets"
    ]
    box = next(s["bbox"] for s in sheets if s["sheet_id"] == "model#01")
    (img,) = doc["images"]
    assert code == 0 and img["region"] == box and doc["query"]["sheet"] == "model#01"
    assert Path(img["path"]).parent == out and Path(img["path"]).name.startswith("model#01-")


def test_only_pngs_are_written_and_the_work_folder_is_untouched(base, capsys):
    def snapshot() -> dict[str, bytes]:
        return {
            str(p.relative_to(base / "work")): p.read_bytes()
            for p in (base / "work").rglob("*")
            if p.is_file() and "renders" not in p.parts
        }

    before = snapshot()
    code, _, _ = run(base, capsys, *bbox_args())
    assert code == 0 and snapshot() == before
    assert {p.suffix for p in (base / "work" / "renders").iterdir()} == {".png"}


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--sheet", "model#01", "--bbox", "0", "0", "10", "10"],
        ["--sheet", "model#99"],
        ["--sheet", "Plot#01"],  # paper space: out of scope
        ["--bbox", "10", "0", "0", "10"],
        ["--bbox", "0", "0", "10", "0"],
        ["--bbox", "0", "0", "10", "10", "--tiles", "0x1"],
        ["--bbox", "0", "0", "10", "10", "--tiles", "axb"],
        ["--bbox", "0", "0", "10", "10", "--tiles", "3"],
        ["--bbox", "0", "0", "10", "10", "--max-px", "10"],
    ],
)
def test_usage_errors_exit_2(base, capsys, args):
    code, _, err = run(base, capsys, *args)
    assert code == 2 and err.strip()


def test_function_raises_reader_error_with_the_exit_code(base):
    with pytest.raises(ReaderError) as exc:
        render(base / "work", REL, sheet="model#99", input_dir=base / "input")
    assert exc.value.exit_code == 2


def test_a_folder_without_inventory_is_a_usage_error(tmp_path, capsys):
    assert main(["render", str(tmp_path), "a.dxf", "--bbox", "0", "0", "1", "1"]) == 2
    assert "inventory.json" in capsys.readouterr().err


# --- review 1 (T23): what the first version got wrong --------------------------------------------------
#
# In-memory documents drawn with `_draw_region`, so a case costs milliseconds. `Shot` is one drawn region.

Z = (0.0, 0.0, 1000.0, 1000.0)


class Shot:
    def __init__(self, png: bytes, measures: dict[str, Any], warnings: list[str]):
        self.png, self.m, self.warnings = png, measures, warnings
        self.w, self.h, self.rows, self.bpp = decode_png_bytes(png)
        self.t = measures["transform"]

    def ink(self, x: float, y: float, reach: int = 2) -> bool:
        return ink_at(self.rows, self.bpp, self.t, x, y, reach)

    def lit(self) -> int:
        return sum(1 for r in self.rows for i in range(0, len(r), self.bpp) if max(r[i : i + 3]) > 60)


def draw(doc, region=Z, layers=None, max_px=1568, overlay=False, boxes=None) -> Shot:
    boxes = boxes if boxes is not None else render_mod._Boxes(doc)
    return Shot(*render_mod._draw_region(doc, boxes, region, layers, max_px, overlay))


def centroid(profile: list[int], first: int) -> float:
    """Sub-pixel position (pixel edges at integers) of the ink of `profile`, whose first pixel is `first`."""
    total = sum(profile)
    assert total > 0, "no ink where the transform says there is a line"
    return sum((first + i + 0.5) * v for i, v in enumerate(profile)) / total


def line_errors(shot: Shot, region, xs, ys) -> list[float]:
    """Centroid of each thin vertical (x) and horizontal (y) line minus where the transform puts it, px."""
    t, u = shot.t, shot.t["units_per_px"]
    x0, y0, x1, y1 = region
    errors = []
    row = t["top_margin_px"] + int((t["y1"] - (y0 + (y1 - y0) * 0.35)) / u)
    for x in xs:
        want = t["left_margin_px"] + (x - t["x0"]) / u
        lo = int(want) - 5
        errors.append(centroid([shot.rows[row][i * shot.bpp] for i in range(lo, lo + 11)], lo) - want)
    col = t["left_margin_px"] + int(((x0 + (x1 - x0) * 0.35) - t["x0"]) / u)
    for y in ys:
        want = t["top_margin_px"] + (t["y1"] - y) / u
        lo = int(want) - 5
        errors.append(centroid([shot.rows[j][col * shot.bpp] for j in range(lo, lo + 11)], lo) - want)
    return errors


def lines_doc(region):
    doc = new_doc()
    msp = doc.modelspace()
    x0, y0, x1, y1 = region
    xs = [x0 + (x1 - x0) * f for f in (0.13, 0.5, 0.87)]
    ys = [y0 + (y1 - y0) * f for f in (0.21, 0.5, 0.79)]
    for x in xs:
        msp.add_line((x, y0 - (y1 - y0)), (x, y1 + (y1 - y0)), dxfattribs={"lineweight": 0})
    for y in ys:
        msp.add_line((x0 - (x1 - x0), y), (x1 + (x1 - x0), y), dxfattribs={"lineweight": 0})
    return doc, xs, ys


# M1: the pixel <-> coordinate transform holds to a fraction of a pixel whatever the shape of the region.
# `growth` is how far the drawn area sticks out of the region on its widest side, in px (above 0.4 for
# the first two, so that a transform that reports the region edge instead of the drawn edge cannot pass).
TRANSFORM_REGIONS = [
    ((0, 0, 37, 1000), False, 0.4),
    ((0, 0, 1000, 37), False, 0.4),
    ((0, 0, 37, 1000), True, 0.0),
    ((0, 0, 1000, 37), True, 0.0),
    ((0, 0, 20000, 520), True, 0.0),
    ((0, 0, 20000, 2300), True, 0.0),
    ((0, 0, 1001, 20000), True, 0.0),
    ((0, 0, 1234, 987), False, 0.0),
    ((7370000, 5782000, 7395000, 5806000), True, 0.0),
]


@pytest.mark.parametrize(("region", "overlay", "growth"), TRANSFORM_REGIONS)
def test_transform_is_exact_to_a_fraction_of_a_pixel(region, overlay, growth):
    doc, xs, ys = lines_doc(region)
    shot = draw(doc, region, overlay=overlay)
    u = shot.t["units_per_px"]
    assert max((region[0] - shot.t["x0"]) / u, (shot.t["y1"] - region[3]) / u) >= growth
    assert max(abs(e) for e in line_errors(shot, region, xs, ys)) <= 0.25


@pytest.mark.parametrize(
    ("region", "overlay", "short_px"), [((0, 0, 13, 20000), False, 2), ((0, 0, 33, 20000), True, 3)]
)
def test_the_transform_holds_at_the_ends_of_a_sliver_whose_drawn_short_side_is_a_few_pixels(
    region, overlay, short_px
):
    # the review measured 0.28 px at 3 % and 97 % of the long axis before the inner SVG stopped keeping
    # the aspect ratio of ezdxf's rounded viewBox
    x0, y0, x1, y1 = region
    doc = new_doc()
    ys = [y0 + (y1 - y0) * f for f in (0.03, 0.97)]  # the scale error grows toward the ends of the long axis
    for y in ys:
        doc.modelspace().add_line((x0 - (x1 - x0), y), (x1 + (x1 - x0), y), dxfattribs={"lineweight": 0})
    shot = draw(doc, region, overlay=overlay)
    t = shot.t
    assert (x1 - x0) / t["units_per_px"] <= short_px + 1  # the drawn area is a few pixels wide
    assert max(abs(e) for e in line_errors(shot, region, [], ys)) <= 0.12


def test_line_weight_keeps_its_pixel_width():
    doc = new_doc()
    doc.modelspace().add_line((500, -1000), (500, 2000), dxfattribs={"lineweight": 25})
    shot = draw(doc)
    row = shot.h // 2
    width = sum(shot.rows[row][i * shot.bpp] for i in range(shot.w)) / 255
    assert 1.7 <= width <= 2.3  # 0.25 mm: about 2 px


def ink_runs(profile: list[int]) -> list[float]:
    """Sub-pixel centre of each run of consecutive lit pixels of a one-pixel-wide profile."""
    runs: list[tuple[int, list[int]]] = []
    for i, v in enumerate(profile):
        if v > 0 and runs and runs[-1][0] + len(runs[-1][1]) == i:
            runs[-1][1].append(v)
        elif v > 0:
            runs.append((i, [v]))
    return [centroid(values, first) for first, values in runs]


def test_the_tick_marks_sit_on_round_values():
    shot = draw(new_doc(), (-3000.0, 100.0, 21000.0, 14100.0), max_px=1000, overlay=True)
    t, u = shot.t, shot.t["units_per_px"]
    left, top = t["left_margin_px"], t["top_margin_px"]
    # the y ticks span [left - 5, left] and the labels end at left - 8: column left - 3 holds the ticks only
    y_values = [t["y1"] - (c - top) * u for c in ink_runs([r[(left - 3) * shot.bpp] for r in shot.rows])]
    # the x ticks span [top + h, top + h + 5], the bottom margin is 34 px: row top + h + 2 has only ticks
    row = shot.rows[shot.h - 34 + 2]
    x_values = [t["x0"] + (c - left) * u for c in ink_runs([row[i * shot.bpp] for i in range(shot.w)])]
    for values in (y_values, x_values):
        assert len(values) >= 3
        step = abs(round(values[1] - values[0], -2))
        assert step in (500, 1000, 2000, 5000)
        assert all(abs(v / step - round(v / step)) * step <= 0.3 * u for v in values)


# M2: a construction line that crosses the region is drawn across it, and an INSERT that holds one is kept.
def test_a_ray_and_an_xline_are_drawn_across_the_region():
    doc = new_doc()
    msp = doc.modelspace()
    msp.add_ray((-3000, 500), (1, 0))  # 500 high, from far left through the region
    msp.add_xline((5000, 5000), (1, 1))  # the diagonal
    msp.add_ray((3000, 200), (1, 0))  # starts right of the region and points away
    shot = draw(doc)
    assert shot.ink(100, 500) and shot.ink(900, 500)
    assert shot.ink(300, 300) and shot.ink(700, 700) and not shot.ink(300, 400)
    assert not shot.ink(500, 200)


def test_an_insert_holding_an_xline_is_not_pruned_away():
    doc = new_doc()
    block = doc.blocks.new("XB")
    block.add_circle((0, 0), 10)
    block.add_xline((0, 0), (1, 1))
    doc.modelspace().add_blockref("XB", (-3000, -2000))  # the xline: y = x + 1000 ... through (0, 1000)
    doc.modelspace().add_blockref("XB", (-3000, -3000))  # y = x: the diagonal
    shot = draw(doc)
    assert shot.m["entities_pruned"] == 2  # the two far circles, not the INSERTs that hold the xlines
    assert shot.ink(500, 500) and shot.ink(200, 200)


# M3: freezing the layer of an INSERT hides the whole reference; switching it off hides only the layer 0
# content (it follows the INSERT's layer).
def layered_insert(state: str, nested: bool = False):
    doc = new_doc()
    for name in ("INS", "B", "VIS"):
        doc.layers.add(name)
    block = doc.blocks.new("BLK")
    block.add_circle((0, 0), 100, dxfattribs={"layer": "B"})
    block.add_circle((300, 0), 100, dxfattribs={"layer": "0"})
    if nested:
        outer = doc.blocks.new("OUT")
        outer.add_circle((0, 300), 100, dxfattribs={"layer": "VIS"})
        outer.add_blockref("BLK", (0, 0), dxfattribs={"layer": "INS"})
        doc.modelspace().add_blockref("OUT", (500, 500), dxfattribs={"layer": "VIS"})
    else:
        doc.modelspace().add_blockref("BLK", (500, 500), dxfattribs={"layer": "INS"})
    if state == "frozen":
        doc.layers.get("INS").freeze()
    elif state == "off":
        doc.layers.get("INS").off()
    return doc


@pytest.mark.parametrize(
    ("state", "layer_b", "layer_zero"),
    [("on", True, True), ("off", True, False), ("frozen", False, False)],
)
def test_a_frozen_insert_layer_hides_the_whole_reference(state, layer_b, layer_zero):
    shot = draw(layered_insert(state))
    assert shot.ink(600, 500) is layer_b  # block circle on layer B
    assert shot.ink(900, 500) is layer_zero  # block circle on layer 0


def test_a_nested_insert_on_a_frozen_layer_is_hidden_but_its_parent_content_is_drawn():
    shot = draw(layered_insert("frozen", nested=True))
    assert shot.ink(600, 800)  # the circle on VIS in the outer block
    assert not shot.ink(600, 500) and not shot.ink(900, 500)


def test_a_frozen_insert_layer_hides_the_reference_under_a_layer_filter():
    shot = draw(layered_insert("frozen"), layers=frozenset({"b"}))
    assert not shot.ink(600, 500)


# M7: pruning is exact. The same region drawn with the box test and with every box unknown is the same PNG.
def _unknown_boxes(doc):
    boxes = render_mod._Boxes(doc)
    boxes.entity = lambda e, stack=(): render_mod._UNKNOWN  # type: ignore[method-assign]
    return boxes


def zoo_base_point(doc, msp):
    block = doc.blocks.new("BP", base_point=(5000, 0))
    block.add_circle((5000, 0), 200)
    msp.add_blockref("BP", (500, 500))
    return [(500, 700)]


def zoo_rotated(doc, msp):
    block = doc.blocks.new("RT")
    block.add_lwpolyline([(0, 0), (600, 0), (600, 300), (0, 300)], close=True)
    insert = msp.add_blockref("RT", (1100, 100), dxfattribs={"rotation": 35})
    # the corner (0, 300) of the block lands left of the insert point: only that part is inside the region
    return [tuple(insert.matrix44().transform((0, 300, 0)))[:2]]


def zoo_nonuniform(doc, msp):
    block = doc.blocks.new("RN")
    block.add_line((2000, 0), (4000, 0))
    msp.add_blockref("RN", (-1500, 500), dxfattribs={"xscale": 0.5, "yscale": 3})
    msp.add_blockref("RN", (500, -2500), dxfattribs={"rotation": 90, "yscale": 0.2})
    return [(0, 500), (500, 100)]


def zoo_nested(doc, msp):
    inner = doc.blocks.new("IN")
    inner.add_line((0, 0), (1000, 0))
    mid = doc.blocks.new("MID")
    mid.add_blockref("IN", (3000, 0), dxfattribs={"rotation": 90})
    msp.add_blockref("MID", (-2500, 0))
    return [(500, 500)]


def zoo_nested_mirrored(doc, msp):
    inner = doc.blocks.new("IN2")
    inner.add_circle((800, 0), 100)
    mid = doc.blocks.new("MID2")
    mid.add_blockref("IN2", (0, 0), dxfattribs={"extrusion": (0, 0, -1)})
    msp.add_blockref("MID2", (-300, 500), dxfattribs={"xscale": -1})  # the circle ends up at (500, 500)
    return [(600, 500), (400, 500)]


def zoo_minsert(doc, msp):
    block = doc.blocks.new("MJ")
    block.add_circle((0, 0), 100)
    # 3 rows 300 apart, 4 columns 250 apart: the first cell (-400, 100) is outside the region, others inside
    msp.add_blockref("MJ", (-400, 100)).grid(size=(3, 4), spacing=(300, 250))
    return [(200, 100), (450, 700)]


def zoo_attrib(doc, msp):
    block = doc.blocks.new("TAGGED")
    block.add_circle((0, 0), 10)
    block.add_attdef("TAG", (0, 0), dxfattribs={"height": 100})
    msp.add_blockref("TAGGED", (-3000, -3000)).add_attrib(
        "TAG", "WWWW", (100, 500), dxfattribs={"height": 100}
    )
    return []  # text: the drawn pixels are asserted by the lit count


def zoo_dimension(doc, msp):
    msp.add_linear_dim(base=(0, 400), p1=(-600, 100), p2=(400, 100), dimstyle="EZDXF").render()
    return [(400, 250)]  # the extension line at p2


def zoo_hatch(doc, msp):
    solid = msp.add_hatch(color=1)
    solid.paths.add_polyline_path([(-500, -500), (300, -500), (300, 300), (-500, 300)], is_closed=True)
    solid.set_solid_fill()
    return [(100, 100)]


def zoo_hatch_pattern(doc, msp):
    # ezdxf orders the lines of a pattern differently from run to run: the pixels agree only to antialiasing
    pattern = msp.add_hatch(color=3)
    pattern.paths.add_polyline_path([(700, 700), (1500, 700), (1500, 1500), (700, 1500)], is_closed=True)
    pattern.set_pattern_fill("ANSI31", scale=20)
    return []


def zoo_ocs_circle(doc, msp):
    msp.add_circle((300, 500), 400, dxfattribs={"extrusion": (0, 0, -1)})  # the WCS centre is (-300, 500)
    return [(100, 500)]


def zoo_wide_polyline(doc, msp):
    msp.add_lwpolyline([(-2000, -100), (2000, -100)], dxfattribs={"const_width": 400})
    return [(500, 50)]


def zoo_ellipse_spline(doc, msp):
    msp.add_ellipse((-600, 500), major_axis=(800, 0), ratio=0.3)
    msp.add_spline([(-1500, 0), (-500, 900), (200, 300)])
    return [(200, 300)]


def zoo_ray(doc, msp):
    msp.add_ray((-3000, 500), (1, 0))
    return [(500, 500)]


ZOO = [
    zoo_base_point,
    zoo_rotated,
    zoo_nonuniform,
    zoo_nested,
    zoo_nested_mirrored,
    zoo_minsert,
    zoo_attrib,
    zoo_dimension,
    zoo_hatch,
    zoo_hatch_pattern,
    zoo_ocs_circle,
    zoo_wide_polyline,
    zoo_ellipse_spline,
    zoo_ray,
]


@pytest.mark.parametrize("build", ZOO, ids=lambda f: f.__name__.removeprefix("zoo_"))
def test_pruning_never_changes_the_image(build):
    doc = new_doc(setup=True)
    msp = doc.modelspace()
    points = build(doc, msp)
    msp.add_circle((50000, 50000), 100)  # something to prune in every case
    pruned = draw(doc, max_px=800)
    unpruned = draw(doc, max_px=800, boxes=_unknown_boxes(doc))
    assert pruned.m["entities_pruned"] >= 1 and unpruned.m["entities_pruned"] == 0
    assert pruned.lit() > 0, "the case draws nothing in the region: it proves nothing"
    assert all(pruned.ink(x, y, reach=4) for x, y in points)
    if build is zoo_hatch_pattern:
        worst = max(
            abs(a - b)
            for ra, rb in zip(pruned.rows, unpruned.rows, strict=True)
            for a, b in zip(ra, rb, strict=True)
        )
        assert worst <= 64
    else:
        assert pruned.png == unpruned.png


def test_a_line_in_the_sliver_the_drawn_area_adds_is_not_pruned():
    # 1000 x 1001 units in an 800 px image: the drawn area is 0.4 px wider than the region on each side
    region = (0.0, 0.0, 1000.0, 1001.0)
    doc = new_doc()
    doc.modelspace().add_line((1000.25, -500), (1000.25, 1500), dxfattribs={"lineweight": 0})
    pruned = draw(doc, region, max_px=800)
    unpruned = draw(doc, region, max_px=800, boxes=_unknown_boxes(doc))
    assert unpruned.lit() > 0 and pruned.png == unpruned.png


# M3 (T21 C1) for composites, m1: a DIMENSION is kept or dropped as a whole by its own layer.
def test_a_dimension_is_filtered_by_its_own_layer_not_by_its_pieces():
    doc = new_doc(setup=True)
    doc.layers.add("DIM")
    msp = doc.modelspace()
    dim = msp.add_linear_dim(
        base=(500, 600), p1=(100, 500), p2=(900, 500), dimstyle="EZDXF", dxfattribs={"layer": "DIM"}
    )
    dim.render()
    dimension = msp.query("DIMENSION").first
    assert dimension is not None
    for piece in doc.blocks.get(dimension.dxf.geometry):
        piece.dxf.layer = "0"  # every piece on layer 0, the dimension itself on DIM
    kept = draw(doc, layers=frozenset({"dim"}))
    other = draw(doc, layers=frozenset({"nothing"}))
    assert kept.lit() > 0 and other.lit() == 0


# M4: `--max-px` stops at the model's image budget.
def test_max_px_above_the_model_budget_is_a_usage_error(base, capsys):
    code, _, err = run(base, capsys, *bbox_args(), "--max-px", "1569")
    assert code == 2 and "1568" in err
    with pytest.raises(ReaderError) as exc:
        render(base / "work", REL, bbox=REGION, max_px=2000, input_dir=base / "input")
    assert exc.value.exit_code == 2
    code, doc, _ = run(base, capsys, *bbox_args(), "--max-px", "1568")
    assert code == 0 and doc["query"]["max_px"] == 1568


def test_the_schema_refuses_a_max_px_above_the_model_budget(base, capsys):
    _, doc, _ = run(base, capsys, *bbox_args())
    doc["query"]["max_px"] = 1569
    assert validate("render", doc)


# M5: whatever ezdxf prints becomes a warning; stdout holds the document only.
def test_what_ezdxf_prints_becomes_a_warning_and_stdout_stays_json(base, capsys, monkeypatch):
    original = render_mod._RegionFrontend.draw_curve_entity

    def noisy(self, entity, properties):
        print("hatching timeout of 30s reached for HATCH(#2A) - aborting")
        print("some other chatter")
        original(self, entity, properties)

    monkeypatch.setattr(render_mod._RegionFrontend, "draw_curve_entity", noisy, raising=False)
    code, doc, _ = run(base, capsys, *bbox_args())  # json.loads fails on any stray line
    assert code == 0 and validate("render", doc) == []
    joined = "\n".join(doc["warnings"])
    assert "hatch" in joined and "timeout" in joined and "some other chatter" in joined


# M6: a tick label is whole or absent, never cut at the image edge.
def edge_ink(shot: Shot) -> bool:
    """Any colour ink (the alpha byte does not count) in the two leftmost pixel columns."""
    return any(max(r[i : i + 3]) > 0 for r in shot.rows for i in (0, shot.bpp))


@pytest.mark.parametrize(
    "region",
    [
        (0.0, 1234510000.0, 20000.0, 1234530000.0),  # 10 digits
        (0.0, -1234510000.0, 20000.0, -1234490000.0),  # a sign and 10 digits
        (0.0, 5806000.0, 1.0, 5806001.0),  # 5806000.5: a decimal
    ],
)
def test_y_labels_are_never_cut_at_the_image_edge(region):
    shot = draw(new_doc(), region, overlay=True)
    assert not edge_ink(shot), "ink in the first two columns: a label is cut"
    assert shot.t["left_margin_px"] >= 94


def test_a_label_that_cannot_fit_is_dropped_with_a_warning():
    shot = draw(new_doc(), (0.0, 1234519000.0, 200.0, 1234529000.0), max_px=128, overlay=True)  # one tick
    assert not edge_ink(shot)
    assert any("label" in w for w in shot.warnings)


# Invisible flag (group 60): ezdxf does not draw it; the image reports how many such entities it holds.
def test_entities_with_the_invisible_flag_are_counted_not_drawn():
    doc = new_doc()
    doc.layers.add("OFF").off()
    msp = doc.modelspace()
    block = doc.blocks.new("IB")
    block.add_circle((0, 0), 100)
    msp.add_circle((200, 200), 50, dxfattribs={"invisible": 1})
    msp.add_circle((600, 200), 50)
    msp.add_blockref("IB", (200, 600), dxfattribs={"invisible": 1})
    msp.add_circle((600, 600), 50, dxfattribs={"layer": "OFF"})  # off, not flagged: not counted
    shot = draw(doc)
    assert shot.ink(650, 200) and not shot.ink(250, 200) and not shot.ink(300, 600) and not shot.ink(650, 600)
    assert shot.m["entities_invisible"] == 2
    assert any("invisible" in w and "2" in w for w in shot.warnings)


def test_a_region_without_invisible_entities_reports_zero():
    doc = new_doc()
    doc.modelspace().add_circle((500, 500), 50)
    shot = draw(doc)
    assert shot.m["entities_invisible"] == 0 and not any("invisible" in w for w in shot.warnings)


# m3: entities_drawn counts what was drawn: leaves, a composite once, nothing hidden.
def test_entities_drawn_counts_what_ezdxf_drew():
    doc = new_doc(setup=True)
    doc.layers.add("OFF").off()
    msp = doc.modelspace()
    msp.add_circle((200, 200), 50)
    msp.add_circle((300, 200), 50, dxfattribs={"layer": "OFF"})
    msp.add_circle((400, 200), 50, dxfattribs={"invisible": 1})
    msp.add_leader([(500, 500), (700, 600), (800, 600)])
    msp.add_text("tiny", dxfattribs={"insert": (500, 800), "height": 1e-10})  # ezdxf skips it
    shot = draw(doc)
    assert shot.m["entities_drawn"] == 2  # the circle and the leader, once


# m2: a layer name that is not in the file is said so.
def test_an_unknown_layer_name_is_a_warning(base, capsys):
    _, doc, _ = run(base, capsys, *bbox_args(), "--layer", LAYER_A, "NoSuchLayer")
    assert any("NoSuchLayer" in w for w in doc["warnings"])
    _, doc, _ = run(base, capsys, *bbox_args(), "--layer", LAYER_A.lower())
    assert not any("not in the file" in w for w in doc["warnings"])


# m5: a top-level entity is boxed once per call, not once per tile.
def test_top_level_boxes_are_computed_once_per_call(base, capsys, monkeypatch):
    calls: list[bool] = []
    original = render_mod._extents

    def counting(entities, *args, **kwargs):
        calls.append(any(not e.is_virtual for e in entities))
        return original(entities, *args, **kwargs)

    monkeypatch.setattr(render_mod, "_extents", counting)
    run(base, capsys, *bbox_args())
    single = sum(calls)
    calls.clear()
    run(base, capsys, *bbox_args(), "--tiles", "2x2")
    assert single > 0 and sum(calls) == single


# m6: a re-intake that changes the drawing changes the file name; a failed write leaves nothing behind.
def test_the_file_name_follows_the_drawing_sha256(base, capsys, tmp_path):
    work = tmp_path / "work"
    shutil.copytree(base / "work", work)
    inventory = work / "inventory.json"
    doc = json.loads(inventory.read_text(encoding="utf-8"))
    (row,) = [r for r in doc["files"] if r["path"] == REL]
    row["sha256"] = "0" * 64
    inventory.write_text(json.dumps(doc), encoding="utf-8")
    capsys.readouterr()
    code = main(["render", str(work), REL, "--input-dir", str(base / "input"), *bbox_args()])
    changed = json.loads(capsys.readouterr().out)["images"][0]["path"]
    _, original, _ = run(base, capsys, *bbox_args())
    assert code == 0 and Path(changed).name != Path(original["images"][0]["path"]).name


def test_file_names_differ_with_every_part_of_the_key():
    args: list[Any] = ["bbox", REL, "a" * 64, (0, 0), (0.0, 0.0, 1.0, 1.0), ["x"], 1568, True]
    names = {render_mod._file_name(*args)}
    for i, other in [
        (1, "other.dxf"),
        (2, "b" * 64),
        (3, (1, 0)),
        (4, (0.0, 0.0, 1.0, 2.0)),
        (5, ["y"]),
        (6, 1000),
        (7, False),
    ]:
        changed = list(args)
        changed[i] = other
        names.add(render_mod._file_name(*changed))
    assert len(names) == 8


def test_a_failed_write_leaves_no_file_behind(base, capsys, monkeypatch, tmp_path):
    out = tmp_path / "pics"

    def boom(self, target):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", boom)
    code, _, err = run(base, capsys, *bbox_args(), "--out-dir", str(out))
    assert code == 3 and "disk full" in err
    assert list(out.iterdir()) == []


def test_two_identical_renders_at_once_both_succeed(base, capsys, monkeypatch, tmp_path):
    out = tmp_path / "pics"
    original = Path.replace
    inner: list[int] = []

    def replace_while_another_render_runs(self, target):
        if not inner:  # the second render starts, and ends, while this one holds its temporary file
            inner.append(-1)
            inner[0] = run(base, capsys, *bbox_args(), "--out-dir", str(out))[0]
        return original(self, target)

    monkeypatch.setattr(Path, "replace", replace_while_another_render_runs)
    code, doc, err = run(base, capsys, *bbox_args(), "--out-dir", str(out))
    assert inner == [0] and code == 0, err
    assert [p.name for p in out.iterdir()] == [Path(doc["images"][0]["path"]).name]  # no temporary file left


# m8: an unexpected ezdxf failure is a message and an exit code, not a traceback.
def test_a_drawing_failure_is_reported_with_exit_1(base, capsys, monkeypatch):
    def boom(self, *args, **kwargs):
        raise RuntimeError("ezdxf broke")

    monkeypatch.setattr(render_mod._RegionFrontend, "draw_layout", boom)
    code, _, err = run(base, capsys, *bbox_args())
    assert code == 1 and "ezdxf broke" in err


# m7: the shipped example is what the code emits.
def test_the_example_matches_the_transform_the_code_emits():
    example = json.loads(
        (Path(__file__).parent.parent / "schemas" / "examples" / "render.example.json").read_text()
    )
    assert validate("render", example) == []
    (img,) = example["images"]
    t = img["transform"]
    assert t["left_margin_px"] >= 94 and t["top_margin_px"] == 10
    grown = (img["region"][0] - t["x0"]) / t["units_per_px"]
    assert 0 <= grown < 1  # x0 is the drawn edge, left of the requested one by less than a pixel


# m5: the children of an INSERT that lies wholly inside the drawn area are not boxed again.
def test_the_children_of_an_insert_wholly_inside_the_area_are_not_boxed():
    doc = new_doc()
    block = doc.blocks.new("IN")
    for i in range(5):
        block.add_circle((i * 20, 0), 5)
    doc.blocks.new("HALF").add_circle((0, 0), 5)
    doc.modelspace().add_blockref("IN", (300, 300))
    boxed: list[int] = []
    original = render_mod._Boxes.entity

    def counting(self, e, stack=()):
        boxed.append(int(e.is_virtual and not stack))
        return original(self, e, stack)

    render_mod._Boxes.entity = counting  # type: ignore[method-assign]
    try:
        shot = draw(doc)
    finally:
        render_mod._Boxes.entity = original  # type: ignore[method-assign]
    assert shot.m["entities_pruned"] == 0 and shot.ink(305, 300) and shot.ink(385, 300)
    assert sum(boxed) == 0


def test_the_children_of_an_insert_that_crosses_the_area_are_still_pruned():
    doc = new_doc()
    block = doc.blocks.new("OUT")
    block.add_circle((0, 0), 5)
    block.add_circle((5000, 0), 5)  # far outside the region
    doc.modelspace().add_blockref("OUT", (500, 500))
    shot = draw(doc)
    assert shot.m["entities_pruned"] == 1 and shot.ink(505, 500)


def test_an_xline_or_ray_that_misses_the_region_is_not_counted_as_drawn():
    doc = new_doc()
    doc.modelspace().add_ray((2000, 500), (1, 0))  # starts right of the region and points away
    doc.modelspace().add_xline((2000, 2000), (1, 0))  # parallel to the region, above it
    doc.modelspace().add_ray((-500, 500), (1, 0))  # crosses the region
    shot = draw(doc)
    assert shot.m["entities_drawn"] == 1 and shot.lit() > 0
    assert shot.warnings == []  # a line that misses the region is no defect


# Mutation survivors of the T23 review.
def test_the_clip_of_an_infinite_line_has_no_false_hits():
    box = (0.0, 0.0, 10.0, 10.0)
    clip = render_mod._clip_infinite
    assert clip(Vec3(0, -100, 0), Vec3(1, 1, 0), False, box) is None  # a diagonal that misses the corner
    assert clip(Vec3(-5, 50, 0), Vec3(1, 0, 0), True, box) is None  # parallel to x, outside the box
    assert clip(Vec3(50, -5, 0), Vec3(0, 1, 0), False, box) is None  # parallel to y, outside the box
    assert clip(Vec3(5, 5, 0), Vec3(0, 0, 0), False, box) is None  # no direction
    assert clip(Vec3(-5, 5, 0), Vec3(1, 0, 0), False, box) == (Vec3(0, 5, 0), Vec3(10, 5, 0))


@pytest.mark.parametrize("direction", [(10, 3), (1, 1), (3, 10), (3, -10), (10, -3)])
def test_an_xline_is_cut_beyond_the_edges_of_the_image(direction):
    # a thick line in a small image looks the same as a very long LINE (round caps hide the cut)
    dx, dy = direction
    doc = new_doc()
    doc.modelspace().add_xline((500, 500), direction, dxfattribs={"lineweight": 211})
    ref = new_doc()
    far = 100000 / max(abs(dx), abs(dy))
    ref.modelspace().add_line(
        (500 - far * dx, 500 - far * dy), (500 + far * dx, 500 + far * dy), dxfattribs={"lineweight": 211}
    )
    assert draw(doc, max_px=100).png == draw(ref, max_px=100).png


def test_the_invisible_count_follows_the_rule_of_harness_geometry():
    # hidden = layer off or frozen for an entity, frozen only for an INSERT (an off layer hides only layer 0)
    doc = new_doc()
    doc.layers.add("OFF").off()
    doc.layers.add("ICE").freeze()
    doc.blocks.new("B").add_circle((0, 0), 10)
    msp = doc.modelspace()
    flag = {"invisible": 1}
    msp.add_circle((100, 100), 10, dxfattribs={**flag, "layer": "OFF"})  # hidden: not counted
    msp.add_circle((200, 100), 10, dxfattribs={**flag, "layer": "ICE"})  # hidden: not counted
    msp.add_circle((300, 100), 10, dxfattribs=flag)  # counted
    msp.add_blockref("B", (100, 300), dxfattribs={**flag, "layer": "ICE"})  # frozen INSERT: hidden
    msp.add_blockref("B", (200, 300), dxfattribs={**flag, "layer": "OFF"})  # off INSERT: counted
    msp.add_blockref("B", (300, 300), dxfattribs=flag)  # counted
    assert draw(doc).m["entities_invisible"] == 3


def test_an_invisible_attribute_and_an_invisible_edged_3dface_are_not_group_60_entities():
    # ezdxf skips both as "invisible", but neither carries group 60: they are not counted
    doc = new_doc()
    block = doc.blocks.new("TAG")
    block.add_circle((0, 0), 50)
    block.add_attdef("MARK", (0, -80), dxfattribs={"height": 20})
    attrib = doc.modelspace().add_blockref("TAG", (500, 500)).add_attrib("MARK", "P1", (500, 420))
    attrib.is_invisible = True
    face = doc.modelspace().add_3dface([(100, 100), (200, 100), (200, 200), (100, 200)])
    face.dxf.invisible_edges = 15
    shot = draw(doc)
    assert shot.m["entities_invisible"] == 0
    assert not any("invisible" in w for w in shot.warnings)


def test_an_entity_hidden_by_its_layer_is_not_reported_as_not_drawn():
    doc = new_doc()
    doc.layers.add("OFF").off()
    doc.modelspace().add_circle((500, 500), 50, dxfattribs={"layer": "OFF"})
    assert draw(doc).warnings == []


def test_an_xref_insert_is_reported_as_not_expanded():
    doc = new_doc()
    head = doc.blocks.new("XR").block
    assert head is not None
    head.dxf.flags = 4
    head.dxf.xref_path = "other.dwg"
    doc.modelspace().add_blockref("XR", (500, 500))
    expected = "some INSERTs were not expanded: {'xref': 1}"
    assert [w for w in draw(doc).warnings if "expanded" in w] == [expected]


def test_an_insert_of_a_missing_block_stops_the_render_with_a_reason():
    # ezdxf cannot enter it, so the render fails with exit 1 instead of drawing a picture with a hole
    doc = new_doc()
    doc.modelspace().add_blockref("GONE", (500, 500))
    with pytest.raises(ReaderError, match='block definition for "GONE" does not exist'):
        draw(doc)


def test_the_children_of_an_insert_crossing_the_top_edge_are_pruned():
    doc = new_doc()
    block = doc.blocks.new("UP")
    block.add_circle((0, 0), 5)
    block.add_circle((0, 5000), 5)  # far above the region
    doc.modelspace().add_blockref("UP", (500, 500))
    assert draw(doc).m["entities_pruned"] == 1


def _dimension_with_block(doc, fill) -> None:
    msp = doc.modelspace()
    msp.add_linear_dim(base=(500, 600), p1=(100, 500), p2=(900, 500), dimstyle="EZDXF").render()
    dimension = msp.query("DIMENSION").first
    assert dimension is not None
    block = doc.blocks.get(dimension.dxf.geometry)
    block.delete_all_entities()
    fill(block)


@pytest.mark.parametrize(
    ("fill", "drawn"),
    [
        (lambda b: None, 0),  # a composite that makes nothing and skips nothing
        (
            lambda b: b.add_text("t", dxfattribs={"insert": (500, 500), "height": 1e-10}),
            0,
        ),  # only a skipped piece
        (
            lambda b: (
                b.add_circle((500, 500), 20),
                b.add_text("t", dxfattribs={"insert": (500, 500), "height": 1e-10}),
            ),
            1,
        ),
    ],
    ids=["empty", "only-skipped", "drawn-and-skipped"],
)
def test_a_composite_counts_as_drawn_only_when_a_piece_was_drawn(fill, drawn):
    doc = new_doc(setup=True)
    _dimension_with_block(doc, fill)
    assert draw(doc).m["entities_drawn"] == drawn


def test_a_hatch_timeout_is_said_to_leave_the_hatch_unfilled(base, capsys, monkeypatch):
    original = render_mod._RegionFrontend.draw_curve_entity

    def noisy(self, entity, properties):
        print("hatching timeout of 30s reached for HATCH(#2A) - aborting")
        original(self, entity, properties)

    monkeypatch.setattr(render_mod._RegionFrontend, "draw_curve_entity", noisy, raising=False)
    _, doc, _ = run(base, capsys, *bbox_args())
    assert any(w.startswith("a hatch was left unfilled, ezdxf:") for w in doc["warnings"])


def test_a_block_box_is_computed_once_however_often_it_is_placed():
    doc = new_doc()
    doc.blocks.new("ONE").add_circle((0, 0), 10)
    for x in (100, 300, 500):
        doc.modelspace().add_blockref("ONE", (x, 500))
    calls: list[int] = []
    original = render_mod._extents

    def counting(entities, *args, **kwargs):
        calls.append(len(list(entities)))
        return original(entities, *args, **kwargs)

    render_mod._extents = counting
    try:
        draw(doc)
    finally:
        render_mod._extents = original
    assert calls == [1]


def test_the_left_margin_widens_to_the_longest_y_label_and_stops_at_a_quarter_of_max_px():
    wide = draw(new_doc(), (0.0, 1234510000.0, 20000.0, 1234530000.0), overlay=True)  # 10 digit labels
    assert wide.t["left_margin_px"] >= 112 and not any("label" in w for w in wide.warnings)
    capped = draw(new_doc(), (0.0, 1234519000.0, 200.0, 1234529000.0), max_px=128, overlay=True)
    assert capped.t["left_margin_px"] == 94  # the cap max(94, 128 // 4): the label is dropped instead


def test_a_very_long_label_is_held_at_the_cap_of_a_quarter_of_max_px():
    shot = draw(new_doc(), (0.0, -1.2345e19, 2e18, -1.2e19), max_px=800, overlay=True)
    assert shot.t["left_margin_px"] == 200 and any("label" in w for w in shot.warnings)
    assert not edge_ink(shot)
