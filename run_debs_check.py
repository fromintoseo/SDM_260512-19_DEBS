"""Check consistency between decode_calc() and decode_debs().

Usage example:
    python run_debs_check.py

Before running, adjust load_instance() if your project does not already expose
an instance object from main.py or another module.
"""

from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from decoder import decode_calc, makespan
from debs import decode_debs, decode_debs_with_log, get_processing_time


RANDOM_SEED = 42
N_SOLUTIONS = 10
OUTPUT_HTML = "debs_gantt.html"
OUTPUT_LOG = "debs_event_log.txt"


def main() -> None:
    instance = load_instance()

    rng = random.Random(RANDOM_SEED)
    solutions = [generate_random_solution(instance, rng) for _ in range(N_SOLUTIONS)]

    for case_idx, (job_seq, machine_seq) in enumerate(solutions, start=1):
        schedule_calc = decode_calc(instance, job_seq, machine_seq)
        schedule_debs = decode_debs(instance, job_seq, machine_seq)

        mk_calc = makespan(schedule_calc)
        mk_debs = makespan(schedule_debs)

        print(f"[{case_idx:02d}] calc={mk_calc}, debs={mk_debs}")

        if mk_calc != mk_debs:
            print("\nMismatch detected!")
            print_first_difference(schedule_calc, schedule_debs, job_seq)
            raise AssertionError(f"makespan mismatch: calc={mk_calc}, debs={mk_debs}")

    print(f"\nAll {N_SOLUTIONS} solutions matched.")

    # Submit one Plotly Gantt HTML using the last DEBS schedule.
    last_job_seq, last_machine_seq = solutions[-1]
    schedule_debs, event_log = decode_debs_with_log(instance, last_job_seq, last_machine_seq)
    save_event_log(event_log, OUTPUT_LOG)
    save_plotly_gantt(schedule_debs, OUTPUT_HTML)
    print(f"Saved: {OUTPUT_HTML}")
    print(f"Saved: {OUTPUT_LOG}")


def load_instance() -> Any:
    """Load your FJSP instance.

    Replace this function with the same instance-loading code used in your
    original GA/decoder experiment.

    Common examples:
        from main import instance
        return instance

        from data_loader import load_instance
        return load_instance("data/sample.json")
    """
    try:
        from main import instance  # type: ignore
        return instance
    except Exception as exc:
        raise RuntimeError(
            "Please edit load_instance() in run_debs_check.py so it returns your FJSP instance."
        ) from exc


def generate_random_solution(instance: Any, rng: random.Random) -> Tuple[List[int], List[int]]:
    """Create one feasible-ish random solution.

    job_seq repeats each job id by the number of operations.
    machine_seq chooses one eligible machine for each gene's operation.
    """
    num_ops_by_job = infer_num_ops_by_job(instance)

    job_seq: List[int] = []
    for job_id, n_ops in num_ops_by_job.items():
        job_seq.extend([job_id] * n_ops)
    rng.shuffle(job_seq)

    op_count: Dict[int, int] = defaultdict(int)
    machine_seq: List[int] = []
    for job_id in job_seq:
        op_id = op_count[job_id]
        op_count[job_id] += 1

        machines = infer_eligible_machines(instance, job_id, op_id)
        if not machines:
            raise ValueError(f"No eligible machines found for job={job_id}, op={op_id}")
        machine_seq.append(rng.choice(machines))

    return job_seq, machine_seq


def infer_num_ops_by_job(instance: Any) -> Dict[int, int]:
    """Infer operation count per job from common Instance structures."""
    jobs = getattr(instance, "jobs", None)
    if jobs is not None:
        result: Dict[int, int] = {}
        for j, job in enumerate(jobs):
            operations = getattr(job, "operations", job)
            result[j] = len(operations)
        return result

    n_jobs = getattr(instance, "n_jobs", getattr(instance, "num_jobs", None))
    n_ops = getattr(instance, "n_ops", getattr(instance, "num_ops", None))
    if n_jobs is not None and n_ops is not None:
        if isinstance(n_ops, int):
            return {j: n_ops for j in range(n_jobs)}
        return {j: n_ops[j] for j in range(n_jobs)}

    ptime = getattr(instance, "ptime", None)
    if isinstance(ptime, dict):
        max_op: Dict[int, int] = defaultdict(lambda: -1)
        for key in ptime.keys():
            if isinstance(key, tuple) and len(key) == 3:
                j, o, _m = key
                max_op[int(j)] = max(max_op[int(j)], int(o))
        if max_op:
            return {j: o + 1 for j, o in max_op.items()}

    raise AttributeError("Cannot infer number of operations per job. Please edit infer_num_ops_by_job().")


