from __future__ import annotations
from pathlib import Path
from decoder import decode_calc, makespan
from debs import decode_debs
from model import Instance, Job, Machine, Operation
import viz_plotly


def main() :
    print("=== FJSP 디코더 비교 테스트 ===\n")
    instance = create_instance() # Processing Time과 인스턴스 여기에 저장

    sample_OS = [0, 1, 0, 1, 2, 3, 4]
    sample_MS = [0, 0, 0, 0, 0, 0, 0]

    # 기존 디코더
    schedule_calc = decode_calc(instance, sample_OS, sample_MS)
    mk_calc = makespan(schedule_calc)

    # DEBS 디코더
    schedule_debs, event_log = decode_debs(instance, sample_OS, sample_MS)
    mk_debs = makespan(schedule_debs)

    print(f"-> 기존 Makespan: {mk_calc}")
    print(f"-> DEBS Makespan: {mk_debs}")

    if mk_calc < mk_debs:
        print("\n 다르다!")
    else:
        print("\n 같다!")

    # 간트차트 저장
    save_event_log(event_log, "debs_event_log.txt")
    viz_plotly.plot_gantt_plotly(instance, schedule_calc, "calc_gantt.html")
    viz_plotly.plot_gantt_plotly(instance, schedule_debs, "debs_gantt.html")

def create_instance() :
    inst = Instance()
    inst.machines = [Machine(i, f"M{i}") for i in range(3)]

    # 5개의 Job
    job_list = [
        [(0, 10), (1, 10)],  # J0: Op0(M0, 10), Op1(M1, 10)
        [(1, 5), (0, 10)],  # J1: Op0(M1, 5), Op1(M0, 10)
        [(2, 10)],  # J2: Op0(M2, 10)
        [(1, 4)],  # J3: Op0(M1, 4)
        [(2, 5)]  # J4: Op0(M2, 5)
    ]

    for j_id, ops in enumerate(job_list):
        job = Job(j_id)
        for op_id, (m_id, ptime) in enumerate(ops):
            op = Operation(j_id, op_id)
            op.add_alternative(m_id, ptime)
            job.add_operation(op)
        inst.jobs.append(job)

    inst.compute_job_idx()
    return inst

def save_event_log(event_log: List[str], path: str) -> None:
    Path(path).write_text("\n".join(event_log), encoding="utf-8")

if __name__ == "__main__":
    main()