"""
PRBD Automated Drainage Design System - Entry Point

Modules:
  models.py              - Data structures (Point3D, Fixture, Panel, etc.)
  pathfinding.py         - Algorithm 1: Heuristic Pathfinding (A* + Dijkstra)
  vent_design.py         - Scenario-based Vent Pipe Design (3 scenarios)
  panelization.py        - Algorithm 2: Panelization (cut at panel boundaries)
  cutting_optimization.py - Algorithm 3: Pipe Cutting Optimization (1D-CSP)
  pipeline.py            - Full PRBD Pipeline orchestrator

Usage:
  python main.py                          # run default model (model 1)
  python main.py --model 2                 # run model #2
  python main.py --model 3 --no-viz        # run model #3 without visualization
  python main.py --list-models             # show available models
  python main.py --run-all --output-dir ../output_dir --no-viz
"""

import argparse
import json
import os
import sys
import math
from datetime import datetime
from pathlib import Path

from models import XYZ, PlumbingFixture, Opening, Panel, Wall, Floor, Joist, JoistConstraint, RoutingConfig, WallOpening, Pipe, SystemType
from vent_design import VentScenario
from pipeline import PRBDPipeline
from pathfinding import HeuristicPathfinder
from visualizer import visualize_multi_storey, StoreyData

# Alias for readability
Point3D = XYZ

# Default directories (relative to project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = PROJECT_ROOT / "input_dir"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output_dir"

# =============================================================================
# Building geometry helpers
# =============================================================================

def _make_outer_walls(prefix: str, floor_w: float, floor_d: float,
                      west_windows: list = None) -> list[Wall]:
    """Create 4 perimeter walls. Optionally override West wall windows."""
    south = Wall(name=f"{prefix}_South", start_point=XYZ(0, 0, 0), end_point=XYZ(floor_w, 0, 0))
    south.doors   = [WallOpening("door", offset=1800, width=900, z_bottom=0, height=2100)]
    south.windows = [WallOpening("window", offset=600, width=900, z_bottom=900, height=1200)]

    east = Wall(name=f"{prefix}_East", start_point=XYZ(floor_w, 0, 0), end_point=XYZ(floor_w, floor_d, 0))
    east.windows = [WallOpening("window", offset=600, width=900, z_bottom=900, height=1200),
                    WallOpening("window", offset=2100, width=900, z_bottom=900, height=1200)]

    north = Wall(name=f"{prefix}_North", start_point=XYZ(floor_w, floor_d, 0), end_point=XYZ(0, floor_d, 0))
    north.windows = [WallOpening("window", offset=1200, width=900, z_bottom=900, height=1200)]

    west = Wall(name=f"{prefix}_West", start_point=XYZ(0, floor_d, 0), end_point=XYZ(0, 0, 0))
    if west_windows is not None:
        west.windows = list(west_windows)
    else:
        west.windows = [WallOpening("window", offset=600,  width=900, z_bottom=900, height=1200),
                        WallOpening("window", offset=1800, width=900, z_bottom=900, height=1200)]

    return [south, east, north, west]

def _make_inner_walls(prefix: str, floor_w: float, floor_d: float) -> list[Wall]:
    """Create internal partition walls with doors."""
    mid_x = Wall(name=f"{prefix}_MidX", start_point=XYZ(floor_w / 2, 0, 0),
                 end_point=XYZ(floor_w / 2, floor_d, 0))
    mid_x.doors = [WallOpening("door", offset=600, width=900, z_bottom=0, height=2100)]

    mid_y = Wall(name=f"{prefix}_MidY", start_point=XYZ(0, floor_d / 2, 0),
                 end_point=XYZ(floor_w, floor_d / 2, 0))
    mid_y.doors = [WallOpening("door", offset=900, width=900, z_bottom=0, height=2100),
                   WallOpening("door", offset=3000, width=900, z_bottom=0, height=2100)]

    return [mid_x, mid_y]

