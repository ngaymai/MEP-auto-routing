"""
BIM data models for the PRBD automated drainage design system.
Class hierarchy based on UML diagram (Figure 7 of the paper).

Hierarchy:
  BuildingComponent
  ├── Stud
  ├── Wall -> PlumbingWall
  ├── Joist
  ├── Floor -> PlumbingFloor
  ├── PlumbingFixture
  └── PlumbingComponent
      ├── Pipe
      └── PlumbingFitting
"""

import math
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


# =============================================================================
# Core Types (Revit API primitives mapped to Python)
# =============================================================================

@dataclass(frozen=True)
class XYZ:
    """3D coordinate point (equivalent to Revit API XYZ)."""
    x: float
    y: float
    z: float

    def __add__(self, other: "XYZ") -> "XYZ":
        return XYZ(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "XYZ") -> "XYZ":
        return XYZ(self.x - other.x, self.y - other.y, self.z - other.z)

    def manhattan_distance(self, other: "XYZ") -> float:
        return abs(self.x - other.x) + abs(self.y - other.y)

    def euclidean_distance(self, other: "XYZ") -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2)


# Alias for backward compatibility
Point3D = XYZ


class SystemType(Enum):
    """Plumbing system type."""
    DRAIN = "drain"
    VENT = "vent"


@dataclass
class Curve:
    """Line segment defined by start and end points."""
    start: XYZ
    end: XYZ

    @property
    def length(self) -> float:
        return self.start.euclidean_distance(self.end)

    @property
    def direction(self) -> tuple:
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        dist = math.sqrt(dx ** 2 + dy ** 2)
        if dist == 0:
            return (0, 0)
        return (dx / dist, dy / dist)


@dataclass
class Connector:
    """Connection point on a plumbing element."""
    point: XYZ
    system_type: SystemType
    size: float  # diameter in mm


@dataclass
class Level:
    """Building level / storey."""
    name: str
    elevation: float  # mm from ground


@dataclass
class Opening:
    """Opening in a floor or wall (obstacle for pipe routing)."""
    min_corner: XYZ
    max_corner: XYZ

    def contains(self, point: XYZ) -> bool:
        return (self.min_corner.x <= point.x <= self.max_corner.x and
                self.min_corner.y <= point.y <= self.max_corner.y)

    def distance_to(self, point: XYZ) -> float:
        """Minimum distance from point to the opening boundary."""
        dx = max(self.min_corner.x - point.x, 0, point.x - self.max_corner.x)
        dy = max(self.min_corner.y - point.y, 0, point.y - self.max_corner.y)
        return math.sqrt(dx ** 2 + dy ** 2)


@dataclass
class WallOpening:
    """Opening in a wall (door or window)."""
    opening_type: str   # "door" or "window"
    offset: float       # distance along wall from start_point (mm)
    width: float        # width of opening (mm)
    z_bottom: float     # bottom of opening relative to wall base (0 for doors)
    height: float       # height of opening (mm)


# Alias for backward compatibility
Obstacle = Opening


# =============================================================================
# BuildingComponent (base class for all BIM elements)
# =============================================================================

@dataclass
class BuildingComponent:
    """Base class for all building elements (Figure 7)."""
    id: int = 0
    name: str = ""
    base_level: Optional[Level] = None


# =============================================================================
# Structural elements
# =============================================================================

@dataclass
class Stud(BuildingComponent):
    """Structural stud within a wall frame."""
    location_point: Optional[XYZ] = None
    width: float = 0.0
    depth: float = 0.0
    rotation: float = 0.0
    top_level: Optional[Level] = None
    function: str = ""
    host_id: Optional[int] = None


@dataclass
class Joist(BuildingComponent):
    """Floor joist / beam structural element."""
    start_point: Optional[XYZ] = None
    end_point: Optional[XYZ] = None
    width: float = 0.0
    depth: float = 0.0  # H_joist
    location_curve: Optional[Curve] = None
    function: str = ""
    host_id: Optional[int] = None


# =============================================================================
# Wall hierarchy: Wall -> PlumbingWall
# =============================================================================

