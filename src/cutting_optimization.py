"""
Algorithm 3: Integer Programming - Pipe Cutting Optimization (1D-CSP).

Minimize total waste when cutting standard-length pipes into required pieces.
"""


class PipeCuttingOptimizer:
    """
    1D Cutting Stock Problem (1D-CSP) solver.

    Objective: min sum(N_i * w_i) where w_i = L_s - sum(n_i * l_i)
    Constraint: sum(n_i * l_i) <= L_s for each pattern
    """

    def __init__(self, standard_length: float):
        """
        Args:
            standard_length: Length of standard stock pipe (L_s), e.g. 6000mm
        """
        self.standard_length = standard_length

    def _generate_cutting_patterns(
        self, piece_lengths: list[float]
    ) -> list[tuple[tuple[int, ...], float]]:
        """
        Generate all feasible cutting patterns using exhaustive tree search.

        Each pattern is a tuple of counts (n_1, n_2, ..., n_k) indicating
        how many of each piece length to cut from one standard pipe.

        Returns list of (pattern, waste).
        """
        patterns = []
        unique_lengths = sorted(set(piece_lengths), reverse=True)
        k = len(unique_lengths)

        def _generate(idx: int, remaining: float, current: list[int]):
            if idx == k:
                used = self.standard_length - remaining
                if used > 0:
                    patterns.append((tuple(current), remaining))
                return

            max_count = int(remaining // unique_lengths[idx])
            for count in range(max_count + 1):
                current.append(count)
                _generate(idx + 1, remaining - count * unique_lengths[idx], current)
                current.pop()

        _generate(0, self.standard_length, [])
        return patterns

    def optimize(self, required_pieces: dict[float, int]) -> dict:
        """
        Solve the 1D-CSP using a greedy Integer Programming approach.

        Args:
            required_pieces: dict mapping piece_length -> quantity needed

        Returns:
            dict with patterns, total_waste, total_pipes, waste_percentage
        """
        piece_lengths = sorted(required_pieces.keys(), reverse=True)
        demands = {l: required_pieces[l] for l in piece_lengths}

        all_patterns = self._generate_cutting_patterns(piece_lengths)

        if not all_patterns:
            return {"patterns": [], "total_waste": 0, "total_pipes": 0, "waste_percentage": 0}

        all_patterns.sort(key=lambda x: x[1])

        remaining_demands = dict(demands)
        selected_patterns = []

        while any(v > 0 for v in remaining_demands.values()):
            best_pattern = None
            best_count = 0
            best_score = float('inf')

            for pattern, waste in all_patterns:
                max_times = float('inf')
                useful = False
                for i, length in enumerate(piece_lengths):
                    if pattern[i] > 0:
                        if remaining_demands[length] > 0:
                            useful = True
                            max_times = min(max_times, remaining_demands[length] // pattern[i])
                        else:
                            max_times = 0
                            break

                if not useful or max_times <= 0:
                    continue

                times = int(max_times)
                if times > 0:
                    score = waste * times
                    if score < best_score:
                        best_score = score
                        best_pattern = pattern
                        best_count = times

            if best_pattern is None:
                for length in piece_lengths:
                    while remaining_demands[length] > 0:
                        single = tuple(1 if l == length else 0 for l in piece_lengths)
                        waste = self.standard_length - length
                        selected_patterns.append((single, 1, waste))
                        remaining_demands[length] -= 1
                break

            waste = self.standard_length - sum(
                best_pattern[i] * piece_lengths[i] for i in range(len(piece_lengths))
            )
            selected_patterns.append((best_pattern, best_count, waste))

            for i, length in enumerate(piece_lengths):
                remaining_demands[length] -= best_pattern[i] * best_count

        total_waste = sum(count * waste for _, count, waste in selected_patterns)
        total_pipes = sum(count for _, count, _ in selected_patterns)
        total_material = total_pipes * self.standard_length

        return {
            "patterns": [
                {
                    "cuts": {piece_lengths[i]: pattern[i] for i in range(len(piece_lengths)) if pattern[i] > 0},
                    "num_pipes": count,
                    "waste_per_pipe": round(waste, 1),
                }
                for pattern, count, waste in selected_patterns
            ],
            "total_waste": round(total_waste, 1),
            "total_pipes": total_pipes,
            "waste_percentage": round(100 * total_waste / total_material, 2) if total_material > 0 else 0,
            "piece_lengths": piece_lengths,
        }
