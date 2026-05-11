from __future__ import annotations
import heapq
from dataclasses import dataclass, field
from model import ScheduledOp

@dataclass(order=True)
class Event:
    time: float # 시간순서 정렬
    seq: int # 시간 같으면 넣은 순서로
    payload: Dict[str, Any] = field(compare=False, default_factory=dict)


class EventQueue:
    def __init__(self) :
        self._heap = []
        self._seq = 0

    def push(self, time, payload):
        heapq.heappush(self._heap, Event(time, self._seq, payload))
        self._seq += 1

    def pop(self) :
        return heapq.heappop(self._heap) # 가장 time이 작은 이벤트 뽑아서 반환

    def __bool__(self) :
        return bool(self._heap) # 큐가 비어있는지 여부

class FJSPDebsSimulator:
    def __init__(self, instance, job_seq, machine_seq):
        self.instance = instance
        self.job_seq = list(job_seq)
        self.machine_seq = list(machine_seq)

        self.event_queue = EventQueue()
        self.op_count = {} # 각 Job이 현재 몇 번째 Operation까지 진행되었는지

        self.job_ready = {} # 각 Job이 다음에 언제 작업을 시작할 수 있는지(이전 작업이 끝난 시간)
        self.machine_ready = {} # 언제 다음 작업 가능한지

        self.schedule = []
        self.event_log = []

    def schedule_event(self, time, payload):
        self.event_queue.push(time, payload)

    def plan_operations_from_chromosome(self):

        for gene_idx, job_id in enumerate(self.job_seq):
            op_id = self.op_count.get(job_id, 0)
            self.op_count[job_id] = op_id + 1 # 몇 번째 op인지 가져와서 증가

            op_idx = self.instance.job_index[job_id] + op_id
            alt_idx = self.machine_seq[op_idx]

            operation = self.instance.jobs[job_id].operations[op_id]
            machine_id, ptime = operation.alternatives[alt_idx]

            start = max(self.job_ready.get(job_id, 0), self.machine_ready.get(machine_id, 0))
            end = start + ptime

            self.job_ready[job_id] = end
            self.machine_ready[machine_id] = end

            payload = {
                "gene_idx": gene_idx, "job_id": job_id, "op_id": op_id,
                "mid": machine_id, "start": start, "end": end, "ptime": ptime,
            }
            self.schedule_event(end, payload)

            self.event_log.append(
                f"OP_FINISH(t={end:g}) : Job {job_id}, Op {op_id}, Machine {machine_id},{start:g} ~ {end:g} (ptime: {ptime:g})\n"
            )

    def run(self):
        self.plan_operations_from_chromosome()
        # 큐에서 완료 시간이 빠른 순서대로 꺼내어 스케줄 append
        while self.event_queue: # __bool__이 true인 동안
            event = self.event_queue.pop()
            p = event.payload
            op = ScheduledOp(p["job_id"], p["op_id"], p["mid"], p["start"], p["end"])
            self.schedule.append(op)

            self.event_log.append(
                f" t={event.time:g} | Job {p['job_id']}-Op {p['op_id']} 끝 (Machine {p['mid']})\n"
            )
        return self.schedule

def decode_debs(instance, job_seq, machine_seq):
    sim = FJSPDebsSimulator(instance, job_seq, machine_seq)
    schedule = sim.run()
    return schedule, sim.event_log