# PRBD Automated Drainage Design — Code Flow Diagram

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                              │
│                        demo()                               │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ models.py    │  │ pathfinding  │  │ visualizer.py    │  │
│  │ (Data Model) │  │ (A* Search)  │  │ (3D Rendering)   │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ vent_design  │  │ panelization │  │ cutting_optim.   │  │
│  │ (Step 1)     │  │ (Step 3)     │  │ (Step 4 - CSP)   │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              pipeline.py (Orchestrator)              │   │
│  │           Step 1 → Step 2 → Step 3 → Step 4         │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Flow chính: `demo()` — Định tuyến ống xuyên tầng L3 → L1

```
demo()
│
├── 1. KHỞI TẠO HÌNH HỌC
│   ├── Tạo RoutingConfig (slope=0.02, grid=300mm, diameter=75mm)
│   ├── Đặt main_stack = (0, 0, 0)
│   ├── Đặt fixture_L3 = (3600, 2400) trên L3
│   ├── Đặt obstacles_L3 = 2 lỗ sàn chặn đường đi trực tiếp
│   └── FOR i = 0..2 (3 tầng):
│       ├── _make_outer_walls(prefix)  → 4 tường bao (S, E, N, W)
│       ├── _make_inner_walls(prefix)  → 2 tường ngăn (MidX, MidY)
│       ├── _make_4_panels(prefix)     → 4 panel sàn (2×2 grid)
│       └── StoreyData(...)            → Gói dữ liệu tầng
│
├── 2. TÌM VỊ TRÍ RISER TỐI ƯU
│   ├── _find_best_riser(fixture, main_stack, all_walls, obstacles)
│   │   │
│   │   │   ┌─────────────────────────────────────────────────┐
│   │   │   │  Cost = manhattan(fixture→riser)                │
│   │   │   │       + manhattan(riser→main_stack)             │
│   │   │   │                                                 │
│   │   │   │  Tiebreaker: ưu tiên riser gần fixture hơn     │
│   │   │   └─────────────────────────────────────────────────┘
│   │   │
│   │   ├── FOR mỗi wall (outer + inner):
│   │   │   ├── Tính blocked zones (cửa/cửa sổ ± clearance)
│   │   │   ├── FOR mỗi grid point trên wall (bước 300mm):
│   │   │   │   ├── Bỏ qua nếu nằm trong vùng cửa/cửa sổ
│   │   │   │   ├── Bỏ qua nếu nằm trong floor obstacle
│   │   │   │   ├── Tính cost = dist(fixture→point) + dist(point→stack)
│   │   │   │   └── Cập nhật best nếu cost thấp hơn
│   │   │   └── END FOR
│   │   └── RETURN (riser_point, wall)
│   │
│   └── Xác định trục riser: tường đứng (x cố định) hay ngang (y cố định)
│
├── 3. ĐỊNH TUYẾN NGANG TẦNG L3: Fixture → Riser
│   ├── HeuristicPathfinder(config, obstacles=obstacles_L3)
│   ├── find_path(fixture.xy → riser.xy)
│   │   │
│   │   │   (Chi tiết A* — xem mục 3 bên dưới)
│   │   │
│   └── Chuyển waypoints → Pipe segments tại z = z_L3_slab_top
│
├── 4. ĐỊNH TUYẾN RISER DỌC ĐỨNG (với tránh cửa sổ)
│   ├── FOR mỗi tầng [L2, L1]:
│   │   ├── Tìm tường tại vị trí tương ứng riser trên tầng đó
│   │   ├── _get_blocked_ranges_on_wall(wall) → vùng bị cửa sổ chặn
│   │   ├── _is_coord_blocked(riser_coord, blocked)?
│   │   │   ├── CÓ → _find_clear_coord() → tọa độ mới tránh cửa sổ
│   │   │   │   └── Thêm đoạn ngang (horizontal shift) trên tường
│   │   │   └── KHÔNG → giữ nguyên tọa độ
│   │   └── Thêm đoạn thẳng đứng (vertical drop) xuống tầng tiếp
│   └── Kết quả: segments_vertical (zigzag nếu có cửa sổ)
│
├── 5. ĐỊNH TUYẾN NGANG TẦNG L1: Riser → Main Stack
│   ├── HeuristicPathfinder(config)  (không có obstacles)
│   ├── find_path(riser_exit.xy → main_stack.xy)
│   └── Chuyển waypoints → Pipe segments tại z = z_L1_slab_top
│
├── 6. KẾT HỢP & IN KẾT QUẢ
│   ├── all_segments = segments_L3 + segments_vertical + segments_L1
│   ├── Tính: total_length, horizontal_L3, horizontal_L1
│   └── In bảng tổng hợp route
│
└── 7. HIỂN THỊ 3D
    └── visualize_multi_storey(storey_data_list, global_routes)
```

