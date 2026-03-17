"""
Full PRBD Pipeline: orchestrates all 4 steps of the automated drainage design.
"""

from models import XYZ, PlumbingFixture, Opening, Panel, RoutingConfig
from pathfinding import HeuristicPathfinder
from vent_design import VentPipeDesigner, VentScenario
from panelization import PanelizationAlgorithm
from cutting_optimization import PipeCuttingOptimizer


class PRBDPipeline:
    """
    Complete PRBD automated drainage design pipeline.

    Step 1: Vent pipe design (scenario-based)
    Step 2: Drainage pipe routing (heuristic pathfinding)
    Step 3: Panelization (cut at panel boundaries)
    Step 4: Pipe cutting optimization (1D-CSP)
    """

    def __init__(
        self,
        config: RoutingConfig,
        obstacles: list[Opening] = None,
        standard_pipe_length: float = 6000.0,
    ):
        self.config = config
        self.obstacles = obstacles or []
        self.pathfinder = HeuristicPathfinder(config, self.obstacles)
        self.panelizer = PanelizationAlgorithm()
        self.optimizer = PipeCuttingOptimizer(standard_pipe_length)

    def run(
        self,
        fixtures: list[PlumbingFixture],
        main_stack: XYZ,
        vent_stack: XYZ,
        panels: list[Panel],
        vent_scenario: VentScenario = VentScenario.INDIVIDUAL,
    ) -> dict:
        """Execute the full pipeline. Returns comprehensive result dict."""
        print("=" * 60)
        print("PRBD Automated Drainage Design System")
        print("=" * 60)

        # --- Step 1: Vent Pipe Design ---
        print(f"\n[Step 1] Scenario-based Vent Pipe Design ({vent_scenario.name})...")
        vent_designer = VentPipeDesigner(vent_stack, self.config)
        vent_routes = vent_designer.design_vents(fixtures, vent_scenario)
        vent_segments = [seg for segs in vent_routes.values() for seg in segs]
        print(f"  Generated {len(vent_segments)} vent pipe segments")

        # --- Step 2: Drainage Pipe Routing ---
        print("\n[Step 2] Rule-based Drainage Pipe Routing...")
        drain_routes = self.pathfinder.route_all_fixtures(fixtures, main_stack)
        drain_segments = [seg for segs in drain_routes.values() for seg in segs]
        print(f"  Routed {len(fixtures)} fixtures -> {len(drain_segments)} drain segments")
        for name, segs in drain_routes.items():
            total_len = sum(s.length for s in segs)
            turns = max(0, len(segs) - 1)
            print(f"    {name}: {total_len:.0f}mm, {turns} turn(s)")

        # --- Step 3: Panelization ---
        print("\n[Step 3] Panelization...")
        all_segments = drain_segments + vent_segments
        panelized_segments, couplings = self.panelizer.panelize(all_segments, panels)
        print(f"  {len(all_segments)} segments -> {len(panelized_segments)} panelized segments")
        print(f"  {len(couplings)} coupling(s) inserted")

        bom = self.panelizer.generate_bom(panelized_segments)
        print("  BOM by panel:")
        for panel_id, items in bom.items():
            total = sum(item['length'] for item in items)
            print(f"    Panel {panel_id}: {len(items)} pieces, total {total:.0f}mm")

        # --- Step 4: Pipe Cutting Optimization ---
        print("\n[Step 4] Pipe Cutting Optimization (1D-CSP)...")
        required = {}
        for seg in panelized_segments:
            # Use horizontal length for cutting — slope doesn't affect stock cuts
            length = round(seg.horizontal_length)
            if length > 0:
                required[length] = required.get(length, 0) + 1

        if required:
            opt_result = self.optimizer.optimize(required)
            print(f"  Total standard pipes needed: {opt_result['total_pipes']}")
            print(f"  Total waste: {opt_result['total_waste']:.0f}mm")
            print(f"  Waste percentage: {opt_result['waste_percentage']:.2f}%")
            print("  Cutting patterns:")
            for i, pat in enumerate(opt_result['patterns'], 1):
                cuts_str = ", ".join(f"{l}mm x{n}" for l, n in pat['cuts'].items())
                print(f"    Pattern {i}: [{cuts_str}] x{pat['num_pipes']} pipes, "
                      f"waste={pat['waste_per_pipe']}mm/pipe")
        else:
            opt_result = {"total_waste": 0, "total_pipes": 0, "waste_percentage": 0, "patterns": []}

        print("\n" + "=" * 60)
        print("Pipeline complete!")
        print("=" * 60)

        return {
            "vent_routes": vent_routes,
            "drain_routes": drain_routes,
            "panelized_segments": panelized_segments,
            "couplings": couplings,
            "bom": bom,
            "cutting_optimization": opt_result,
        }
