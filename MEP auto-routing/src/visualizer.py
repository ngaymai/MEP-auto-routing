"""
3D Visualization for the PRBD drainage system (multi-storey support).
Uses matplotlib to render walls, floor slabs, openings, fixtures, and pipe paths.
"""

import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import matplotlib.colors as mcolors

import math
from models import XYZ, PlumbingFixture, Opening, Panel, Wall, Floor, Pipe, WallOpening


# Distinct colors for drain routes
ROUTE_COLORS = list(mcolors.TABLEAU_COLORS.values())


# =============================================================================
# Per-storey data bundle
# =============================================================================

class StoreyData:
    """All geometry for a single storey."""

    def __init__(
        self,
        label: str,
        z_base: float,
        wall_height: float,
        floor_thickness: float,
        walls: list[Wall] = None,
        panels: list[Panel] = None,
        obstacles: list[Opening] = None,
        fixtures: list[PlumbingFixture] = None,
        drain_routes: dict[str, list[Pipe]] = None,
        vent_routes: dict[str, list[Pipe]] = None,
        couplings: list[XYZ] = None,
        main_stack: XYZ = None,
        vent_stack: XYZ = None,
    ):
        self.label = label
        self.z_base = z_base
        self.wall_height = wall_height
        self.floor_thickness = floor_thickness
        self.walls = walls or []
        self.panels = panels or []
        self.obstacles = obstacles or []
        self.fixtures = fixtures or []
        self.drain_routes = drain_routes or {}
        self.vent_routes = vent_routes or {}
        self.couplings = couplings or []
        self.main_stack = main_stack
        self.vent_stack = vent_stack


# =============================================================================
# Main visualize function (multi-storey)
# =============================================================================