---

## 3. Detailed Flow: A\* Pathfinding (`HeuristicPathfinder.find_path`)

```
find_path(start, terminal)
│
├── Convert start, terminal → grid coordinates (divide by grid_size=300)
│
├── Initialize priority queue:
│   └── (f_score=0, counter=0, gx, gy, g_cost=0, turns=0, prev_dir=None, path=[start])
│
├── WHILE queue is not empty:
│   ├── Pop node with smallest f_score
│   │
│   ├── If reached terminal → RETURN path + [terminal]
│   │
│   ├── If already visited → skip
│   │
│   ├── FOR each neighbor (4 directions: ±X, ±Y):
│   │   │
│   │   ├── new_g_cost = g_cost + grid_size
│   │   │
│   │   ├── CHECK JOIST CONSTRAINT:
│   │   │   └── new_g_cost ≤ (H_joist - d_top - d_bottom) / slope ?
│   │   │       └── NO → skip neighbor
│   │   │
│   │   ├── CHECK FLOOR OBSTACLE:
│   │   │   └── distance(neighbor, obstacle) ≥ min_pipe_length ?
│   │   │       └── NO → skip neighbor
│   │   │
│   │   ├── Count turns: +1 if direction changed from prev_dir
│   │   │
│   │   ├── CALCULATE FITNESS:
│   │   │   │
│   │   │   │  ┌──────────────────────────────────────┐
│   │   │   │  │  f(n) = g(n) + h(n) + t(n)          │
│   │   │   │  │                                      │
│   │   │   │  │  g(n) = cumulative pipe length       │
│   │   │   │  │  h(n) = manhattan to terminal        │
│   │   │   │  │  t(n) = turn count × grid_size       │
│   │   │   │  └──────────────────────────────────────┘
│   │   │   │
│   │   │   └── f_n = new_g_cost + h_n + total_turns × grid_size
│   │   │
│   │   └── Push neighbor to queue
│   │
│   └── END FOR
│
└── RETURN [] (no path found)
```

**Slope applied to Z:**
$$z_{node} = z_{start} - g_{cost} \times slope$$

---

## 4. Detailed Flow: `_find_best_riser` — Optimal Riser Position Selection

```
_find_best_riser(fixture_pos, main_stack, walls, grid_size, clearance, obstacles)
│
├── best_cost = ∞
│
├── FOR each wall in walls (perimeter + partition):
│   │
│   ├── Calculate wall_len, direction vector (dx, dy)
│   │
│   ├── Determine blocked zones:
│   │   └── Each door/window → (offset - clearance, offset + width + clearance)
│   │
│   ├── FOR offset = grid_size, 2×grid_size, ... < wall_len:
│   │   │
│   │   ├── Inside blocked zone? → SKIP
│   │   │
│   │   ├── Calculate world coord: (wx, wy) = start + direction × offset
│   │   │
│   │   ├── Inside floor obstacle? → SKIP
│   │   │
│   │   ├── cost = |fixture.x - wx| + |fixture.y - wy|
│   │   │        + |stack.x - wx|   + |stack.y - wy|
│   │   │
│   │   └── cost < best_cost? → update best
│   │       (tiebreaker: prefer closer to fixture)
│   │
│   └── END FOR
│
└── RETURN (best_point, best_wall)
```

---

## 5. Detailed Flow: Window Avoidance on Vertical Riser (Zigzag Logic)

