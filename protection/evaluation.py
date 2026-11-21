"""Strategy-neutral budget, connectivity and worst-attack evaluation."""
import time
from protection.attacks import prepare_attacks, surviving_ids
from protection.flow import maximum_delivery
from protection.errors import DeadlineExceeded
from protection.models import Evaluation
from protection.errors import EvaluationError, InvalidProtectionError
from protection.models import Scenario, integer, require


def budget_for(scenario: Scenario, percent: int) -> int:
    """Return the floored 20% or 40% budget without floating-point arithmetic."""
    integer(percent, 'percent')
    require(percent in (20, 40), 'percent must be 20 or 40')
    return sum(edge.cost for edge in scenario.edges) * percent // 100


def validate_protection(scenario: Scenario, budget: int, edge_ids: list[int]) -> int:
    """Validate a submission without sorting/coercing it; return its total cost."""
    if type(budget) is not int or budget < 0:
        raise InvalidProtectionError('budget must be a nonnegative integer (not bool)')
    if type(edge_ids) is not list:
        raise InvalidProtectionError('protection must be a list[int]')
    previous = -1
    cost = 0
    for edge_id in edge_ids:
        if type(edge_id) is not int or not 0 <= edge_id < len(scenario.edges):
            raise InvalidProtectionError('edge id must be an existing integer id (not bool)')
        if edge_id <= previous:
            raise InvalidProtectionError('edge ids must be strictly increasing and unique')
        previous = edge_id
        cost += scenario.edges[edge_id].cost
    if cost > budget:
        raise InvalidProtectionError('protection cost exceeds budget')
    return cost


