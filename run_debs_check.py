from __future__ import annotations
import random
from pathlib import Path
from typing import List, Tuple

from decoder import decode_calc, makespan
from debs import decode_debs
from model import Instance, Job, Machine, Operation
import viz_plotly


def read_fjsp_instance(filepath: Path) -> Instance:
    text = filepath.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]

    # 첫 줄 파싱 (jobs 수, machines 수)
    first_line = lines[0].split()
    num_jobs = int(first_line[0])
    num_machines = int(first_line[1])

    inst = Instance()
    # 기계는 0번 인덱스부터 시작하도록 세팅 (M0, M1, ...)
    inst.machines = [Machine(i, f"M{i}") for i in range(num_machines)]

    # 두 번째 줄부터 Job 파싱
    for j_id in range(num_jobs):
        job_line = lines[j_id + 1].split()
        job = Job(j_id)
        num_ops = int(job_line[0])

        ptr = 1
        for op_id in range(num_ops):
            op = Operation(j_id, op_id)
            num_alt = int(job_line[ptr])
            ptr += 1
            for _ in range(num_alt):
                # 데이터셋의 기계 번호는 1부터 시작하므로 -1을 해줍니다 (0-based)
                m_id = int(job_line[ptr]) - 1
                ptime = int(job_line[ptr + 1])
                op.add_alternative(m_id, ptime)
                ptr += 2
            job.add_operation(op)
        inst.jobs.append(job)

    inst.compute_job_idx()
    return inst


def generate_random_solution(instance: Instance) -> Tuple[List[int], List[int]]:
    job_seq = []
    machine_seq = []

    for job in instance.jobs:
        for op in job.operations:
            job_seq.append(job.job_id)
            # 해당 공정에서 선택 가능한 대안 기계 중 랜덤
            machine_seq.append(random.randint(0, len(op.alternatives) - 1))

    # 작업 순서(OS)를 무작위로 섞음
    random.shuffle(job_seq)

    return job_seq, machine_seq


def save_event_log(event_log: List[str], path: Path) -> None:
    path.write_text("\n".join(event_log), encoding="utf-8")


def main():

    data_dir = Path("Brandimarte_Data/Text")
    results_dir = Path("results")
    fjs_files = sorted(data_dir.glob("Mk*.fjs"))

    for file_path in fjs_files:
        inst_name = file_path.stem
        print(f"▶ [{inst_name}] 인스턴스 테스트")

        instance = read_fjsp_instance(file_path)
        inst_out_dir = results_dir / inst_name
        inst_out_dir.mkdir(exist_ok=True)

        sample_OS, sample_MS = generate_random_solution(instance)

        schedule_calc = decode_calc(instance, sample_OS, sample_MS)
        mk_calc = makespan(schedule_calc)

        schedule_debs, event_log = decode_debs(instance, sample_OS, sample_MS)
        mk_debs = makespan(schedule_debs)

        print(f"  - 기존 Makespan: {mk_calc}")
        print(f"  - DEBS Makespan: {mk_debs}")
        if mk_calc != mk_debs:
            print(" 다르다")
        else:
            print(" 같다")

        log_path = inst_out_dir / f"{inst_name}_event_log.txt"
        calc_gantt_path = inst_out_dir / f"{inst_name}_calc_gantt.html"
        debs_gantt_path = inst_out_dir / f"{inst_name}_debs_gantt.html"

        save_event_log(event_log, log_path)

        viz_plotly.plot_gantt_plotly(instance, schedule_calc, str(calc_gantt_path))
        viz_plotly.plot_gantt_plotly(instance, schedule_debs, str(debs_gantt_path))


if __name__ == "__main__":
    main()
