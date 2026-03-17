# Summary: Methodology and Implementation

The automated drainage system design for panelized residential buildings (PRBD) is built on a closed-loop process, from pipe route planning to shop drawing generation and material optimization.

---

## 1. Methodology

The automation process is divided into 4 main steps/modules:

*   **Step 1: Scenario-based Vent Pipe Design:**
    Instead of manual drafting, the system provides 3 pre-built vent pipe design scenarios that comply with plumbing code requirements. The scenarios include: (1) Each fixture has its own individual branch vent; (2) A single common vent shared by all fixtures; (3) Sharing the sink's vent pipe with other nearby fixtures [26, Table 1, 27].
*   **Step 2: Rule-based Drainage Pipe Design:**
    Uses a novel heuristic algorithm combining the greedy search strategy of A-star (AA) and Dijkstra (DA) algorithms to automatically determine the optimal pipe route. The algorithm finds the shortest path with the fewest turns from the plumbing fixture to the main drainage stack, while continuously checking 3D spatial constraints such as: joist penetration depth limits and safe clearance from floor openings.
*   **Step 3: Residential Drainage System Panelization:**
    To support factory manufacturing and assembly, the overall pipe network is automatically analyzed for intersection coordinates with wall and floor panel boundaries. Pipes are "cut" at these boundaries and connected with coupling fittings. A separate Bill of Materials (BOM) is then generated for each panel.
*   **Step 4: Pipe Cutting Optimization:**
    This step solves the one-dimensional cutting stock problem (1D-CSP) to minimize material waste. An Integer Programming algorithm is used to enumerate all feasible cutting scenarios from the standard pipe length via a tree structure, and then find the optimal cutting plan.

---

## 2. Implementation

To demonstrate the feasibility of the method, the research team developed a working software tool with the following characteristics:

*   **Platform and Programming Language:**
    The system was developed as an **add-on for Autodesk Revit**. The source code was written in **C#** and communicates directly with the BIM environment through the **Revit API** to automatically create pipes, fittings, and identify structural elements.
*   **Input Data Requirements:**
    The system requires a BIM model at a minimum detail level of **LOD 300** (accurately representing dimensions, shapes, and positions of walls, floors, doors, and plumbing fixtures). Engineers also need to set up pipe routing preferences and can use pre-designed "combo fittings" (standardized fitting assemblies) to increase standardization.
*   **User Interface:**
    The add-on uses **Windows Form** dialogs for user interaction. Users can easily select vent pipe scenarios, trap types, or configure pipe slope and height parameters directly through this interface.
*   **Automated Shop Drawing Generation:**
    The software not only automates 3D spatial modeling but also automatically generates **plan layout drawings and individual shop drawings for each panel (plumbing wall/floor panel shop drawings)**, along with the corresponding BOM displayed directly on the drawings.
*   **Multi-software Optimization Integration:**
    The BOM is automatically exported from Revit to a **Microsoft Excel** file. The Integer Programming algorithm for pipe cutting optimization is executed via a **Visual Basic (VB)** macro embedded within Excel.
*   **Real-world Effectiveness (Case Study):**
    When tested on a 2-storey townhouse project with 5 units, the tool **reduced design time from approximately 1 week to about 20 minutes**. Additionally, pipe waste after applying the cutting optimization algorithm was reduced to **only 13.02%**, significantly better than the 19.43% waste rate from manual cutting in typical construction sequences.