def connected_pairs(scenario: Scenario, surviving_ids: tuple[int, ...]) -> int:
    """Count unordered connected node pairs, retaining isolated nodes.

    Internal surviving IDs may be a tuple or list, strictly increasing and
    unique. Invalid internal graph selections raise EvaluationError. Each
    component contributes s*(s-1)//2; the full-graph count n*(n-1)//2 is also
    the denominator to use when displaying the connected ratio.
    """
    if type(surviving_ids) not in (tuple, list):
        raise EvaluationError('surviving ids must be a tuple or list')
    n = len(scenario.nodes)
    total_pairs = n * (n - 1) // 2
    adjacent = [[] for _ in range(n)]
    previous = -1
    for edge_id in surviving_ids:
        if type(edge_id) is not int or not 0 <= edge_id < len(scenario.edges):
            raise EvaluationError('surviving edge id must be an existing integer id (not bool)')
        if edge_id <= previous:
            raise EvaluationError('surviving ids must be strictly increasing and unique')
        previous = edge_id
        edge = scenario.edges[edge_id]
        adjacent[edge.u].append(edge.v)
        adjacent[edge.v].append(edge.u)

    visited = set()
    pairs = 0
    for node in range(n):
        if node in visited:
            continue
        visited.add(node)
        stack = [node]
        size = 0
        while stack:
            current = stack.pop()
            size += 1
            for neighbor in adjacent[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        if size == n:
            return total_pairs
        pairs += size * (size - 1) // 2
    return pairs


class Evaluator:
    """One execution's private cache; only fully scored residual networks enter it.

    All connectivity scores are computed before any flow solve. Coordinates
    break attack ties, not traversal order. A new instance starts cold.
    """

    def __init__(self, scenario, prepared=None, *, use_cache=True, require_certificate=False):
        self.scenario = scenario
        self.prepared = prepare_attacks(scenario) if prepared is None else prepared
        if (self.prepared.scenario_id != scenario.scenario_id
                or self.prepared.attack_settings != scenario.attack_settings
                or self.prepared.policy_version != scenario.evaluation_policy.version):
            raise EvaluationError('prepared attacks do not match scenario/policy')
        for candidate in self.prepared.candidates:
            if any(i >= len(scenario.edges) for i in candidate.damaged_edge_ids):
                raise EvaluationError('prepared attack contains unknown edge')
        self.use_cache = use_cache
        self.require_certificate = require_certificate
        self._cache = {}
        self.cache_hits = 0
        self.evaluation_calls = 0
        self.last_diagnostics = ()
        self.fallback_solves = 0
        if require_certificate:
            self._all_edges = (1 << len(scenario.edges)) - 1
            self._attack_masks = {}
            self._connections = {}
            for candidate in self.prepared.candidates:
                mask = sum(1 << edge_id for edge_id in candidate.damaged_edge_ids)
                self._attack_masks.setdefault(mask, candidate)

    @property
    def cache_size(self):
        return len(self._cache)

    @staticmethod
    def _check_deadline(deadline):
        if deadline is not None and time.monotonic() >= deadline:
            raise DeadlineExceeded('evaluation deadline expired')

    def _certified_attack_outcomes(self, edge_ids):
        # 생존 간선이 같으면 점수도 같다. 좌표순 동점 규칙에 따라 첫 공격 위치만 보존한다.
        protected = sum(1 << edge_id for edge_id in edge_ids)
        vulnerable = self._all_edges ^ protected
        survivors = {}
        for damaged, candidate in self._attack_masks.items():
            mask = self._all_edges ^ (damaged & vulnerable)
            survivors.setdefault(mask, candidate)
        for mask, candidate in survivors.items():
            if mask not in self._connections:
                remaining = tuple(edge.id for edge in self.scenario.edges if mask & (1 << edge.id))
                self._connections[mask] = connected_pairs(self.scenario, remaining), remaining
            pairs, remaining = self._connections[mask]
            yield pairs, candidate, remaining

    def evaluate(self, edge_ids, budget, *, deadline=None):
        self._check_deadline(deadline)
        cost = validate_protection(self.scenario, budget, edge_ids)
        self.evaluation_calls += 1
        if self.require_certificate:
            candidates = list(self._certified_attack_outcomes(edge_ids))
        else:
            candidates = []
            for candidate in self.prepared.candidates:
                self._check_deadline(deadline)
                remaining = surviving_ids(self.scenario, candidate, edge_ids)
                candidates.append((connected_pairs(self.scenario, remaining), candidate, remaining))
        minimum = min(pairs for pairs, _, _ in candidates)
        best = None
        diagnostics = []
        for pairs, candidate, remaining in candidates:
            # 연결 쌍이 최소인 공격끼리만 전달량으로 최악의 공격을 가린다.
            if pairs != minimum:
                continue
            self._check_deadline(deadline)
            # 같은 생존 간선 집합은 공격 위치가 달라도 동일한 흐름 문제다.
            key = (self.scenario.scenario_id, sum(1 << i for i in remaining),
                   self.scenario.evaluation_policy.version)
            if self.use_cache and key in self._cache:
                delivery = self._cache[key]
                self.cache_hits += 1
            else:
                if self.require_certificate:
                    delivery = maximum_delivery(self.scenario, remaining, deadline=deadline, require_certificate=True)
                else:
                    delivery = maximum_delivery(self.scenario, remaining, deadline=deadline)
                self._check_deadline(deadline)
                if (delivery.diagnostics is not None and
                        delivery.diagnostics.certificate_status == 'highs_residual_fallback'):
                    self.fallback_solves += 1
                if self.use_cache:
                    self._cache[key] = delivery
            diagnostics.append(delivery.diagnostics)
            attack_key = (delivery.delivery_units, candidate.x, candidate.y)
            if best is None or attack_key < best[0]:
                best = (attack_key, delivery, candidate)
        self._check_deadline(deadline)
        _, delivery, candidate = best
        n = len(self.scenario.nodes)
        self.last_diagnostics = tuple(diagnostics)
        return Evaluation(tuple(edge_ids), cost, minimum, minimum / (n * (n - 1) // 2),
                          delivery.delivered_mbps, delivery.delivery_ratio,
                          delivery.delivery_units, (candidate.x, candidate.y))
