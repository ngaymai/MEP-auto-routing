"""
Algorithm 1: Heuristic Pathfinding Algorithm (A* + Dijkstra hybrid).

Fitness function: f(n) = g(n) + h(n) + t(n)
Constraints: joist penetration, floor opening clearance.
"""

import heapq
from typing import Optional

from models import XYZ, PlumbingFixture, Opening, Pipe, SystemType, RoutingConfig

# Aliases for readability
Point3D = XYZ


class HeuristicPathfinder:
    """
    Heuristic pathfinding combining A* greedy search and Dijkstra.

    Fitness function: f(n) = g(n) + h(n) + t(n)
    - g(n): pipe length from start S to node n
    - h(n): Manhattan distance from node n to terminal T
    - t(n): number of turns from start S to node n

    Constraints:
    - Joist penetration: g(n) <= (H_joist - d_top - d_bottom) / S_slope
    - Floor opening: D(n) >= l_min
    """

    DIRECTIONS = [
        (1, 0),   # +X
        (-1, 0),  # -X
        (0, 1),   # +Y
        (0, -1),  # -Y
    ]

    def __init__(self, config: RoutingConfig, obstacles: list[Opening] = None):
        self.config = config
        self.obstacles = obstacles or []

    def _check_joist_constraint(self, g_cost: float) -> bool:
        if self.config.joist_constraint is None:
            return True
        max_depth = self.config.joist_constraint.max_penetration_depth
        max_horizontal = max_depth / self.config.pipe_slope if self.config.pipe_slope > 0 else float('inf')
        return g_cost <= max_horizontal

    def _check_floor_opening_constraint(self, point: Point3D) -> bool:
        for obstacle in self.obstacles:
            if obstacle.distance_to(point) < self.config.min_pipe_length:
                return False
        return True

    def _is_valid(self, point: Point3D, g_cost: float) -> bool:
        if not self._check_joist_constraint(g_cost):
            return False
        if not self._check_floor_opening_constraint(point):
            return False
        return True

    def _count_turn(self, prev_dir: Optional[tuple], new_dir: tuple) -> int:
        if prev_dir is None:
            return 0
        return 0 if prev_dir == new_dir else 1

    def find_path(self, start: XYZ, terminal: XYZ) -> list[XYZ]:
        """
        Find optimal pipe path from fixture drain (start) to main stack (terminal).
        Returns list of XYZ waypoints forming the pipe route.
        """
        grid = self.config.grid_size

        slope = self.config.pipe_slope

        def to_grid(p: XYZ) -> tuple:
            return (round(p.x / grid), round(p.y / grid))

        def from_grid(gx: int, gy: int, g_cost: float = 0.0) -> XYZ:
            """Create a point with z dropping by slope * horizontal distance."""
            return XYZ(gx * grid, gy * grid, start.z - g_cost * slope)

        start_grid = to_grid(start)
        terminal_grid = to_grid(terminal)

        counter = 0
        open_set = []
        start_node = from_grid(*start_grid, 0.0)
        h0 = start_node.manhattan_distance(from_grid(*terminal_grid, 0.0))
        heapq.heappush(open_set, (h0, counter, start_grid[0], start_grid[1], 0.0, 0, None, [start]))

        visited = {}

        while open_set:
            f_score, _, gx, gy, g_cost, turns, prev_dir, path = heapq.heappop(open_set)
            grid_pos = (gx, gy)

            if grid_pos == terminal_grid:
                return path + [terminal]

            if grid_pos in visited and visited[grid_pos] <= f_score:
                continue
            visited[grid_pos] = f_score

            for dx, dy in self.DIRECTIONS:
                nx, ny = gx + dx, gy + dy
                new_g = g_cost + grid
                new_pos = from_grid(nx, ny, new_g)

                if not self._is_valid(new_pos, new_g):
                    continue

                new_dir = (dx, dy)
                new_turns = turns + self._count_turn(prev_dir, new_dir)

                h_n = new_pos.manhattan_distance(from_grid(*terminal_grid, 0.0))
                f_n = new_g + h_n + new_turns * grid

                neighbor_grid = (nx, ny)
                if neighbor_grid in visited and visited[neighbor_grid] <= f_n:
                    continue

                counter += 1
                heapq.heappush(open_set, (f_n, counter, nx, ny, new_g, new_turns, new_dir, path + [new_pos]))

        return []

    def route_fixture(self, fixture: PlumbingFixture, terminal: XYZ) -> list[Pipe]:
        """Route a single fixture to the main stack, return pipe segments."""
        path = self.find_path(fixture.position, terminal)
        if not path:
            return []

        segments = []
        for i in range(len(path) - 1):
            segments.append(Pipe(
                start_point=path[i],
                end_point=path[i + 1],
                size=self.config.default_diameter,
                system_type=SystemType.DRAIN,
            ))
        return segments

    def route_all_fixtures(self, fixtures: list[PlumbingFixture], terminal: XYZ) -> dict[str, list[Pipe]]:
        """Route all fixtures to the main drainage stack."""
        routes = {}
        for fixture in fixtures:
            routes[fixture.name] = self.route_fixture(fixture, terminal)
        return routes
