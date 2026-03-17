"""
Algorithm 2: Panelization Algorithm.

Segment the drainage pipe network at panel boundaries,
insert couplings, and generate BOM per panel.
"""

from typing import Optional

from models import XYZ, Panel, Pipe


class PanelizationAlgorithm:
    """
    Panelization: segment the drainage pipe network at panel boundaries.

    Steps:
    1. Build database of panel boundary equations and pipe centerline equations
    2. Compute intersections between boundaries and pipe segments
    3. Cut pipes at intersections and insert couplings
    4. Repeat until all panels are processed
    """

    @staticmethod
    def _line_segment_intersection_2d(
        p1: XYZ, p2: XYZ,
        p3: XYZ, p4: XYZ,
    ) -> Optional[XYZ]:
        """Find intersection of two 2D line segments (p1-p2) and (p3-p4)."""
        x1, y1 = p1.x, p1.y
        x2, y2 = p2.x, p2.y
        x3, y3 = p3.x, p3.y
        x4, y4 = p4.x, p4.y

        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-10:
            return None

        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

        EPS = 1e-9
        if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS:
            t = max(0.0, min(1.0, t))
            ix = x1 + t * (x2 - x1)
            iy = y1 + t * (y2 - y1)
            iz = p1.z + t * (p2.z - p1.z)
            return XYZ(ix, iy, iz)
        return None

    def panelize(
        self, pipe_segments: list[Pipe], panels: list[Panel]
    ) -> tuple[list[Pipe], list[XYZ]]:
        """
        Cut pipe segments at panel boundaries.

        Returns:
            - List of new (smaller) pipe segments with panel_id assigned
            - List of coupling positions (intersection points)
        """
        coupling_positions = []
        result_segments = list(pipe_segments)

        for panel in panels:
            boundary_eqs = panel.get_boundary_equations()
            new_segments = []

            for seg in result_segments:
                cuts = []
                for _a, _b, _c, bnd_start, bnd_end in boundary_eqs:
                    intersection = self._line_segment_intersection_2d(
                        seg.start_point, seg.end_point, bnd_start, bnd_end
                    )
                    if intersection is not None:
                        dist_start = seg.start_point.euclidean_distance(intersection)
                        dist_end = seg.end_point.euclidean_distance(intersection)
                        if dist_start > 1.0 and dist_end > 1.0:
                            cuts.append(intersection)

                if not cuts:
                    new_segments.append(seg)
                    continue

                cuts.sort(key=lambda p: seg.start_point.euclidean_distance(p))

                prev = seg.start_point
                for cut_point in cuts:
                    new_segments.append(Pipe(
                        start_point=prev, end_point=cut_point,
                        size=seg.size, system_type=seg.system_type,
                    ))
                    coupling_positions.append(cut_point)
                    prev = cut_point
                new_segments.append(Pipe(
                    start_point=prev, end_point=seg.end_point,
                    size=seg.size, system_type=seg.system_type,
                ))

            result_segments = new_segments

        result_segments = self._assign_panel_ids(result_segments, panels)
        return result_segments, coupling_positions

    def _assign_panel_ids(
        self, segments: list[Pipe], panels: list[Panel]
    ) -> list[Pipe]:
        """Assign each segment to the panel that contains its midpoint."""
        for seg in segments:
            mid = XYZ(
                (seg.start_point.x + seg.end_point.x) / 2,
                (seg.start_point.y + seg.end_point.y) / 2,
                (seg.start_point.z + seg.end_point.z) / 2,
            )
            for panel in panels:
                if self._point_in_panel(mid, panel):
                    seg.panel_id = panel.panel_id
                    break
        return segments

    @staticmethod
    def _point_in_panel(point: XYZ, panel: Panel) -> bool:
        """Check if point is inside panel boundary using ray casting."""
        n = len(panel.boundaries)
        if n < 3:
            return False

        vertices = [b[0] for b in panel.boundaries]
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = vertices[i].x, vertices[i].y
            xj, yj = vertices[j].x, vertices[j].y
            if ((yi > point.y) != (yj > point.y)) and \
               (point.x < (xj - xi) * (point.y - yi) / (yj - yi + 1e-15) + xi):
                inside = not inside
            j = i
        return inside

    def generate_bom(
        self, segments: list[Pipe]
    ) -> dict[str, list[dict]]:
        """
        Generate Bill of Materials grouped by panel.
        Returns dict: panel_id -> list of {size, length, system_type}
        """
        bom = {}
        for seg in segments:
            pid = seg.panel_id or "unassigned"
            if pid not in bom:
                bom[pid] = []
            bom[pid].append({
                "size": seg.size,
                "length": round(seg.length, 1),
                "system_type": seg.system_type.value,
            })
        return bom
        return bom
