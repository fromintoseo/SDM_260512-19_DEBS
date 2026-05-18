'''

from __future__ import annotations
import heapq
from dataclasses import dataclass, field
from model import ScheduledOp


@dataclass(order=True)
class Event:
    time: float
    seq: int
    job_details: dict = field(compare=False, default_factory=dict)


class EventQueue:
    def __init__(self):
        self._heap = []
        self.event_id = 0

    def push(self, time, job_details):
        heapq.heappush(self._heap, Event(time, self.event_id, job_details))
        self.event_id += 1

    def pop(self):
        return heapq.heappop(self._heap)

    def __bool__(self):
        return bool(self._heap)


class FJSPDebsSimulator:
    def __init__(self, instance, job_seq, machine_seq):
        self.instance = instance
        self.job_seq = list(job_seq)
        self.machine_seq = list(machine_seq)

        self.event_queue = EventQueue()
        self.schedule = []
        self.event_log = []

        self.clock = 0.0

        # 0: IDLE, 1: BUSY
        self.machine_busy = {m.machine_id: 0 for m in instance.machines}
        self.job_busy = {j.job_id: 0 for j in instance.jobs}
        self.machine_status = {m.machine_id: "IDLE" for m in instance.machines}
        self.op_progress_available = {j.job_id: 0 for j in instance.jobs}

        self.waiting_ops = self.make_waiting_ops()

    def make_waiting_ops(self):
        waiting = []
        op_count = {}
        for job_id in self.job_seq:
            op_id = op_count.get(job_id, 0)
            op_count[job_id] = op_id + 1
            idx = self.instance.job_index[job_id] + op_id
            alt_idx = self.machine_seq[idx]
            machine_id, ptime = self.instance.jobs[job_id].operations[op_id].alternatives[alt_idx]
            waiting.append({"job_id": job_id, "op_id": op_id, "machine_id": machine_id, "ptime": ptime})
        return waiting

    def get_machine_status_summary(self):
        status_list = [f"M{machine_id}: {status}" for machine_id, status in sorted(self.machine_status.items())]
        return " [Machine] " + ", ".join(status_list)

    def start_scheduling(self):
        to_start = []
        for op in self.waiting_ops:
            job_id, machine_id, op_id = op["job_id"], op["machine_id"], op["op_id"]

            if op_id != self.op_progress_available[job_id]:
                continue

            if self.job_busy[job_id] == 0 and self.machine_busy[machine_id] == 0:
                to_start.append(op)

                self.job_busy[job_id] = 1
                self.machine_busy[machine_id] = 1
                self.op_progress_available[job_id] += 1
                self.machine_status[machine_id] = f"J{job_id}-O{op_id}"

        if to_start:
            time_prefix = f"[t={self.clock:g}] "
            indent = " " * len(time_prefix)

            for i, op in enumerate(to_start):
                self.waiting_ops.remove(op)
                end_time = self.clock + op["ptime"]
                job_details = {
                    "job_id": op["job_id"],
                    "op_id": op["op_id"],
                    "machine_id": op["machine_id"],
                    "start": self.clock,
                    "end": end_time
                }
                self.event_queue.push(end_time, job_details)

                prefix = time_prefix if i == 0 else indent
                self.event_log.append(
                    f"{prefix}시작: Job {op['job_id']}-Op {op['op_id']} (Machine {op['machine_id']}, 종료예정 t={end_time:g})"
                )
            self.event_log.append(self.get_machine_status_summary()) # Machine 현황

    def run(self):
        self.event_log.append("--- 시뮬레이션 시작 ---")
        self.start_scheduling()

        while self.event_queue:
            event = self.event_queue.pop()
            self.clock = event.time
            p = event.job_details

            job_id, machine_id = p["job_id"], p["machine_id"]

            self.job_busy[job_id] = 0
            self.machine_busy[machine_id] = 0
            self.machine_status[machine_id] = "IDLE"

            self.schedule.append(ScheduledOp(job_id, p["op_id"], machine_id, p["start"], p["end"]))

            self.event_log.append(f"[t={self.clock:g}] 완료: Job {job_id}-Op {p['op_id']} (Machine {machine_id})")
            self.event_log.append(self.get_machine_status_summary())

            # 작업이 끝났으니 다음 작업을 넣을 수 있는지 다시 탐색
            self.start_scheduling()

        self.event_log.append("--- 시뮬레이션 종료 ---")
        return self.schedule

def decode_debs(instance, job_seq, machine_seq):
    sim = FJSPDebsSimulator(instance, job_seq, machine_seq)
    schedule = sim.run()
    return schedule, sim.event_log

'''

from __future__ import annotations
import heapq
from dataclasses import dataclass, field
from model import ScheduledOp