def infer_eligible_machines(instance: Any, job_id: int, op_id: int) -> List[int]:
    """Infer eligible machines by checking finite processing times."""
    for method_name in ("eligible_machines", "get_eligible_machines"):
        method = getattr(instance, method_name, None)
        if callable(method):
            return list(method(job_id, op_id))

    machines = getattr(instance, "machines", None)
    if machines is None:
        n_machines = getattr(instance, "n_machines", getattr(instance, "num_machines", None))
        if n_machines is not None:
            machines = list(range(n_machines))

    if machines is None:
        machines = infer_machines_from_ptime(instance)

    eligible: List[int] = []
    for mid in machines:
        try:
            p = get_processing_time(instance, job_id, op_id, int(mid))
        except Exception:
            p = None
        if p is not None and p != float("inf"):
            eligible.append(int(mid))
    return eligible


def infer_machines_from_ptime(instance: Any) -> List[int]:
    ptime = getattr(instance, "ptime", None)
    if isinstance(ptime, dict):
        machines = set()
        for key in ptime.keys():
            if isinstance(key, tuple) and len(key) == 3:
                machines.add(int(key[2]))
        return sorted(machines)

    n_machines = getattr(instance, "n_machines", getattr(instance, "num_machines", None))
    if n_machines is not None:
        return list(range(n_machines))

    raise AttributeError("Cannot infer machine list. Please edit infer_machines_from_ptime().")


def print_first_difference(schedule_calc: List[Any], schedule_debs: List[Any], job_seq: List[int]) -> None:
    """Print first operation whose start/end differs.

    Comparison is by (job_id, op_id), not list position, because DEBS may append
    operations in event-finish order.
    """
    calc_map = {op_key(op): op for op in schedule_calc}
    debs_map = {op_key(op): op for op in schedule_debs}

    op_count: Dict[int, int] = defaultdict(int)
    for gene_idx, job_id in enumerate(job_seq):
        op_id = op_count[job_id]
        op_count[job_id] += 1
        key = (job_id, op_id)

        c = calc_map.get(key)
        d = debs_map.get(key)
        if c is None or d is None:
            print(f"First missing op at gene={gene_idx}, key={key}: calc={c}, debs={d}")
            return

        if get_start(c) != get_start(d) or get_end(c) != get_end(d) or get_mid(c) != get_mid(d):
            print(f"First different operation at gene={gene_idx}, job={job_id}, op={op_id}")
            print(f"  calc: mid={get_mid(c)}, start={get_start(c)}, end={get_end(c)}")
            print(f"  debs: mid={get_mid(d)}, start={get_start(d)}, end={get_end(d)}")
            return

    print("No operation-level difference found, but makespan differs. Check makespan() implementation.")


def op_key(op: Any) -> Tuple[int, int]:
    return (get_job_id(op), get_op_id(op))


def get_job_id(op: Any) -> int:
    return int(getattr(op, "job_id"))


def get_op_id(op: Any) -> int:
    return int(getattr(op, "op_id", getattr(op, "operation_id", None)))


def get_mid(op: Any) -> int:
    return int(getattr(op, "mid", getattr(op, "machine_id", None)))


def get_start(op: Any) -> float:
    return float(getattr(op, "start"))


def get_end(op: Any) -> float:
    return float(getattr(op, "end"))


def save_event_log(event_log: List[str], path: str) -> None:
    Path(path).write_text("\n".join(event_log), encoding="utf-8")


def save_plotly_gantt(schedule: List[Any], output_html: str) -> None:
    """Save Plotly Gantt HTML.

    If your previous viz_plotly.py has a different function name, replace this
    fallback with that project-specific function.
    """
    # Try project's existing visualizer first.
    try:
        import viz_plotly  # type: ignore
        for fn_name in ("plot_gantt", "save_gantt", "plotly_gantt", "draw_gantt"):
            fn = getattr(viz_plotly, fn_name, None)
            if callable(fn):
                try:
                    fn(schedule, output_html=output_html)
                    return
                except TypeError:
                    fn(schedule, output_html)
                    return
    except Exception:
        pass

    # Fallback: direct Plotly implementation.
    import plotly.express as px
    import pandas as pd

    rows = []
    for op in schedule:
        rows.append(
            {
                "Machine": f"M{get_mid(op)}",
                "Job": f"J{get_job_id(op)}",
                "Operation": f"J{get_job_id(op)}-O{get_op_id(op)}",
                "Start": get_start(op),
                "Finish": get_end(op),
            }
        )

    df = pd.DataFrame(rows)
    fig = px.timeline(df, x_start="Start", x_end="Finish", y="Machine", color="Job", hover_name="Operation")
    fig.update_yaxes(autorange="reversed")
    fig.write_html(output_html)


if __name__ == "__main__":
    main()