```
FOR each storey in [L2, L1]:
│
├── Find matching_wall = wall at the same position as riser_wall on this storey
│   (same x if vertical wall, same y if horizontal wall)
│
├── blocked = _get_blocked_ranges_on_wall(matching_wall)
│   └── Convert window offsets → world coord ranges
│
├── check_val = riser_y (vertical wall) or riser_x (horizontal wall)
│
├── _is_coord_blocked(check_val, blocked)?
│   │
│   ├── BLOCKED:
│   │   ├── new_val = _find_clear_coord(check_val, blocked, grid, max)
│   │   │   └── Find nearest unblocked grid coordinate (±1, ±2, ... × grid)
│   │   │
│   │   ├── Add Pipe: horizontal shift (riser_xy → new_xy) at current z
│   │   │   ┌─────────────────────────────────────┐
│   │   │   │  Pipe runs horizontally along wall  │
│   │   │   │  to avoid window before dropping    │
│   │   │   └─────────────────────────────────────┘
│   │   └── Update riser_x or riser_y = new_val
│   │
│   └── NOT BLOCKED: keep current position
│
└── Add Pipe: vertical drop (current_z → target_z)
    └── Pipe drops vertically to the next storey floor slab
```

**Zigzag illustration when encountering windows:**

```
          Level 3       Level 2       Level 1
            │              │              │
    ────────┤       ┌──────┤              │
            │       │ shift│              │
            │       │◄─────┤              │
            ▼       ▼      │              │
         (drop)  (drop)    │           (drop)
            │       │      │              │
            ▼       ▼      │              ▼
         ───┘    ───┘   window         ───┘
```

---

## 6. PRBDPipeline — 4-Step Pipeline (per storey)

```
PRBDPipeline.run(fixtures, main_stack, vent_stack, panels, scenario)
│
├── STEP 1: Vent Pipe Design
│   └── VentPipeDesigner.design_vents(fixtures, scenario)
│       │
│       ├── INDIVIDUAL:  each fixture → separate vent → vent_stack
│       ├── SINGLE_COMMON: all → common point (centroid) → vent_stack
│       ├── SHARED_SINK: group by nearby sink (< 2000mm) → shared vent
│       │
│       └── RETURN dict[fixture_name → list[Pipe]]
│
├── STEP 2: Drainage Pipe Routing
│   └── HeuristicPathfinder.route_all_fixtures(fixtures, main_stack)
│       │
│       ├── FOR each fixture:
│       │   └── find_path(fixture.position → main_stack) → A* search
│       │
│       └── RETURN dict[fixture_name → list[Pipe]]
│
├── STEP 3: Panelization
│   └── PanelizationAlgorithm.panelize(all_segments, panels)
│       │
│       ├── FOR each panel:
│       │   ├── Calculate boundary equations from edges
│       │   ├── FOR each pipe segment:
│       │   │   ├── Find 2D intersections with boundaries
│       │   │   ├── Cut segment at intersection
│       │   │   └── Insert coupling at cut point
│       │   └── END FOR
│       │
│       ├── Assign panel_id to each segment (ray-casting test)
│       ├── generate_bom() → group by panel
│       │
│       └── RETURN (panelized_segments, couplings)
│
└── STEP 4: Pipe Cutting Optimization (1D-CSP)
    └── PipeCuttingOptimizer.optimize(required_pieces)
        │
        ├── _generate_cutting_patterns(piece_lengths)
        │   └── Exhaustive tree search: combinations of each type
        │       such that total ≤ standard_length (6000mm)
        │
        ├── Greedy selection:
        │   ├── Sort patterns by waste (ascending)
        │   ├── WHILE demands remain:
        │   │   ├── Find best pattern matching demand
        │   │   ├── Calculate times to use pattern
        │   │   └── Decrement demand, add to results
        │   └── END WHILE
        │
        └── RETURN {patterns, total_waste, total_pipes, waste_pct}
```

---

## 7. Visualization Flow: `visualize_multi_storey`