@dataclass(order=True)
class Event:
    time: float
    seq: int
    job_details: dict = field(compare=False, default_factory=dict)


class EventQueue:
    def __init__(self):
        self._heap = []
        self.event_id = 0

    def push(self, time, job_details):
        heapq.heappush(self._heap, Event(time, self.event_id, job_details))
        self.event_id += 1

    def pop(self):
        return heapq.heappop(self._heap)

    def __bool__(self):
        return bool(self._heap)


class FJSPDebsSimulator:
    def __init__(self, instance, job_seq, machine_seq):
        self.instance = instance
        self.job_seq = list(job_seq)
        self.machine_seq = list(machine_seq)

        self.event_queue = EventQueue()
        self.schedule = []
        self.event_log = []
        self.clock = 0.0

        # 기계와 Job의 상태 (0: IDLE, 1: BUSY)
        self.machine_busy = {m.machine_id: 0 for m in instance.machines}
        self.job_busy = {j.job_id: 0 for j in instance.jobs}
        self.completed_ops = {j.job_id: 0 for j in instance.jobs}
        self.machine_status = {m.machine_id: "IDLE" for m in instance.machines}
        self.machine_queues = self.build_machine_queues()

    def build_machine_queues(self):
        queues = {m.machine_id: [] for m in self.instance.machines}
        op_count = {}

        for job_id in self.job_seq:
            op_id = op_count.get(job_id, 0)
            op_count[job_id] = op_id + 1

            idx = self.instance.job_index[job_id] + op_id
            alt_idx = self.machine_seq[idx]
            machine_id, ptime = self.instance.jobs[job_id].operations[op_id].alternatives[alt_idx]

            # 각 기계의 Queue에 추가
            queues[machine_id].append({
                "job_id": job_id, "op_id": op_id, "ptime": ptime
            })
        return queues

    def get_machine_status_summary(self):
        status_list = [f"M{machine_id}: {status}" for machine_id, status in sorted(self.machine_status.items())]
        return " [Machine] " + ", ".join(status_list)

    def start_scheduling(self):
        starts = []
        # 모든 기계를 순회하며 IDLE 체크
        for machine_id, queue in self.machine_queues.items():
            if self.machine_busy[machine_id] == 0 and len(queue) > 0:

                next_task = queue[0]
                job_id, op_id = next_task["job_id"], next_task["op_id"]

                # 선행 공정이 완료되었고(completed_ops), 해당 Job이 놀고 있다면(job_busy)
                if op_id == self.completed_ops[job_id] and self.job_busy[job_id] == 0:
                    queue.pop(0)
                    starts.append((machine_id, next_task))

        if starts:
            time_prefix = f"[t={self.clock:g}] "
            indent = " " * len(time_prefix)

            for i, (machine_id, task) in enumerate(starts):
                job_id, op_id, ptime = task["job_id"], task["op_id"], task["ptime"]

                self.job_busy[job_id] = 1
                self.machine_busy[machine_id] = 1
                self.machine_status[machine_id] = f"J{job_id}-O{op_id}"

                # 종료시간 계산
                end_time = self.clock + ptime

                self.event_queue.push(end_time, {
                    "job_id": job_id, "op_id": op_id, "machine_id": machine_id,
                    "start": self.clock, "end": end_time
                })

                prefix = time_prefix if i == 0 else indent
                self.event_log.append(
                    f"{prefix}시작: Job {job_id}-Op {op_id} (Machine {machine_id}, 종료예정 t={end_time:g})"
                )
            self.event_log.append(self.get_machine_status_summary())

    def run(self):
        self.event_log.append("--- 시뮬레이션 시작 ---")

        self.start_scheduling()

        while self.event_queue:
            event = self.event_queue.pop()
            self.clock = event.time # pop event의 end time으로 워프
            p = event.job_details

            job_id, machine_id = p["job_id"], p["machine_id"]

            self.completed_ops[job_id] += 1
            self.job_busy[job_id] = 0
            self.machine_busy[machine_id] = 0
            self.machine_status[machine_id] = "IDLE"

            self.schedule.append(ScheduledOp(job_id, p["op_id"], machine_id, p["start"], p["end"]))

            self.event_log.append(f"[t={self.clock:g}] 완료: Job {job_id}-Op {p['op_id']} (Machine {machine_id})")
            self.event_log.append(self.get_machine_status_summary())

            self.start_scheduling()

        self.event_log.append("--- 시뮬레이션 종료 ---")
        return self.schedule


def decode_debs(instance, job_seq, machine_seq):
    sim = FJSPDebsSimulator(instance, job_seq, machine_seq)
    schedule = sim.run()
    return schedule, sim.event_log