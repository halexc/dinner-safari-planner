"""Compare solver preparation, model size and feasibility on local event data."""

import argparse
import importlib.util
import json
from pathlib import Path
from time import monotonic

from ortools.sat.python import cp_model

from cykelfest_routing.data import DinnerData, Participant
from cykelfest_routing.project import load_project
from cykelfest_routing.solver import solve_routes, validate_assignment
from cykelfest_routing.verification import SegmentPreferences


def benchmark(solve, data, preferences, maximum_time, workers=None):
    metrics = {"stages": []}
    start = monotonic()
    original = cp_model.CpSolver

    def progress(message):
        metrics["stages"].append({"message": message, "seconds": round(monotonic() - start, 3)})
        if message.startswith("Feasible starting assignment ready"):
            metrics["starting_assignment_seconds"] = round(monotonic() - start, 3)

    class FirstSolution(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            metrics.setdefault("first_search_solution_seconds", round(monotonic() - start, 3))

    class RecordedSolver(original):
        def solve(self, model, *arguments, **keywords):
            if "preparation_seconds" not in metrics:
                metrics.update(
                    preparation_seconds=round(monotonic() - start, 3),
                    variables=len(model.proto.variables),
                    constraints=len(model.proto.constraints),
                    table_cells=sum(
                        len(c.table.values) for c in model.proto.constraints if c.has_table()
                    ),
                )
            callback = arguments[0] if arguments else keywords.get("solution_callback")
            if callback is None:
                callback = FirstSolution()
            else:
                original_callback = callback.on_solution_callback

                def record():
                    metrics.setdefault(
                        "first_search_solution_seconds", round(monotonic() - start, 3)
                    )
                    original_callback()

                callback.on_solution_callback = record
            status = super().solve(model, callback)
            metrics.setdefault("searches", []).append(
                {
                    "status": self.status_name(status),
                    "budget_seconds": round(self.parameters.max_time_in_seconds, 3),
                    "wall_seconds": round(self.wall_time, 3),
                    "workers": self.parameters.num_search_workers,
                }
            )
            return status

    cp_model.CpSolver = RecordedSolver
    try:
        options = {} if workers is None else {"search_workers": workers}
        result = solve(data, preferences, maximum_time=maximum_time, progress=progress, **options)
    finally:
        cp_model.CpSolver = original
    if result.data is not None:
        validate_assignment(result.data, preferences)
    return result, metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--sizes", nargs="*", type=int, default=[9, 36, 60])
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--workers", type=int, help="Override automatic worker selection")
    parser.add_argument("--output", type=Path, default=Path("artifacts/solver-benchmark.json"))
    args = parser.parse_args()
    implementations = [("optimized", solve_routes)]
    if args.baseline:
        spec = importlib.util.spec_from_file_location("cykelfest_routing._baseline", args.baseline)
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        implementations.insert(0, ("baseline", baseline.solve_routes))
    events = []
    for n in args.sizes:
        data = DinnerData()
        data.participants = {
            str(i): Participant(
                id=str(i),
                name=f"Pair {i}",
                latitude=58.4 + (i // 9) * 0.002,
                longitude=15.6 + (i % 9) * 0.003,
            )
            for i in range(n)
        }
        events.append((f"grid-{n}", data, SegmentPreferences()))
    if args.project:
        data, settings = load_project(args.project)
        events.append(
            (
                args.project.name,
                data,
                SegmentPreferences(settings.minimum_segment_km, settings.maximum_segment_km),
            )
        )
    records = []
    for name, data, preferences in events:
        for implementation, solve in implementations:
            result, metrics = benchmark(
                solve,
                data,
                preferences,
                args.seconds,
                args.workers if implementation == "optimized" else None,
            )
            record = dict(
                event=name,
                implementation=implementation,
                participants=len(data.participants),
                status=result.status,
                elapsed_seconds=round(result.elapsed, 3),
                objectives=result.objectives,
                **metrics,
            )
            records.append(record)
            print(json.dumps(record), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
