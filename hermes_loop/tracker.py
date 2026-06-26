"""ETATracker — per-task-type average duration & time estimation."""


class ETATracker:
    """Tracks average iteration duration per task type and estimates remaining time."""

    def __init__(self):
        self._type_totals: dict[str, float] = {}
        self._type_counts: dict[str, int] = {}

    def record_iteration(self, task_type: str, duration_seconds: float):
        self._type_totals.setdefault(task_type, 0)
        self._type_totals[task_type] += duration_seconds
        self._type_counts.setdefault(task_type, 0)
        self._type_counts[task_type] += 1

    def avg_duration(self, task_type: str | None = None) -> float:
        if (
            task_type
            and task_type in self._type_counts
            and self._type_counts[task_type] > 0
        ):
            return self._type_totals[task_type] / self._type_counts[task_type]
        total = sum(self._type_totals.values())
        count = sum(self._type_counts.values())
        return round(total / count, 1) if count > 0 else 0.0

    def estimate_remaining(
        self, task_type: str, iterations_done: int, max_iterations: int
    ) -> float:
        if max_iterations <= 0:
            return 0.0
        remaining = max_iterations - iterations_done
        if remaining <= 0:
            return 0.0
        avg = self.avg_duration(task_type)
        return round(avg * remaining, 1)

    def format_eta(self, seconds: float) -> str:
        if seconds <= 0:
            return "N/A"
        if seconds >= 3600:
            return f"{seconds / 3600:.1f}h ({seconds / 60:.0f}m)"
        if seconds >= 60:
            return f"{seconds / 60:.0f}m"
        return f"{seconds:.0f}s"

    def to_dict(self) -> dict:
        return {
            "per_type": {
                tt: {
                    "avg": self.avg_duration(tt),
                    "count": self._type_counts[tt],
                }
                for tt in self._type_counts
            },
            "overall_avg": self.avg_duration(),
        }
