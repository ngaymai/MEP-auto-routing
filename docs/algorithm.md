# Detailed Analysis of Core Algorithms in the PRBD System

The paper applies 3 main algorithms to solve the following problems sequentially: Pipe pathfinding, Pipe panelization by panel boundaries, and Cutting pattern optimization to minimize material waste.

---

## 1. Heuristic Pathfinding Algorithm

**Objective:** Find the shortest path with the fewest turns from a plumbing fixture (Start point - S) to the main drainage stack (Terminal point - T) within a space constrained by obstacles.

**Algorithm Basis:** This algorithm is a novel heuristic method combining the greedy search strategy of the A-star algorithm (AA) and Dijkstra's algorithm (DA). The pipe routing space is divided into grid cells based on the minimum pipe length ($l_{min}$).

**Fitness Function:**
At each pipe step (to a new node $n$), the system evaluates the best direction using the function $f(n)$:
> **$f(n) = g(n) + h(n) + t(n)$**

Where:
*   $g(n)$: Pipe length from the start point S to node $n$.
*   $h(n)$: Manhattan distance from node $n$ to the terminal point T, calculated as: $h(n) = |X_t - X_n| + |Y_t - Y_n|$.
*   $t(n)$: Number of turns from the start point S to node $n$.

**Physical Constraints:**
At each neighboring node, the algorithm must check 2 strict constraints to ensure valid pipe routing:
1.  **Joist penetration constraint:** $g(n) \le (H_{Joist} - d_{top} - d_{bottom}) / S_{slope}$. (Ensures the pipe elevation change due to slope $S_{slope}$ does not exceed the safe space available for drilling through floor joists).
2.  **Floor opening constraint:** $D(n) \ge l_{min}$. (The distance from node $n$ to the edges of floor openings $D(n)$ must be greater than or equal to the unit pipe length).

**Execution Steps:**
1. Mark the fixture drain point as the start point S.
2. Calculate the fitness value $f(n)$ for the 4 neighboring nodes.
3. Check constraints $g(n)$ and $D(n)$, keeping only nodes that pass validation.
4. Select the node with the smallest $f(n)$ value as the new start point.
5. Repeat steps 2-4 until the pipe reaches the terminal point T.

---

## 2. Panelization Algorithm

**Objective:** Divide the continuous pipe network (found in Step 1) into smaller segments that fit entirely within the geometric boundaries of each wall or floor panel.

**Execution Steps:**
1.  **Build database:** Establish a matrix of panel boundary equations and pipe centerline equations.
2.  **Calculate intersections:** The system iterates through each boundary and computes intersection coordinates between the boundary segment and drainage pipe segments.
3.  **Cut and Join:** At each intersection coordinate found, the system "cuts" the pipe in two and automatically inserts a coupling fitting (a fitting that joins 2 pipes without changing direction).
4.  The algorithm repeats until all panels and boundaries have been processed.

---

## 3. Integer Programming Algorithm for Pipe Cutting Optimization

**Objective:** Solve the one-dimensional cutting stock problem (1D-CSP) — Cut a standard pipe ($L_s$) of default length into multiple smaller segments of required sizes ($l_i$) such that the total material waste is minimized.

**Scenario Generation (Tree Structure):**
The system uses an exhaustive search algorithm based on a tree structure to generate all feasible cutting scenarios.
For each scenario, the remaining material length (which is also the waste $w_h$ for that scenario) after cutting n pipe segments is calculated as:
> **$w_h = L_k = L_s - \sum_{i=1}^{k} n_i l_i$**

*(Where: $n_i$ is the number of pipe segments of length $l_i$ cut from the standard pipe $L_s$)*.

**Objective Function:**
After obtaining the list of all cutting scenarios with their corresponding waste amounts, the system uses Integer Programming to find the global minimum of the following objective function:
> **$\min \sum_{i=1}^{N} N_i w_i = \sum_{i=1}^{N} \left[N_i \times \left(L_s - \sum_{i=1}^{k} n_i l_i\right)\right]$**

*(Where: $N_i$ is the number of standard pipes that need to be cut according to the configuration of cutting scenario $i$)*.

**Total Length Constraint:**
Ensures that the total length of pieces produced in a cutting scenario never exceeds the length of the original standard pipe:
> **$\sum_{i=1}^{k} n_i l_i \le L_s$**