```
visualize_multi_storey(storeys, global_routes)
│
├── Create Figure + Axes3D
│
├── FOR each storey:
│   ├── z_offset = storey.z_base
│   │
│   ├── DRAW FLOOR SLAB:
│   │   └── _draw_floor_box() → 3D box alpha=0.45
│   │
│   ├── DRAW WALLS:
│   │   └── FOR each wall:
│   │       └── _draw_wall(wall, z_base, height)
│   │           ├── Wall body: moccasin, alpha=0.18
│   │           ├── Doors: brown, alpha=0.3
│   │           └── Windows: blue, alpha=0.25
│   │
│   ├── DRAW FLOOR OPENINGS:
│   │   └── _draw_opening() → red rectangle
│   │
│   ├── DRAW FIXTURES:
│   │   └── Green triangle at fixture position
│   │
│   ├── DRAW PER-STOREY PIPES (drain_routes + vent_routes):
│   │   ├── Drain: thick lines, colored by fixture
│   │   └── Vent: thin dashed lines
│   │
│   ├── DRAW COUPLINGS:
│   │   └── Red X marks at junction points
│   │
│   └── DRAW STACKS:
│       ├── main_stack: black vertical line
│       └── vent_stack: blue vertical line
│
├── DRAW GLOBAL ROUTES (cross-storey):
│   └── Thick lines, absolute z (no offset)
│
└── plt.show()
```

---

## 8. Module Dependency Diagram

```
                    ┌─────────────┐
                    │  main.py    │
                    │   demo()    │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
     ┌────────────┐ ┌────────────┐ ┌───────────┐
     │ pathfinding│ │ pipeline   │ │ visualizer│
     │   .py      │ │   .py      │ │   .py     │
     └─────┬──────┘ └─────┬──────┘ └───────────┘
           │               │
           │        ┌──────┼──────┬──────────┐
           │        │      │      │          │
           │        ▼      ▼      ▼          ▼
           │  ┌────────┐ ┌────┐ ┌──────┐ ┌────────┐
           │  │  vent  │ │path│ │panel │ │cutting │
           │  │ design │ │find│ │ izat │ │ optim  │
           │  └────────┘ └────┘ └──────┘ └────────┘
           │        │      │      │          │
           └────────┴──────┴──────┴──────────┘
                           │
                    ┌──────▼──────┐
                    │  models.py  │
                    │ (XYZ, Wall, │
                    │  Pipe, etc) │
                    └─────────────┘
```

---

## 9. Key Functions Summary

| Module | Function / Class | Description |
|--------|------------------|-------------|
| `main.py` | `demo()` | Entry point: cross-storey routing L3→L1 |
| `main.py` | `_find_best_riser()` | Find optimal riser position on any wall |
| `main.py` | `_make_outer_walls()` | Create 4 perimeter walls |
| `main.py` | `_make_inner_walls()` | Create 2 internal partition walls |
| `main.py` | `_get_blocked_ranges_on_wall()` | Get window-blocked ranges on a wall |
| `main.py` | `_is_coord_blocked()` | Check if coordinate is blocked |
| `main.py` | `_find_clear_coord()` | Find nearest unblocked grid coordinate |
| `pathfinding.py` | `HeuristicPathfinder.find_path()` | A\* search: $f(n)=g(n)+h(n)+t(n)$ |
| `pathfinding.py` | `HeuristicPathfinder.route_fixture()` | Route 1 fixture → Pipe segments |
| `vent_design.py` | `VentPipeDesigner.design_vents()` | Design vents with 3 scenarios |
| `panelization.py` | `PanelizationAlgorithm.panelize()` | Cut pipes at panel boundaries, insert couplings |
| `cutting_optimization.py` | `PipeCuttingOptimizer.optimize()` | 1D-CSP: optimize standard pipe cutting |
| `pipeline.py` | `PRBDPipeline.run()` | 4-step orchestrator |
| `visualizer.py` | `visualize_multi_storey()` | 3D rendering of entire building |

---

## 10. Key Mathematical Formulas

**Fitness function (A\*):**

$$f(n) = g(n) + h(n) + t(n)$$

- $g(n)$: cumulative horizontal length from start to current node
- $h(n)$: Manhattan distance from node to terminal
- $t(n)$: turn count × `grid_size` (direction change penalty)

**Slope (pipe gradient):**

$$z_{node} = z_{start} - g_{cost} \times slope$$

**Joist constraint:**

$$g_{cost} \leq \frac{H_{joist} - d_{top} - d_{bottom}}{slope}$$

**Riser selection cost:**

$$cost = |f_x - r_x| + |f_y - r_y| + |s_x - r_x| + |s_y - r_y|$$

Where: $f$ = fixture, $r$ = riser, $s$ = main stack

**1D-CSP (Cutting Stock):**

$$\min \sum_{i} N_i \times w_i \quad \text{where } w_i = L_{standard} - \sum_{j} n_{ij} \times l_j$$
