"""Read-only submission context and bounded JSON transport (no return unpickling)."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import select
import struct
import time
from protection.errors import DeadlineExceeded, EvaluationError, InvalidProtectionError
from protection.models import strict_json_loads

MAX_FRAME_BYTES = 16 * 1024 * 1024


class ProtocolError(RuntimeError):
    pass


class JsonChannel:
    """Incremental nonblocking frames. One read/write quantum is at most 64 KiB.

    Supervisors must call step rather than recv: an incomplete header/body must
    never prevent deadline/RSS observation. Completion timestamps precede JSON
    decoding. Spawn arguments are trusted infrastructure, not submission results.
    """
    def __init__(self, sock, run_id):
        self.sock = sock
        sock.setblocking(False)
        self.run_id = run_id
        self.incoming = bytearray()
        self.outgoing = bytearray()
        self.length = None

    def queue(self, kind, payload=None, request_id=0):
        try:
            body = json.dumps(dict(run_id=self.run_id, request_id=request_id,
                                   type=kind, payload=payload), allow_nan=False,
                              separators=(',', ':')).encode('utf-8')
        except (ValueError, TypeError, RecursionError) as exc:
            raise ProtocolError('non-JSON message') from exc
        if len(body) > MAX_FRAME_BYTES or len(self.outgoing) + len(body) > MAX_FRAME_BYTES + 4:
            raise ProtocolError('frame exceeds 16 MiB')
        self.outgoing.extend(struct.pack('!I', len(body)))
        self.outgoing.extend(body)

    def flush(self):
        if self.outgoing:
            try:
                n = self.sock.send(self.outgoing[:65536])
                del self.outgoing[:n]
            except BlockingIOError:
                pass

    def step(self):
        self.flush()
        needed = 4 - len(self.incoming) if self.length is None else self.length - len(self.incoming)
        try:
            chunk = self.sock.recv(min(65536, needed))
        except BlockingIOError:
            return None
        if not chunk:
            raise EOFError('channel closed before complete message')
        self.incoming.extend(chunk)
        if self.length is None and len(self.incoming) == 4:
            self.length = struct.unpack('!I', self.incoming)[0]
            self.incoming.clear()
            if not 0 < self.length <= MAX_FRAME_BYTES:
                raise ProtocolError('invalid frame length')
            return None
        if self.length is None or len(self.incoming) < self.length:
            return None
        received_ns = time.monotonic_ns()
        raw = bytes(self.incoming)
        self.incoming.clear()
        self.length = None
        try:
            message = strict_json_loads(raw.decode('utf-8'))
            if (type(message) is not dict or set(message) != {'run_id','request_id','type','payload'}
                    or message['run_id'] != self.run_id or type(message['request_id']) is not int
                    or message['request_id'] < 0 or type(message['type']) is not str):
                raise ValueError('invalid envelope')
        except Exception as exc:
            raise ProtocolError('malformed JSON/envelope') from exc
        return message, received_ns

    def recv(self, deadline=None):
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                raise DeadlineExceeded('context deadline expired')
            result = self.step()
            if result is not None:
                return result[0]
            select.select([self.sock], [self.sock] if self.outgoing else [], [], .01)

    def send(self, kind, payload=None, request_id=0):
        self.queue(kind, payload, request_id)
        while self.outgoing:
            self.flush()
            if self.outgoing:
                select.select([], [self.sock], [], .01)

    def close(self):
        self.sock.close()


def validate_ids(scenario, budget, ids):
    """Lightweight contract validation without importing scientific libraries."""
    if type(ids) is not list or len(ids) > len(scenario.edges):
        raise InvalidProtectionError('return/evaluation requires bounded list[int]')
    previous = -1
    cost = 0
    for i in ids:
        if type(i) is not int or not previous < i < len(scenario.edges):
            raise InvalidProtectionError('ids must be existing, sorted, unique integers; bool forbidden')
        previous = i
        cost += scenario.edges[i].cost
    if cost > budget:
        raise InvalidProtectionError('protection exceeds budget')


@dataclass(frozen=True)
class ExecutionContext:
    scenario: object
    budget: int
    limit_seconds: float
    algorithm_seed: int | None
    repeat_index: int
    repeat_count: int
    _t0_ns: int = field(repr=False)
    _evaluator: object = field(repr=False, compare=False)
    _best: list = field(default_factory=lambda: [None], repr=False, compare=False)

    def elapsed_seconds(self):
        return (time.monotonic_ns() - self._t0_ns) / 1e9

    def remaining_seconds(self):
        return max(0.0, self.limit_seconds - self.elapsed_seconds())

    def evaluate(self, edge_ids):
        validate_ids(self.scenario, self.budget, edge_ids)
        if self.remaining_seconds() <= 0:
            raise DeadlineExceeded('context deadline expired')
        # D-005: ordinary in-process call, with the same worker's LP/cache RSS.
        result = self._evaluator.evaluate(edge_ids, self.budget,
            deadline=self._t0_ns / 1e9 + self.limit_seconds)
        def rank(ev):
            return (-ev.connected_pairs, -ev.delivery_units, ev.cost, ev.protected_ids)
        if self._best[0] is None or rank(result) < rank(self._best[0]):
            self._best[0] = result
        return result
