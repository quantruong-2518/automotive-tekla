#!/usr/bin/env bash
# EVAL-5 setup: scratch repo copy at the frozen commit with rev-7 skills, three project folders (r, h, m),
# frozen-inputs record. Usage: setup.sh <frozen-sha> <eval-dir>. Run from the main checkout.
# <eval-dir> must already hold key/ (EVAL-5 key) and key-sha256.txt; it must not hold repo/.
set -euo pipefail
SHA="$1"
E="$2"
MAIN="$(pwd)"
REPO="$E/repo"
[ -e "$REPO" ] && { echo "refusing: $REPO exists" >&2; exit 2; }
[ -f "$E/key-sha256.txt" ] || { echo "refusing: $E/key-sha256.txt missing" >&2; exit 2; }
mkdir -p "$REPO"
git archive "$SHA" | tar -x -C "$REPO"
rm -rf "$REPO/dwg-lab/proposals/skills/eval3" "$REPO/dwg-lab/proposals/skills/eval4" "$REPO/dwg-lab/proposals/skills/eval5"
# rev 7 (approval SIMULATED unless the engineer approved it) replaces the active skills in the copy only
for s in drawing-intake structural-drawing-reader drawing-analysis-report tekla-conversion-plan; do
  rm -rf "$REPO/.claude/skills/$s"
  cp -r "$REPO/dwg-lab/proposals/skills/rev7/$s" "$REPO/.claude/skills/$s"
done
(cd "$REPO" && uv sync -q)

S="$MAIN/dwg-lab/samples/L3-complex"
for a in r h m; do mkdir -p "$E/projects/eval5-$a/input" "$E/projects/eval5-$a/tmp"; done
cp "$S/eval4-heldout/264_6-story_house_6x16.5m.dwg" "$S/eval4-heldout/271_3-story_house_14.2x19.7m.dwg" \
   "$S/eval4-heldout/278_5-story_house_4.4x15.3m.dwg" "$S/eval4-heldout/180_steel_building.dwg" \
   "$E/projects/eval5-r/input/"
cp "$S"/eval5-heldout/*.dwg "$E/projects/eval5-h/input/"
cp "$S/dwgshare-rc-projects/267_4-story_house_complete_project.dwg" \
   "$S/dwgshare-rc-projects/433_townhouse_12m_x_20.6m.dwg" \
   "$S/structuralbd-complete-sets/Complete_Steel_Building_Drawing_01.dwg" "$E/projects/eval5-m/input/"

{
  echo "# EVAL-5 frozen inputs (written before any arm output)"
  echo
  echo "- written: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "- harness commit: $SHA (branch feat/tool-wave-4)"
  echo "- knowledge/font-encodings.csv sha256: $(sha256sum "$REPO/knowledge/font-encodings.csv" | cut -d' ' -f1)"
  echo "- skills under test: rev 7 from dwg-lab/proposals/skills/rev7 at $SHA"
  echo "- rev-7 skills tree sha256: $(cd "$REPO/.claude/skills" && find drawing-intake structural-drawing-reader drawing-analysis-report tekla-conversion-plan -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
  echo "- converter: $("$MAIN/dwg-lab/tools/libredwg/bin/dwg2dxf" --version 2>&1 | head -1)"
  echo "- answer key (H): $(tr '\n' ' ' < "$E/key-sha256.txt")"
  echo "- input drawings sha256:"
  for f in "$E"/projects/*/input/*.dwg; do echo "  - $(basename "$(dirname "$(dirname "$f")")")/$(basename "$f") $(sha256sum "$f" | cut -d' ' -f1)"; done
} > "$E/frozen-inputs.md"
cat "$E/frozen-inputs.md"