def _make_4_panels(prefix: str, floor_w: float, floor_d: float) -> list[Panel]:
    """Create 4 floor panels (2x2 grid)."""
    hw, hd = floor_w / 2, floor_d / 2
    return [
        Panel(f"{prefix}_A", "floor", [
            (XYZ(0, 0, 0), XYZ(hw, 0, 0)), (XYZ(hw, 0, 0), XYZ(hw, hd, 0)),
            (XYZ(hw, hd, 0), XYZ(0, hd, 0)), (XYZ(0, hd, 0), XYZ(0, 0, 0)),
        ]),
        Panel(f"{prefix}_B", "floor", [
            (XYZ(hw, 0, 0), XYZ(floor_w, 0, 0)), (XYZ(floor_w, 0, 0), XYZ(floor_w, hd, 0)),
            (XYZ(floor_w, hd, 0), XYZ(hw, hd, 0)), (XYZ(hw, hd, 0), XYZ(hw, 0, 0)),
        ]),
        Panel(f"{prefix}_C", "floor", [
            (XYZ(0, hd, 0), XYZ(hw, hd, 0)), (XYZ(hw, hd, 0), XYZ(hw, floor_d, 0)),
            (XYZ(hw, floor_d, 0), XYZ(0, floor_d, 0)), (XYZ(0, floor_d, 0), XYZ(0, hd, 0)),
        ]),
        Panel(f"{prefix}_D", "floor", [
            (XYZ(hw, hd, 0), XYZ(floor_w, hd, 0)), (XYZ(floor_w, hd, 0), XYZ(floor_w, floor_d, 0)),
            (XYZ(floor_w, floor_d, 0), XYZ(hw, floor_d, 0)), (XYZ(hw, floor_d, 0), XYZ(hw, hd, 0)),
        ]),
    ]


def _find_best_riser(fixture_pos: XYZ, main_stack: XYZ, walls: list[Wall],
                     grid_size: float = 300, clearance: float = 150,
                     obstacles: list = None) -> tuple[XYZ, Wall]:
    """Find the riser position on any wall that minimizes total horizontal pipe.

    Cost = manhattan(fixture→riser) + manhattan(riser→main_stack)
    Both perimeter and internal partition walls are considered.
    Points inside floor obstacles are excluded.

    Returns (riser_point, wall).
    """
    best_point, best_wall, best_cost = None, None, float("inf")
    obs = obstacles or []

    for wall in walls:
        sx, sy = wall.start_point.x, wall.start_point.y
        ex, ey = wall.end_point.x, wall.end_point.y
        wall_len = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2)
        if wall_len == 0:
            continue
        dx, dy = (ex - sx) / wall_len, (ey - sy) / wall_len

        blocked = []
        for wo in wall.doors + wall.windows:
            blocked.append((wo.offset - clearance, wo.offset + wo.width + clearance))

        step = int(grid_size)
        for offset in range(step, int(wall_len), step):
            if all(not (lo < offset < hi) for lo, hi in blocked):
                wx = round(sx + dx * offset)
                wy = round(sy + dy * offset)
                # Skip if inside a floor obstacle
                in_obstacle = any(
                    o.min_corner.x <= wx <= o.max_corner.x and
                    o.min_corner.y <= wy <= o.max_corner.y
                    for o in obs
                )
                if in_obstacle:
                    continue
                cost = (abs(fixture_pos.x - wx) + abs(fixture_pos.y - wy)
                        + abs(main_stack.x - wx) + abs(main_stack.y - wy))
                # Tiebreaker: prefer riser closer to fixture (shorter upper-floor pipe)
                dist_to_fixture = abs(fixture_pos.x - wx) + abs(fixture_pos.y - wy)
                if cost < best_cost or (cost == best_cost and dist_to_fixture < best_tie):
                    best_cost = cost
                    best_tie = dist_to_fixture
                    best_point = XYZ(wx, wy, 0)
                    best_wall = wall

    if best_point is None:
        w = walls[0]
        mx = (w.start_point.x + w.end_point.x) / 2
        my = (w.start_point.y + w.end_point.y) / 2
        best_point = XYZ(round(mx), round(my), 0)
        best_wall = w

    return best_point, best_wall


# --- Window-avoidance helpers for vertical riser ---

def _get_blocked_ranges_on_wall(wall: Wall, clearance: float = 150) -> list[tuple[float, float]]:
    """Get blocked coordinate ranges (in world XY) from windows on a wall.
    Returns list of (y_lo, y_hi) for vertical walls or (x_lo, x_hi) for horizontal."""
    sx, sy = wall.start_point.x, wall.start_point.y
    ex, ey = wall.end_point.x, wall.end_point.y
    wall_len = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2)
    if wall_len == 0:
        return []
    dx, dy = (ex - sx) / wall_len, (ey - sy) / wall_len
    ranges = []
    for wo in wall.windows:
        p1x = sx + dx * wo.offset
        p1y = sy + dy * wo.offset
        p2x = sx + dx * (wo.offset + wo.width)
        p2y = sy + dy * (wo.offset + wo.width)
        # Use whichever axis has variation
        if abs(ey - sy) > abs(ex - sx):  # vertical wall (varies in Y)
            ranges.append((min(p1y, p2y) - clearance, max(p1y, p2y) + clearance))
        else:  # horizontal wall (varies in X)
            ranges.append((min(p1x, p2x) - clearance, max(p1x, p2x) + clearance))
    return ranges


