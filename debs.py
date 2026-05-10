"""DEBS based decoder for Flexible Job Shop Scheduling Problem (FJSP).

This module intentionally uses only the event-engine idea:
    - priority queue
    - Event(time, type, payload)
    - schedule_event() / run() loop

It does NOT use arrival queue, FIFO, SPT, LPT, or dispatching-rule logic.
The chromosome already decides the job order and machine assignment.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from math import inf
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from model import ScheduledOp  # type: ignore
except Exception:  # pragma: no cover - fallback for standalone testing
    @dataclass
    class ScheduledOp:  # type: ignore
        job_id: int
        op_id: int
        mid: int
        start: float
        end: float


OP_FINISH = "OP_FINISH"


@dataclass(order=True)
class Event:
    """Priority queue event.

    seq is included only to make ordering deterministic when two events have the
    same time.
    """

    time: float
    seq: int
    type: str = field(compare=False)
    payload: Dict[str, Any] = field(compare=False, default_factory=dict)


class EventQueue:
    def __init__(self) -> None:
        self._heap: List[Event] = []
        self._seq = 0

    def push(self, time: float, event_type: str, payload: Dict[str, Any]) -> None:
        heapq.heappush(self._heap, Event(time=time, seq=self._seq, type=event_type, payload=payload))
        self._seq += 1

    def pop(self) -> Event:
        return heapq.heappop(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)


class FJSPDebsSimulator:
    """Small DEBS simulator that reproduces the calc decoder result.

    Important point:
    FJSP chromosome decoding is gene-order based, not arrival-queue based.
    Therefore, while scanning genes, we reserve each job/machine's next available
    time immediately. OP_FINISH events are still pushed and later popped in time
    order to build the event-based schedule/log.
    """

    def __init__(self, instance: Any, job_seq: List[int], machine_seq: List[int], log_enabled: bool = False) -> None:
        if len(job_seq) != len(machine_seq):
            raise ValueError(f"job_seq and machine_seq length mismatch: {len(job_seq)} != {len(machine_seq)}")

        self.instance = instance
        self.job_seq = list(job_seq)
        self.machine_seq = list(machine_seq)
        self.log_enabled = log_enabled

        self.event_queue = EventQueue()
        self.op_count: Dict[int, int] = {}

        # These are reservation states used while reading the chromosome.
        self.job_ready: Dict[int, float] = {}
        self.machine_ready: Dict[int, float] = {}

        self.schedule: List[ScheduledOp] = []
        self.event_log: List[str] = []

    def schedule_event(self, time: float, event_type: str, payload: Dict[str, Any]) -> None:
        self.event_queue.push(time, event_type, payload)

    def plan_operations_from_chromosome(self) -> None:
        """Read genes and create OP_FINISH events.

        This part mirrors decode_calc:
            start = max(job_ready[job_id], machine_ready[mid])
            end   = start + ptime(job_id, op_id, mid)
        """
        for gene_idx, (job_id, mid) in enumerate(zip(self.job_seq, self.machine_seq)):
            op_id = self.op_count.get(job_id, 0)
            self.op_count[job_id] = op_id + 1

            ptime = get_processing_time(self.instance, job_id, op_id, mid)
            if ptime is None or ptime == inf:
                raise ValueError(f"Infeasible or missing ptime: gene={gene_idx}, job={job_id}, op={op_id}, machine={mid}")

            start = max(self.job_ready.get(job_id, 0), self.machine_ready.get(mid, 0))
            end = start + ptime

            # Reserve availability immediately so the next gene sees the same
            # state as decode_calc.
            self.job_ready[job_id] = end
            self.machine_ready[mid] = end

            payload = {
                "gene_idx": gene_idx,
                "job_id": job_id,
                "op_id": op_id,
                "mid": mid,
                "start": start,
                "end": end,
                "ptime": ptime,
            }
            self.schedule_event(end, OP_FINISH, payload)

            if self.log_enabled:
                self.event_log.append(
                    f"PLAN  t={start:g}->{end:g} | gene={gene_idx} | J{job_id}-O{op_id} on M{mid}"
                )

    def run(self) -> List[ScheduledOp]:
        self.plan_operations_from_chromosome()

        while self.event_queue:
            event = self.event_queue.pop()
            if event.type == OP_FINISH:
                self.handle_op_finish(event)
            else:
                raise ValueError(f"Unknown event type: {event.type}")

        return self.schedule

    def handle_op_finish(self, event: Event) -> None:
        p = event.payload
        op = make_scheduled_op(
            job_id=p["job_id"],
            op_id=p["op_id"],
            mid=p["mid"],
            start=p["start"],
            end=p["end"],
        )
        self.schedule.append(op)

        if self.log_enabled:
            self.event_log.append(
                f"FINISH t={event.time:g} | gene={p['gene_idx']} | J{p['job_id']}-O{p['op_id']} on M{p['mid']}"
            )


def decode_debs(instance: Any, job_seq: List[int], machine_seq: List[int]) -> List[ScheduledOp]:
    """Decode FJSP chromosome using an event queue.

    Returns
    -------
    schedule : List[ScheduledOp]
        Each item has job_id, op_id, mid, start, end.
    """
    sim = FJSPDebsSimulator(instance, job_seq, machine_seq, log_enabled=False)
    return sim.run()


def decode_debs_with_log(instance: Any, job_seq: List[int], machine_seq: List[int]) -> Tuple[List[ScheduledOp], List[str]]:
    """Optional helper for debugging/event-log submission."""
    sim = FJSPDebsSimulator(instance, job_seq, machine_seq, log_enabled=True)
    schedule = sim.run()
    return schedule, sim.event_log


def make_scheduled_op(job_id: int, op_id: int, mid: int, start: float, end: float) -> ScheduledOp:
    """Create ScheduledOp while tolerating small constructor differences."""
    try:
        return ScheduledOp(job_id, op_id, mid, start, end)  # type: ignore[misc, call-arg]
    except TypeError:
        try:
            return ScheduledOp(job_id=job_id, op_id=op_id, mid=mid, start=start, end=end)  # type: ignore[misc, call-arg]
        except TypeError:
            # Some projects use operation_id/machine_id names.
            return ScheduledOp(job_id=job_id, operation_id=op_id, machine_id=mid, start=start, end=end)  # type: ignore[misc, call-arg]


def get_processing_time(instance: Any, job_id: int, op_id: int, mid: int) -> Optional[float]:
    """Return processing time p(job, operation, machine).

    The exact Instance structure differs by project, so this accessor supports
    several common forms:
        1) instance.get_processing_time(job_id, op_id, mid)
        2) instance.ptime[(job_id, op_id, mid)]
        3) instance.ptime[job_id][op_id][mid]
        4) instance.jobs[job_id].operations[op_id].ptime[mid]
    If your model.py has a single known format, you may simplify this function.
    """
    for method_name in ("get_processing_time", "processing_time", "get_ptime"):
        method = getattr(instance, method_name, None)
        if callable(method):
            value = method(job_id, op_id, mid)
            return None if value is None else float(value)

    for attr_name in ("ptime", "processing_times", "proc_times"):
        table = getattr(instance, attr_name, None)
        value = lookup_ptime_table(table, job_id, op_id, mid)
        if value is not None:
            return float(value)

    jobs = getattr(instance, "jobs", None)
    if jobs is not None:
        try:
            job = jobs[job_id]
            operations = getattr(job, "operations", job)
            op = operations[op_id]
            for attr_name in ("ptime", "processing_times", "proc_times"):
                table = getattr(op, attr_name, None)
                if table is not None:
                    if isinstance(table, dict):
                        return float(table.get(mid, inf))
                    return float(table[mid])
        except Exception:
            pass

    raise AttributeError(
        "Cannot find processing time. Please adapt get_processing_time() to your Instance structure."
    )


def lookup_ptime_table(table: Any, job_id: int, op_id: int, mid: int) -> Optional[float]:
    if table is None:
        return None

    if isinstance(table, dict):
        # Flat dict: {(job, op, machine): time}
        for key in ((job_id, op_id, mid), (job_id, op_id, str(mid)), (str(job_id), str(op_id), str(mid))):
            if key in table:
                return table[key]

        # Nested dict: ptime[job][op][machine]
        try:
            level1 = table[job_id]
        except KeyError:
            try:
                level1 = table[str(job_id)]
            except KeyError:
                return None

        try:
            level2 = level1[op_id]
        except Exception:
            try:
                level2 = level1[str(op_id)]
            except Exception:
                return None

        if isinstance(level2, dict):
            return level2.get(mid, level2.get(str(mid)))
        return level2[mid]

    # List/tuple/ndarray style: ptime[job][op][machine]
    try:
        return table[job_id][op_id][mid]
    except Exception:
        return None
