"""
Scenario-based Vent Pipe Design (3 scenarios).

1. Individual branch vent for each fixture
2. Single common vent for all fixtures
3. Shared sink vent for other fixtures
"""

from enum import Enum

from models import XYZ, PlumbingFixture, Pipe, SystemType, RoutingConfig
from pathfinding import HeuristicPathfinder

# Alias for readability
Point3D = XYZ


class VentScenario(Enum):
    INDIVIDUAL = 1
    SINGLE_COMMON = 2
    SHARED_SINK = 3


class VentPipeDesigner:
    """Scenario-based vent pipe design with 3 scenarios."""

    def __init__(self, vent_stack_position: XYZ, config: RoutingConfig):
        self.vent_stack_position = vent_stack_position
        self.config = config
        self.pathfinder = HeuristicPathfinder(config)

    def design_vents(self, fixtures: list[PlumbingFixture], scenario: VentScenario) -> dict[str, list[Pipe]]:
        if scenario == VentScenario.INDIVIDUAL:
            return self._individual_vents(fixtures)
        elif scenario == VentScenario.SINGLE_COMMON:
            return self._single_common_vent(fixtures)
        elif scenario == VentScenario.SHARED_SINK:
            return self._shared_sink_vent(fixtures)
        else:
            raise ValueError(f"Unknown vent scenario: {scenario}")

    def _individual_vents(self, fixtures: list[PlumbingFixture]) -> dict[str, list[Pipe]]:
        """Scenario 1: Each fixture gets its own vent pipe to the vent stack."""
        vent_routes = {}
        for fixture in fixtures:
            vent_start = XYZ(fixture.position.x, fixture.position.y, fixture.position.z + 300)
            path = self.pathfinder.find_path(vent_start, self.vent_stack_position)
            segments = [Pipe(
                start_point=fixture.position, end_point=vent_start,
                size=50.0, system_type=SystemType.VENT,
            )]
            for i in range(len(path) - 1):
                segments.append(Pipe(
                    start_point=path[i], end_point=path[i + 1],
                    size=50.0, system_type=SystemType.VENT,
                ))
            vent_routes[f"vent_{fixture.name}"] = segments
        return vent_routes

    def _single_common_vent(self, fixtures: list[PlumbingFixture]) -> dict[str, list[Pipe]]:
        """Scenario 2: All fixtures share a single common vent."""
        if not fixtures:
            return {}

        cx = sum(f.position.x for f in fixtures) / len(fixtures)
        cy = sum(f.position.y for f in fixtures) / len(fixtures)
        cz = fixtures[0].position.z
        common_point = XYZ(cx, cy, cz + 300)
        segments = []

        for fixture in fixtures:
            vent_start = XYZ(fixture.position.x, fixture.position.y, fixture.position.z + 300)
            segments.append(Pipe(
                start_point=fixture.position, end_point=vent_start,
                size=50.0, system_type=SystemType.VENT,
            ))
            segments.append(Pipe(
                start_point=vent_start, end_point=common_point,
                size=50.0, system_type=SystemType.VENT,
            ))

        path = self.pathfinder.find_path(common_point, self.vent_stack_position)
        for i in range(len(path) - 1):
            segments.append(Pipe(
                start_point=path[i], end_point=path[i + 1],
                size=75.0, system_type=SystemType.VENT,
            ))

        return {"common_vent": segments}

    def _shared_sink_vent(self, fixtures: list[PlumbingFixture]) -> dict[str, list[Pipe]]:
        """Scenario 3: Sink vent shared with nearby fixtures."""
        sinks = [f for f in fixtures if f.fixture_type == "sink"]
        others = [f for f in fixtures if f.fixture_type != "sink"]
        vent_routes = {}

        for sink in sinks:
            segments = []
            vent_start = XYZ(sink.position.x, sink.position.y, sink.position.z + 300)
            segments.append(Pipe(
                start_point=sink.position, end_point=vent_start,
                size=50.0, system_type=SystemType.VENT,
            ))

            shared_fixtures = [
                f for f in others
                if sink.position.euclidean_distance(f.position) < 2000
            ]
            for f in shared_fixtures:
                f_vent_start = XYZ(f.position.x, f.position.y, f.position.z + 300)
                segments.append(Pipe(
                    start_point=f.position, end_point=f_vent_start,
                    size=50.0, system_type=SystemType.VENT,
                ))
                segments.append(Pipe(
                    start_point=f_vent_start, end_point=vent_start,
                    size=50.0, system_type=SystemType.VENT,
                ))
                others = [o for o in others if o.name != f.name]

            path = self.pathfinder.find_path(vent_start, self.vent_stack_position)
            for i in range(len(path) - 1):
                segments.append(Pipe(
                    start_point=path[i], end_point=path[i + 1],
                    size=50.0, system_type=SystemType.VENT,
                ))
            vent_routes[f"vent_group_{sink.name}"] = segments

        for f in others:
            vent_start = XYZ(f.position.x, f.position.y, f.position.z + 300)
            path = self.pathfinder.find_path(vent_start, self.vent_stack_position)
            segments = [Pipe(
                start_point=f.position, end_point=vent_start,
                size=50.0, system_type=SystemType.VENT,
            )]
            for i in range(len(path) - 1):
                segments.append(Pipe(
                    start_point=path[i], end_point=path[i + 1],
                    size=50.0, system_type=SystemType.VENT,
                ))
            vent_routes[f"vent_{f.name}"] = segments

        return vent_routes