def _is_coord_blocked(val: float, blocked: list[tuple[float, float]]) -> bool:
    return any(lo <= val <= hi for lo, hi in blocked)


def _find_clear_coord(val: float, blocked: list[tuple[float, float]],
                      grid_size: float, max_val: float) -> float:
    """Find nearest grid-aligned coordinate that is not blocked."""
    for d in range(1, 50):
        for candidate in [val - d * grid_size, val + d * grid_size]:
            if 0 <= candidate <= max_val and not _is_coord_blocked(candidate, blocked):
                return candidate
    return val


# =============================================================================
# JSON model loader
# =============================================================================

def load_model(json_path: str) -> dict:
    """Load a building model from a JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_xyz(d: dict) -> XYZ:
    return XYZ(d["x"], d["y"], d["z"])


def _parse_wall_opening(d: dict) -> WallOpening:
    return WallOpening("window", offset=d["offset"], width=d["width"],
                       z_bottom=d["z_bottom"], height=d["height"])


WALL_NAME_MAP = {"South": 0, "East": 1, "North": 2, "West": 3}


# =============================================================================
# Tee writer: prints to both stdout and file
# =============================================================================

class TeeWriter:
    """Write output to both stdout and a file simultaneously."""

    def __init__(self, filepath: str):
        self._stdout = sys.stdout
        self._file = open(filepath, "w", encoding="utf-8")

    def write(self, text):
        self._stdout.write(text)
        self._file.write(text)

    def flush(self):
        self._stdout.flush()
        self._file.flush()

    def close(self):
        self._file.close()
        sys.stdout = self._stdout


# =============================================================================
# Core run function (replaces hardcoded demo)
# =============================================================================

def run(model: dict, visualize: bool = True):
    """Run the cross-storey drainage routing from a loaded model dict."""

    # --- Extract building dimensions ---
    bldg = model["building"]
    FLOOR_W = float(bldg["floor_width"])
    FLOOR_D = float(bldg["floor_depth"])
    WALL_H  = float(bldg["wall_height"])
    SLAB_T  = float(bldg["slab_thickness"])
    STOREY_H = WALL_H + SLAB_T
    num_storeys = int(bldg["num_storeys"])

    # --- Routing config ---
    rc = model["routing_config"]
    joist = Joist(name="joist", start_point=XYZ(0, 0, 0), end_point=XYZ(FLOOR_W, 0, 0),
                  width=rc["joist_width"], depth=rc["joist_depth"])
    config = RoutingConfig(
        pipe_slope=rc["pipe_slope"], min_pipe_length=rc["min_pipe_length"],
        grid_size=rc["grid_size"], default_diameter=rc["default_diameter"],
        joist_constraint=JoistConstraint.from_joist(joist, d_top=rc["joist_d_top"],
                                                    d_bottom=rc["joist_d_bottom"]),
    )

    main_stack = _parse_xyz(model["main_stack"])
    vent_stack = _parse_xyz(model["vent_stack"])

    # --- Parse fixtures (group by floor) ---
    fixtures_by_floor = {}  # floor_num -> list of PlumbingFixture
    for fd in model["fixtures"]:
        fix = PlumbingFixture(
            name=fd["name"], fixture_type=fd["type"],
            drain_diameter=fd["drain_diameter"],
            _position=_parse_xyz(fd["position"]),
        )
        fixtures_by_floor.setdefault(fd["floor"], []).append(fix)

    # Use the fixture on the highest floor for cross-storey routing
    top_floor = max(fixtures_by_floor.keys())
    fixture_top = fixtures_by_floor[top_floor][0]

    # --- Parse obstacles (group by floor) ---
    obstacles_by_floor = {}
    for od in model.get("obstacles", []):
        obs = Opening(_parse_xyz(od["min_corner"]), _parse_xyz(od["max_corner"]))
        obstacles_by_floor.setdefault(od["floor"], []).append(obs)

    obstacles_top = obstacles_by_floor.get(top_floor, [])

    # --- Parse wall overrides ---
    wall_overrides = {}  # (floor, wall_name_idx) -> list[WallOpening]
    for wo in model.get("wall_overrides", []):
        idx = WALL_NAME_MAP.get(wo["wall"])
        if idx is not None:
            wall_overrides[(wo["floor"], idx)] = [_parse_wall_opening(w) for w in wo["windows"]]

    # --- Build multi-storey geometry ---
    print(f"\n  Model: {model['name']}")
    print(f"  Building: {FLOOR_W:.0f} x {FLOOR_D:.0f} mm, {num_storeys} storey(s)")
    print(f"  Storeys: {num_storeys}, Wall height: {WALL_H:.0f}mm, Slab: {SLAB_T:.0f}mm")

    storey_walls_all = []
    storey_data_list = []
    for i in range(num_storeys):
        z_base = i * STOREY_H
        prefix = f"L{i + 1}"
        label = f"Level {i + 1}" + (" (Ground)" if i == 0 else "")

        outer = _make_outer_walls(prefix, FLOOR_W, FLOOR_D)
        # Apply wall overrides for this floor
        for wall_idx in range(4):
            key = (i + 1, wall_idx)  # floors are 1-indexed in JSON
            if key in wall_overrides:
                outer[wall_idx].windows = wall_overrides[key]
        inner = _make_inner_walls(prefix, FLOOR_W, FLOOR_D)
        all_walls = outer + inner
        storey_walls_all.append(all_walls)
        panels = _make_4_panels(prefix, FLOOR_W, FLOOR_D)

        floor_num = i + 1
        obstacles = obstacles_by_floor.get(floor_num, [])
        fixtures_vis = fixtures_by_floor.get(floor_num, [])

        storey_data_list.append(StoreyData(
            label=label, z_base=z_base, wall_height=WALL_H, floor_thickness=SLAB_T,
            walls=all_walls, panels=panels, obstacles=obstacles, fixtures=fixtures_vis,
            drain_routes={}, vent_routes={}, couplings=[],
            main_stack=main_stack, vent_stack=vent_stack,
        ))

    # --- Single-storey: just do horizontal routing ---
    if num_storeys == 1:
        pathfinder = HeuristicPathfinder(config, obstacles=obstacles_top)
        z_slab_top = SLAB_T
        path = pathfinder.find_path(
            XYZ(fixture_top.position.x, fixture_top.position.y, 0),
            XYZ(main_stack.x, main_stack.y, 0),
        )
        segments = []
        for j in range(len(path) - 1):
            s, e = path[j], path[j + 1]
            segments.append(Pipe(
                start_point=XYZ(s.x, s.y, z_slab_top + s.z),
                end_point=XYZ(e.x, e.y, z_slab_top + e.z),
                size=fixture_top.drain_diameter, system_type=SystemType.DRAIN,
            ))
        total_len = sum(seg.length for seg in segments)
        print("=" * 60)
        print("  Single-Storey Pipe Route")
        print("=" * 60)
        print(f"  Fixture: L1 at ({fixture_top.position.x}, {fixture_top.position.y})")
        print(f"  Stack:   L1 at ({main_stack.x}, {main_stack.y})")
        print(f"  Segments: {len(segments)}")
        print(f"  Total length: {total_len:.0f}mm")
        print("=" * 60)

        route_label = f"L1 drain ({fixture_top.name})"
        global_routes = {route_label: segments}
        if visualize:
            visualize_multi_storey(storey_data_list, global_routes=global_routes)
        return storey_data_list

    # --- Multi-storey cross-storey routing ---
    # Find riser on any wall that minimizes total horizontal pipe
    top_all_walls = storey_walls_all[top_floor - 1]
    riser_xy, riser_wall = _find_best_riser(
        fixture_top.position, main_stack, top_all_walls, grid_size=config.grid_size,
        obstacles=obstacles_top,
    )
    print(f"  Riser wall: {riser_wall.name}")
    print(f"  Riser position: ({riser_xy.x}, {riser_xy.y})  (closest to fixture)")

    is_vertical_wall = abs(riser_wall.end_point.x - riser_wall.start_point.x) < 1

    # --- 1) Horizontal on top floor: fixture → riser ---
    pathfinder_top = HeuristicPathfinder(config, obstacles=obstacles_top)
    z_top_slab_top = (top_floor - 1) * STOREY_H + SLAB_T

    path_top = pathfinder_top.find_path(
        XYZ(fixture_top.position.x, fixture_top.position.y, 0),
        XYZ(riser_xy.x, riser_xy.y, 0),
    )
    segments_top = []
    for j in range(len(path_top) - 1):
        s, e = path_top[j], path_top[j + 1]
        segments_top.append(Pipe(
            start_point=XYZ(s.x, s.y, z_top_slab_top + s.z),
            end_point=XYZ(e.x, e.y, z_top_slab_top + e.z),
            size=fixture_top.drain_diameter, system_type=SystemType.DRAIN,
        ))

    # --- 2) Vertical riser with window avoidance (zigzag) ---
    riser_x, riser_y = riser_xy.x, riser_xy.y
    current_z = segments_top[-1].end_point.z if segments_top else z_top_slab_top
    segments_vertical = []
    n_detours = 0

    for floor_idx in range(top_floor - 2, -1, -1):
        target_z = floor_idx * STOREY_H + SLAB_T
        floor_walls = storey_walls_all[floor_idx]
        matching_wall = None
        for w in floor_walls:
            if is_vertical_wall:
                if abs(w.start_point.x - riser_x) < 1 and abs(w.end_point.x - riser_x) < 1:
                    matching_wall = w
                    break
            else:
                if abs(w.start_point.y - riser_y) < 1 and abs(w.end_point.y - riser_y) < 1:
                    matching_wall = w
                    break

        if matching_wall:
            blocked = _get_blocked_ranges_on_wall(matching_wall)
            check_val = riser_y if is_vertical_wall else riser_x
            max_val = FLOOR_D if is_vertical_wall else FLOOR_W
            if _is_coord_blocked(check_val, blocked):
                new_val = _find_clear_coord(check_val, blocked, config.grid_size, max_val)
                label = f"L{floor_idx + 1}"
                print(f"  ⚠ Window at {label} ({matching_wall.name}): "
                      f"riser shifts {'y' if is_vertical_wall else 'x'}="
                      f"{check_val:.0f} → {new_val:.0f}")
                if is_vertical_wall:
                    segments_vertical.append(Pipe(
                        start_point=XYZ(riser_x, riser_y, current_z),
                        end_point=XYZ(riser_x, new_val, current_z),
                        size=fixture_top.drain_diameter, system_type=SystemType.DRAIN,
                    ))
                    riser_y = new_val
                else:
                    segments_vertical.append(Pipe(
                        start_point=XYZ(riser_x, riser_y, current_z),
                        end_point=XYZ(new_val, riser_y, current_z),
                        size=fixture_top.drain_diameter, system_type=SystemType.DRAIN,
                    ))
                    riser_x = new_val
                n_detours += 1

        segments_vertical.append(Pipe(
            start_point=XYZ(riser_x, riser_y, current_z),
            end_point=XYZ(riser_x, riser_y, target_z),
            size=fixture_top.drain_diameter, system_type=SystemType.DRAIN,
        ))
        current_z = target_z

    # --- 3) Horizontal on L1: riser landing → main stack ---
    pathfinder_L1 = HeuristicPathfinder(config)
    z_L1_slab_top = SLAB_T
    path_L1 = pathfinder_L1.find_path(
        XYZ(riser_x, riser_y, 0),
        XYZ(main_stack.x, main_stack.y, 0),
    )
    segments_L1 = []
    for j in range(len(path_L1) - 1):
        s, e = path_L1[j], path_L1[j + 1]
        segments_L1.append(Pipe(
            start_point=XYZ(s.x, s.y, z_L1_slab_top + s.z),
            end_point=XYZ(e.x, e.y, z_L1_slab_top + e.z),
            size=fixture_top.drain_diameter, system_type=SystemType.DRAIN,
        ))

    all_segments = segments_top + segments_vertical + segments_L1
    total_len = sum(seg.length for seg in all_segments)
    horiz_top = sum(seg.horizontal_length for seg in segments_top)
    horiz_L1 = sum(seg.horizontal_length for seg in segments_L1)

    print("=" * 60)
    print("  Cross-Storey Pipe Route (optimized riser)")
    print("=" * 60)
    print(f"  Fixture:     L{top_floor} at ({fixture_top.position.x}, {fixture_top.position.y})")
    print(f"  Riser:       {riser_wall.name} at ({riser_xy.x}, {riser_xy.y})")
    print(f"  Riser exit:  ({riser_x}, {riser_y})")
    print(f"  Stack:       L1 at ({main_stack.x}, {main_stack.y})")
    print(f"  Horizontal L{top_floor}: {horiz_top:.0f}mm ({len(segments_top)} segs)")
    print(f"  Vertical:      {len(segments_vertical)} segs ({n_detours} window detour(s))")
    print(f"  Horizontal L1: {horiz_L1:.0f}mm ({len(segments_L1)} segs)")
    print(f"  Total length:  {total_len:.0f}mm")
    print("=" * 60)

    if segments_vertical:
        print("\n  Riser path:")
        for j, seg in enumerate(segments_vertical):
            sp, ep = seg.start_point, seg.end_point
            kind = "horizontal shift" if abs(sp.z - ep.z) < 1 else "vertical drop"
            if j == 0:
                print(f"    start: ({sp.x:.0f}, {sp.y:.0f}, z={sp.z:.0f})")
            print(f"    → ({ep.x:.0f}, {ep.y:.0f}, z={ep.z:.0f})  ({kind})")

    route_label = f"L{top_floor}→L1 drain (optimized)"
    global_routes = {route_label: all_segments}
    if visualize:
        visualize_multi_storey(storey_data_list, global_routes=global_routes)

    return storey_data_list


# =============================================================================
# CLI
# =============================================================================

def _get_model_list(input_dir: Path) -> list[Path]:
    """Return sorted list of .json model files in input_dir."""
    return sorted(input_dir.glob("*.json"))


def list_available_models(input_dir: Path):
    """List all .json model files in input_dir with numbered indices."""
    models = _get_model_list(input_dir)
    if not models:
        print(f"  No model files found in {input_dir}")
        return
    print(f"\n  Available models in {input_dir}:")
    print("  " + "-" * 55)
    for i, mp in enumerate(models, start=1):
        with open(mp, "r", encoding="utf-8") as f:
            data = json.load(f)
        name = data.get("name", mp.stem)
        desc = data.get("description", "")
        bldg = data.get("building", {})
        storeys = bldg.get("num_storeys", "?")
        print(f"  [{i}]  {mp.name:<32s} {storeys}F  {name}")
        if desc:
            print(f"       {desc[:75]}")
    print(f"\n  Usage: python main.py --model <number>")
    print()


def parse_args():
    parser = argparse.ArgumentParser(
        description="PRBD Automated Drainage Design System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\nExamples:
  python main.py                          # run default model (model 1)
  python main.py --model 2                # run model #2
  python main.py --model 3 --no-viz       # run model #3 without 3D visualization
  python main.py --list-models            # show available models with indices
  python main.py --run-all --no-viz       # run all models sequentially
""",
    )
    parser.add_argument("--model", "-m", type=int, default=None,
                        help="Model number to run (see --list-models for indices)")
    parser.add_argument("--input-dir", type=str, default=str(DEFAULT_INPUT_DIR),
                        help=f"Directory containing model JSON files (default: {DEFAULT_INPUT_DIR})")
    parser.add_argument("--output-dir", "-o", type=str, default=None,
                        help="Directory to save output logs (default: print to terminal only)")
    parser.add_argument("--no-viz", action="store_true",
                        help="Skip 3D visualization")
    parser.add_argument("--list-models", action="store_true",
                        help="List available model files in input_dir and exit")
    parser.add_argument("--run-all", action="store_true",
                        help="Run all models in input_dir sequentially")
    return parser.parse_args()