@dataclass
class Wall(BuildingComponent):
    """Wall element."""
    start_point: Optional[XYZ] = None
    end_point: Optional[XYZ] = None
    location_curve: Optional[Curve] = None
    is_mechanical: bool = False
    is_structural: bool = False
    doors: list = field(default_factory=list)
    windows: list = field(default_factory=list)

    def get_hosting_openings(self) -> list[Opening]:
        return []


@dataclass
class PlumbingWall(Wall):
    """Wall panel containing plumbing elements."""
    pipes: list = field(default_factory=list)
    fittings: list = field(default_factory=list)
    fixtures: list = field(default_factory=list)
    assemblies: list = field(default_factory=list)
    geometry: list = field(default_factory=list)  # list of Curve (boundary edges)

    def is_overlapped(self, stud: Stud) -> bool:
        if stud.location_point is None:
            return False
        for pipe in self.pipes:
            if pipe.location_curve and stud.location_point:
                mid = XYZ(
                    (pipe.location_curve.start.x + pipe.location_curve.end.x) / 2,
                    (pipe.location_curve.start.y + pipe.location_curve.end.y) / 2,
                    (pipe.location_curve.start.z + pipe.location_curve.end.z) / 2,
                )
                if mid.euclidean_distance(stud.location_point) < stud.width:
                    return True
        return False

    def get_design_layout(self) -> list[Curve]:
        return list(self.geometry)

    def get_boundary_equations(self) -> list:
        """Return boundary equations as (a, b, c, start, end) tuples."""
        equations = []
        for curve in self.geometry:
            a = curve.end.y - curve.start.y
            b = curve.start.x - curve.end.x
            c = -(a * curve.start.x + b * curve.start.y)
            equations.append((a, b, c, curve.start, curve.end))
        return equations


# =============================================================================
# Floor hierarchy: Floor -> PlumbingFloor
# =============================================================================

@dataclass
class Floor(BuildingComponent):
    """Floor element."""
    thickness: float = 0.0
    boundaries: list = field(default_factory=list)  # list of Curve
    openings: list = field(default_factory=list)     # list of Opening

    def get_hosting_openings(self) -> list[Opening]:
        return list(self.openings)


@dataclass
class PlumbingFloor(Floor):
    """Floor panel containing plumbing elements."""
    pipes: list = field(default_factory=list)
    fittings: list = field(default_factory=list)
    fixtures: list = field(default_factory=list)
    assemblies: list = field(default_factory=list)
    geometry: list = field(default_factory=list)  # list of Curve (boundary edges)

    def is_overlapped(self, plate) -> bool:
        return False

    def is_over_depth(self, plate) -> bool:
        return False

    def get_design_layout(self) -> list[Curve]:
        return list(self.geometry)

    def get_boundary_equations(self) -> list:
        """Return boundary equations as (a, b, c, start, end) tuples."""
        equations = []
        for curve in self.geometry:
            a = curve.end.y - curve.start.y
            b = curve.start.x - curve.end.x
            c = -(a * curve.start.x + b * curve.start.y)
            equations.append((a, b, c, curve.start, curve.end))
        return equations


# =============================================================================
# Plumbing Fixture
# =============================================================================

@dataclass
class PlumbingFixture(BuildingComponent):
    """Plumbing fixture: toilet, sink, shower, bathtub, etc."""
    host_id: Optional[int] = None
    level: Optional[Level] = None
    still_height: float = 0.0
    connections: list = field(default_factory=list)  # list of Connector
    fixture_type: str = ""  # "toilet", "sink", "shower", "bathtub"
    drain_diameter: float = 75.0  # mm
    _position: Optional[XYZ] = field(default=None, repr=False)

    @property
    def position(self) -> XYZ:
        """Fixture location (from drain connector or explicit position)."""
        if self._position is not None:
            return self._position
        return self.get_drainage_connector_point()

    @position.setter
    def position(self, value: XYZ):
        self._position = value

    def get_drainage_connector_point(self) -> XYZ:
        """Get the drain connection point (UML: GetDrainageConnectorPoint)."""
        for conn in self.connections:
            if conn.system_type == SystemType.DRAIN:
                return conn.point
        return XYZ(0, 0, 0)


# Alias for backward compatibility
Fixture = PlumbingFixture


# =============================================================================
# PlumbingComponent hierarchy: PlumbingComponent -> Pipe, PlumbingFitting
# =============================================================================