def visualize_multi_storey(storeys: list[StoreyData], global_routes: dict[str, list[Pipe]] = None):
    """Render a multi-storey 3D scene.

    Args:
        storeys: per-storey geometry bundles.
        global_routes: cross-storey pipe routes with absolute Z (no offset applied).
    """
    fig = plt.figure(figsize=(15, 10))
    ax = fig.add_subplot(111, projection="3d")

    all_max_z = 0
    route_idx = 0

    for storey in storeys:
        zb = storey.z_base
        ft = storey.floor_thickness
        wh = storey.wall_height
        slab_top = zb + ft
        storey_top = slab_top + (wh - ft)
        if storey_top > all_max_z:
            all_max_z = storey_top

        # --- Floor slab ---
        _draw_floor_box(ax, storey.panels, zb, ft)

        # --- Walls (sit on top of the slab) ---
        for wall in storey.walls:
            _draw_wall(ax, wall, slab_top, wh - ft)

        # --- Panel grid ---
        for panel in storey.panels:
            verts = [(s.x, s.y, slab_top) for s, _ in panel.boundaries]
            poly = Poly3DCollection([verts], alpha=0.06, facecolor="lightblue",
                                    edgecolor="steelblue", linewidth=0.5)
            ax.add_collection3d(poly)
            cx_p = sum(v[0] for v in verts) / len(verts)
            cy_p = sum(v[1] for v in verts) / len(verts)
            ax.text(cx_p, cy_p, slab_top + 15, panel.panel_id,
                    fontsize=6, color="steelblue", ha="center", va="center")

        # Panel boundary dashes
        drawn = set()
        for panel in storey.panels:
            for s, e in panel.boundaries:
                edge = (min(s.x, e.x), min(s.y, e.y), max(s.x, e.x), max(s.y, e.y))
                if edge not in drawn:
                    ax.plot([s.x, e.x], [s.y, e.y], [slab_top, slab_top],
                            color="steelblue", linewidth=0.4, linestyle="--")
                    drawn.add(edge)

        # --- Openings ---
        for obs in storey.obstacles:
            _draw_opening(ax, obs, zb, ft)

        # --- Fixtures ---
        for fixture in storey.fixtures:
            p = fixture.position
            ax.scatter(p.x, p.y, slab_top, s=80, c="green", marker="^",
                       zorder=5, depthshade=False)
            ax.text(p.x, p.y, slab_top + 100, fixture.name, fontsize=7,
                    color="darkgreen", ha="center", fontweight="bold")

        # --- Main stack / vent stack ---
        if storey.main_stack:
            ms = storey.main_stack
            ax.scatter(ms.x, ms.y, slab_top, s=120, c="black", marker="s",
                       zorder=5, depthshade=False)

        if storey.vent_stack:
            vs = storey.vent_stack
            ax.scatter(vs.x, vs.y, vs.z + slab_top, s=100, c="purple",
                       marker="D", zorder=5, depthshade=False)

        # --- Drain routes ---
        for name, segments in storey.drain_routes.items():
            color = ROUTE_COLORS[route_idx % len(ROUTE_COLORS)]
            xs, ys, zs = _segments_to_coords(segments, z_offset=slab_top)
            ax.plot(xs, ys, zs, color=color, linewidth=2.5,
                    label=f"{storey.label} drain:{name}", zorder=4)
            ax.scatter(xs, ys, zs, c=color, s=15, zorder=5, depthshade=False)
            route_idx += 1

        # --- Vent routes ---
        for name, segments in storey.vent_routes.items():
            color = ROUTE_COLORS[route_idx % len(ROUTE_COLORS)]
            xs, ys, zs = _segments_to_coords(segments, z_offset=slab_top)
            ax.plot(xs, ys, zs, color=color, linewidth=1.0, linestyle="--",
                    alpha=0.5, label=f"{storey.label} vent:{name}", zorder=3)
            route_idx += 1

        # --- Couplings ---
        if storey.couplings:
            cx = [c.x for c in storey.couplings]
            cy = [c.y for c in storey.couplings]
            cz = [c.z + slab_top for c in storey.couplings]
            ax.scatter(cx, cy, cz, c="red", s=35, marker="x", linewidths=2,
                       zorder=6, depthshade=False)

        # --- Storey label ---
        ax.text(-200, -200, zb + wh / 2, storey.label,
                fontsize=10, color="gray", fontweight="bold", ha="right")

    # --- Main stack vertical line (full height) ---
    if storeys and storeys[0].main_stack:
        ms = storeys[0].main_stack
        ax.plot([ms.x, ms.x], [ms.y, ms.y], [0, all_max_z],
                color="black", linewidth=2, linestyle=":", label="Main Stack")
    if storeys and storeys[0].vent_stack:
        vs = storeys[0].vent_stack
        ax.plot([vs.x, vs.x], [vs.y, vs.y], [0, all_max_z],
                color="purple", linewidth=1.5, linestyle=":", label="Vent Stack")

    # --- Global cross-storey routes (absolute Z, no offset) ---
    if global_routes:
        for name, segments in global_routes.items():
            color = ROUTE_COLORS[route_idx % len(ROUTE_COLORS)]
            xs, ys, zs = _segments_to_coords(segments, z_offset=0)
            ax.plot(xs, ys, zs, color=color, linewidth=3.0,
                    label=name, zorder=6)
            ax.scatter(xs, ys, zs, c=color, s=25, zorder=7, depthshade=False)
            route_idx += 1

    # --- Axis ---
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    ax.set_title("PRBD Drainage System - Multi-Storey 3D View", fontsize=13, fontweight="bold")

    handles, labels = ax.get_legend_handles_labels()
    if handles:
        # Limit legend entries to avoid clutter
        max_legend = 15
        ax.legend(handles[:max_legend], labels[:max_legend],
                  loc="upper left", fontsize=6, framealpha=0.8)

    ax.set_box_aspect([1, 1, 1.2])
    plt.tight_layout()
    plt.show()


# =============================================================================
# Single-storey convenience wrapper (backward compatible)
# =============================================================================

def visualize(
    panels: list[Panel],
    obstacles: list[Opening],
    fixtures: list[PlumbingFixture],
    main_stack: XYZ,
    vent_stack: XYZ,
    drain_routes: dict[str, list[Pipe]],
    vent_routes: dict[str, list[Pipe]],
    panelized_segments: list[Pipe] = None,
    couplings: list[XYZ] = None,
    walls: list[Wall] = None,
    floor_slab: Floor = None,
    wall_height: float = 2700.0,
    floor_thickness: float = 200.0,
):
    """Single-storey visualization (backward compatible)."""
    storey = StoreyData(
        label="Level 1",
        z_base=0,
        wall_height=wall_height,
        floor_thickness=floor_thickness,
        walls=walls or [],
        panels=panels,
        obstacles=obstacles,
        fixtures=fixtures,
        drain_routes=drain_routes,
        vent_routes=vent_routes,
        couplings=couplings or [],
        main_stack=main_stack,
        vent_stack=vent_stack,
    )
    visualize_multi_storey([storey])


# =========================================================================
# Drawing helpers
# =========================================================================