def main():
    args = parse_args()
    input_dir = Path(args.input_dir)

    if args.list_models:
        list_available_models(input_dir)
        return

    all_models = _get_model_list(input_dir)
    if not all_models:
        print(f"No model files found in {input_dir}")
        return

    # Collect model files to run
    if args.run_all:
        model_files = all_models
    elif args.model is not None:
        idx = args.model
        if idx < 1 or idx > len(all_models):
            print(f"Error: --model {idx} is out of range. Available: 1..{len(all_models)}")
            print("Use --list-models to see available models.")
            return
        model_files = [all_models[idx - 1]]
    else:
        # Default: run model #1 (first in sorted order)
        model_files = [all_models[0]]

    # Prepare output directory
    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    visualize = not args.no_viz

    for model_path in model_files:
        if not model_path.exists():
            print(f"Error: file not found: {model_path}")
            continue

        model = load_model(str(model_path))
        model_name = model_path.stem

        # Set up output tee if output_dir specified
        tee = None
        if output_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = output_dir / f"{model_name}_{timestamp}.txt"
            tee = TeeWriter(str(out_file))
            sys.stdout = tee

        try:
            print(f"\n{'='*60}")
            print(f"  Running model: {model_path.name}")
            print(f"{'='*60}")
            run(model, visualize=visualize)
        finally:
            if tee:
                tee.close()

        if output_dir:
            print(f"  Output saved to: {out_file}")


if __name__ == "__main__":
    main()