@dataclass
class PlumbingComponent(BuildingComponent):
    """Base class for pipes and fittings."""
    start_point: Optional[XYZ] = None
    end_point: Optional[XYZ] = None
    system_type: SystemType = SystemType.DRAIN
    connections: list = field(default_factory=list)  # list of Connector

    @property
    def length(self) -> float:
        if self.start_point and self.end_point:
            return self.start_point.euclidean_distance(self.end_point)
        return 0.0

    @property
    def horizontal_length(self) -> float:
        """Horizontal (XY-plane) length, ignoring slope."""
        if self.start_point and self.end_point:
            return self.start_point.manhattan_distance(self.end_point)
        return 0.0


@dataclass
class Pipe(PlumbingComponent):
    """Drainage or vent pipe segment."""
    size: float = 75.0  # diameter in mm
    location_curve: Optional[Curve] = None
    fixture_drainage_point: Optional[XYZ] = None
    panel_id: Optional[str] = None

    def auto_design_layout(self) -> list[Curve]:
        """Generate design layout curves (UML: AutoDesignLayout)."""
        if self.start_point and self.end_point:
            return [Curve(self.start_point, self.end_point)]
        return []

    @property
    def direction(self) -> tuple:
        if not self.start_point or not self.end_point:
            return (0, 0)
        dx = self.end_point.x - self.start_point.x
        dy = self.end_point.y - self.start_point.y
        dist = math.sqrt(dx ** 2 + dy ** 2)
        if dist == 0:
            return (0, 0)
        return (dx / dist, dy / dist)


# Alias for backward compatibility
PipeSegment = Pipe


@dataclass
class PlumbingFitting(PlumbingComponent):
    """Pipe fitting: elbow, tee, coupling, etc."""
    size: float = 75.0  # diameter in mm
    fitting_type: str = ""  # "elbow", "tee", "coupling"


# =============================================================================
# Panel (convenience wrapper for panelization algorithm)
# =============================================================================

@dataclass
class Panel:
    """Generic panel for the panelization algorithm.
    Can be constructed directly or from PlumbingWall/PlumbingFloor."""
    panel_id: str = ""
    panel_type: str = ""  # "wall" or "floor"
    boundaries: list = field(default_factory=list)  # list of (XYZ, XYZ) tuples

    def get_boundary_equations(self) -> list:
        """Return boundary equations as (a, b, c, start, end)."""
        equations = []
        for start, end in self.boundaries:
            a = end.y - start.y
            b = start.x - end.x
            c = -(a * start.x + b * start.y)
            equations.append((a, b, c, start, end))
        return equations

    @classmethod
    def from_plumbing_wall(cls, pw: PlumbingWall) -> "Panel":
        return cls(
            panel_id=pw.name or str(pw.id),
            panel_type="wall",
            boundaries=[(c.start, c.end) for c in pw.geometry],
        )

    @classmethod
    def from_plumbing_floor(cls, pf: PlumbingFloor) -> "Panel":
        return cls(
            panel_id=pf.name or str(pf.id),
            panel_type="floor",
            boundaries=[(c.start, c.end) for c in pf.geometry],
        )


# =============================================================================
# Algorithm Configuration (routing parameters, not in UML)
# =============================================================================

@dataclass
class JoistConstraint:
    """Structural joist constraints for pipe penetration check."""
    joist_height: float  # H_joist (mm)
    d_top: float         # min clearance from top of joist (mm)
    d_bottom: float      # min clearance from bottom of joist (mm)

    @property
    def max_penetration_depth(self) -> float:
        return self.joist_height - self.d_top - self.d_bottom

    @classmethod
    def from_joist(cls, joist: Joist, d_top: float, d_bottom: float) -> "JoistConstraint":
        """Create constraint from a Joist element."""
        return cls(joist_height=joist.depth, d_top=d_top, d_bottom=d_bottom)


@dataclass
class RoutingConfig:
    """Configuration parameters for pipe routing algorithm."""
    pipe_slope: float = 0.02           # S_slope: slope ratio (e.g., 2%)
    min_pipe_length: float = 300.0     # l_min: minimum pipe unit length (mm)
    grid_size: float = 300.0           # grid cell size based on l_min (mm)
    default_diameter: float = 75.0     # default pipe diameter (mm)
    joist_constraint: Optional[JoistConstraint] = None