def _draw_wall(ax, wall: Wall, z_base: float, height: float):
    """Draw a wall as a vertical rectangular plane with visible fill."""
    if wall.start_point is None or wall.end_point is None:
        return

    sx, sy = wall.start_point.x, wall.start_point.y
    ex, ey = wall.end_point.x, wall.end_point.y
    z0, z1 = z_base, z_base + height

    verts = [(sx, sy, z0), (ex, ey, z0), (ex, ey, z1), (sx, sy, z1)]
    poly = Poly3DCollection([verts], alpha=0.18, facecolor="moccasin",
                            edgecolor="sienna", linewidth=1.2)
    ax.add_collection3d(poly)

    mx, my = (sx + ex) / 2, (sy + ey) / 2
    ax.text(mx, my, z1 + 50, wall.name, fontsize=5, color="sienna", ha="center")

    # --- Draw door / window openings on this wall ---
    wall_len = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2)
    if wall_len == 0:
        return
    dx, dy = (ex - sx) / wall_len, (ey - sy) / wall_len

    for wo in (wall.doors + wall.windows):
        if not isinstance(wo, WallOpening):
            continue
        color = "saddlebrown" if wo.opening_type == "door" else "deepskyblue"
        edge_c = "maroon" if wo.opening_type == "door" else "steelblue"
        a = wo.z_bottom + z0  # absolute z bottom
        b_z = a + wo.height   # absolute z top
        x0o = sx + dx * wo.offset
        y0o = sy + dy * wo.offset
        x1o = sx + dx * (wo.offset + wo.width)
        y1o = sy + dy * (wo.offset + wo.width)
        verts_o = [(x0o, y0o, a), (x1o, y1o, a), (x1o, y1o, b_z), (x0o, y0o, b_z)]
        poly_o = Poly3DCollection([verts_o], alpha=0.35, facecolor=color,
                                   edgecolor=edge_c, linewidth=1.4)
        ax.add_collection3d(poly_o)


def _draw_floor_box(ax, panels: list[Panel], z_base: float, thickness: float):
    """Draw floor slab as a box derived from panel extents."""
    all_x, all_y = [], []
    for panel in panels:
        for s, _ in panel.boundaries:
            all_x.append(s.x)
            all_y.append(s.y)
    if not all_x:
        return

    x0, x1 = min(all_x), max(all_x)
    y0, y1 = min(all_y), max(all_y)
    zt = z_base + thickness

    top = [(x0, y0, zt), (x1, y0, zt), (x1, y1, zt), (x0, y1, zt)]
    bot = [(x0, y0, z_base), (x1, y0, z_base), (x1, y1, z_base), (x0, y1, z_base)]

    ax.add_collection3d(Poly3DCollection([top], alpha=0.45, facecolor="#B0B0B0",
                                          edgecolor="#555555", linewidth=1.5))
    ax.add_collection3d(Poly3DCollection([bot], alpha=0.35, facecolor="#A0A0A0",
                                          edgecolor="#555555", linewidth=1.0))
    for i in range(4):
        j = (i + 1) % 4
        side = [bot[i], bot[j], top[j], top[i]]
        ax.add_collection3d(Poly3DCollection([side], alpha=0.30, facecolor="#C0C0C0",
                                              edgecolor="#666666", linewidth=0.8))


def _draw_opening(ax, obs: Opening, z_base: float, thickness: float):
    """Draw opening as a red hole punched through the floor slab."""
    x0, y0 = obs.min_corner.x, obs.min_corner.y
    x1, y1 = obs.max_corner.x, obs.max_corner.y
    zt = z_base + thickness

    top = [(x0, y0, zt), (x1, y0, zt), (x1, y1, zt), (x0, y1, zt)]
    ax.add_collection3d(Poly3DCollection([top], alpha=0.3, facecolor="salmon",
                                          edgecolor="red", linewidth=1.2))
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for i in range(4):
        j = (i + 1) % 4
        side = [(corners[i][0], corners[i][1], z_base),
                (corners[j][0], corners[j][1], z_base),
                (corners[j][0], corners[j][1], zt),
                (corners[i][0], corners[i][1], zt)]
        ax.add_collection3d(Poly3DCollection([side], alpha=0.18, facecolor="salmon",
                                              edgecolor="red", linewidth=0.6))
    ax.text((x0 + x1) / 2, (y0 + y1) / 2, zt + 15,
            "Opening", fontsize=5, color="red", ha="center")


def _segments_to_coords(segments: list[Pipe], z_offset: float = 0) -> tuple[list, list, list]:
    """Extract ordered (x, y, z) coordinate lists from pipe segments."""
    if not segments:
        return [], [], []
    xs = [segments[0].start_point.x]
    ys = [segments[0].start_point.y]
    zs = [segments[0].start_point.z + z_offset]
    for seg in segments:
        xs.append(seg.end_point.x)
        ys.append(seg.end_point.y)
        zs.append(seg.end_point.z + z_offset)
    return xs, ys, zs
    return xs, ys, zs
