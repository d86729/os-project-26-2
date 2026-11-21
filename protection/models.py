"""Immutable v1 input/record models and strict research serialization."""
from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import math

from protection.errors import EvaluationError, InvalidScenarioError


def require(condition, message):
    if not condition:
        raise InvalidScenarioError(message)


def integer(value, name, minimum=0, maximum=None):
    require(type(value) is int and value >= minimum and
            (maximum is None or value <= maximum), f'{name}: invalid integer {value!r}')


def finite(value, name, minimum=None, maximum=None):
    require(type(value) in (int, float) and math.isfinite(value), f'{name}: finite number required')
    require(minimum is None or value >= minimum, f'{name}: below minimum')
    require(maximum is None or value <= maximum, f'{name}: above maximum')


def fixed_policy(obj):
    for f in fields(obj):
        value = getattr(obj, f.name)
        require(type(value) is type(f.default) and value == f.default,
                f'Unsupported {type(obj).__name__}.{f.name}; version migration required')


@dataclass(frozen=True)
class EvaluationPolicy:
    version: str = 'evaluation-v2'
    rounding: str = 'ROUND_HALF_EVEN'
    decimal_precision: int = 50
    delivery_digits: int = 6
    residual_relative_tolerance: float = 1e-7
    primal_tolerance: float = 1e-9
    dual_tolerance: float = 1e-9
    ipm_tolerance: float = 1e-10
    certificate_denominator_limit: int = 1_000_000_000
    max_solver_attempts: int = 2
    threads: int = 1
    certification: str = 'rational_primal_dual_or_highs_residual_1e-7'

    def __post_init__(self):
        fixed_policy(self)


def coordinate_units(value) -> int:
    with localcontext() as ctx:
        ctx.prec = 50
        value = Decimal(str(value))
        require(value.is_finite(), 'nonfinite coordinate')
        return int(value.quantize(Decimal('0.000000001'), rounding=ROUND_HALF_EVEN) * 10**9)


def rounded_fraction_units(value: Fraction, digits=6) -> int:
    value = Fraction(value) * 10**digits
    whole, remainder = divmod(value.numerator, value.denominator)
    twice = remainder * 2
    return whole + int(twice > value.denominator or (twice == value.denominator and whole % 2 == 1))


def certify_interval(lower: Fraction, upper: Fraction, total: int) -> int:
    if not (total > 0 and 0 <= lower <= upper <= total):
        raise EvaluationError('Invalid primal/dual interval', reason='certificate_failed')
    lo = rounded_fraction_units(lower / total)
    hi = rounded_fraction_units(upper / total)
    if lo != hi:
        raise EvaluationError('Certified interval crosses rounding boundary', reason='numeric_ambiguity')
    return lo


@dataclass(frozen=True)
class GenerationSettings:
    version: str = 'generation-v1'
    alpha: int = 1
    beta: int = 3
    m0: int = 2
    rho: int = 1
    min_distance: float = 1e-9

    def __post_init__(self):
        fixed_policy(self)


@dataclass(frozen=True)
class AttackSettings:
    version: str = 'attack-v1'
    count: int = 1
    radius: float = 0.15
    distance_tolerance: float = 1e-9
    grid_denominator: int = 5
    coordinate_digits: int = 9
    candidate_sources: tuple[str, ...] = ('nodes', 'midpoints', 'grid')

    def __post_init__(self):
        fixed_policy(self)


@dataclass(frozen=True)
class Node:
    id: int
    x: float
    y: float

    def __post_init__(self):
        integer(self.id, 'node id')
        for name in ('x', 'y'):
            v = getattr(self, name)
            finite(v, name, 0)
            require(v < 1, 'coordinates must be <1')
            object.__setattr__(self, name, float(v))


@dataclass(frozen=True)
class Edge:
    id: int
    u: int
    v: int
    capacity_mbps: int
    cost: int

    def __post_init__(self):
        for name in ('id', 'u', 'v'):
            integer(getattr(self, name), name)
        require(self.u < self.v, 'edge requires u<v')
        integer(self.capacity_mbps, 'capacity', 10, 30)
        integer(self.cost, 'cost', 1, 10)


@dataclass(frozen=True)
class Demand:
    id: int
    source: int
    target: int
    amount_mbps: int

    def __post_init__(self):
        for name in ('id', 'source', 'target'):
            integer(getattr(self, name), name)
        require(self.source != self.target, 'demand source==target')
        integer(self.amount_mbps, 'amount', 5, 20)


@dataclass(frozen=True)
class Scenario:
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    demands: tuple[Demand, ...]
    seed: int
    schema_version: int = 1
    scenario_id: str = ''
    generation: GenerationSettings = GenerationSettings()
    attack_settings: AttackSettings = AttackSettings()
    evaluation_policy: EvaluationPolicy = EvaluationPolicy()
    environment: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        integer(self.schema_version, 'schema', 1, 1)
        integer(self.seed, 'seed')
        for name, cls in (('nodes', Node), ('edges', Edge), ('demands', Demand)):
            values = getattr(self, name)
            require(type(values) is tuple and all(type(x) is cls for x in values), name + ': immutable tuple required')
            require(tuple(x.id for x in values) == tuple(range(len(values))), name + ': ids must equal indices')
        n = len(self.nodes)
        require(n >= 3 and len(self.demands) == n, 'n>=3 and exactly n demands required')
        pairs = tuple((e.u, e.v) for e in self.edges)
        require(pairs == tuple(sorted(set(pairs))), 'edges must be unique and sorted')
        require(all(e.v < n for e in self.edges), 'edge endpoint missing')
        demand_pairs = tuple((d.source, d.target) for d in self.demands)
        require(len(set(demand_pairs)) == n, 'duplicate demand pair')
        require(all(max(pair) < n for pair in demand_pairs), 'demand endpoint missing')
        reached = {0}
        while True:
            before = len(reached)
            for u, v in pairs:
                if u in reached or v in reached:
                    reached.update((u, v))
            if len(reached) == before:
                break
        require(len(reached) == n, 'input graph disconnected')
        require(type(self.generation) is GenerationSettings and type(self.attack_settings) is AttackSettings and
                type(self.evaluation_policy) is EvaluationPolicy, 'invalid policy models')
        require(type(self.environment) is tuple and all(type(p) is tuple and len(p) == 2 and
                all(type(x) is str for x in p) for p in self.environment), 'invalid environment')
        require(len({p[0] for p in self.environment}) == len(self.environment), 'duplicate environment key')
        require(type(self.scenario_id) is str, 'invalid scenario_id')
        expected = scenario_hash(self)
        require(not self.scenario_id or self.scenario_id == expected, 'scenario_id mismatch')
        object.__setattr__(self, 'scenario_id', expected)


def environment_tuple(value):
    require(type(value) is tuple and all(type(p) is tuple and len(p) == 2 and
            all(type(x) is str for x in p) for p in value), 'invalid immutable environment')
    require(len({p[0] for p in value}) == len(value), 'duplicate environment key')


def ids_tuple(values):
    require(type(values) is tuple, 'ids require tuple')
    for v in values:
        integer(v, 'edge id')
    require(values == tuple(sorted(set(values))), 'ids must be unique and sorted')


@dataclass(frozen=True)
class SolverDiagnostics:
    success: bool
    status: int
    message: str
    attempts: int
    raw_delivered_mbps: float
    maximum_residual: float
    certified_lower: Fraction | None
    certified_upper: Fraction | None
    certificate_status: str
    elapsed_seconds: float

    def __post_init__(self):
        require(type(self.success) is bool, 'success must be bool')
        require(type(self.message) is str and type(self.certificate_status) is str,
                'diagnostic text must be immutable strings')
        integer(self.status, 'solver status')
        integer(self.attempts, 'attempts', 1, 2)
        for name in ('raw_delivered_mbps', 'maximum_residual', 'elapsed_seconds'):
            finite(getattr(self, name), name, 0)
        if self.certificate_status == 'highs_residual_fallback':
            require(self.success and self.status == 0 and self.maximum_residual <= 1e-7,
                    'fallback requires converged solver and small residual')
            require(self.certified_lower is None and self.certified_upper is None,
                    'fallback is not a rational certificate')
        else:
            require(type(self.certified_lower) is Fraction and type(self.certified_upper) is Fraction,
                    'exact fractions required')
            require(0 <= self.certified_lower <= self.certified_upper, 'invalid certificate interval')


@dataclass(frozen=True)
class Evaluation:
    protected_ids: tuple[int, ...]
    cost: int
    connected_pairs: int
    connected_ratio: float
    delivered_mbps: float
    delivery_ratio: float
    delivery_units: int
    worst_attack: tuple[float, float]

    def __post_init__(self):
        ids_tuple(self.protected_ids)
        integer(self.cost, 'cost')
        integer(self.connected_pairs, 'connected_pairs')
        integer(self.delivery_units, 'delivery_units', 0, 1000000)
        finite(self.connected_ratio, 'connected_ratio', 0, 1)
        finite(self.delivery_ratio, 'delivery_ratio', 0, 1)
        finite(self.delivered_mbps, 'delivered_mbps', 0)
        require(type(self.worst_attack) is tuple and len(self.worst_attack) == 2, 'attack tuple required')
        for coordinate in self.worst_attack:
            finite(coordinate, 'attack coordinate', 0, 1)

    @property
    def score(self):
        return self.connected_pairs, self.delivery_units

    @property
    def defender_key(self):
        return -self.connected_pairs, -self.delivery_units, self.cost, self.protected_ids


@dataclass(frozen=True)
class UpperBound:
    connected_pairs: int
    delivery_units: int
    source: str
    certified: bool

    def __post_init__(self):
        integer(self.connected_pairs, 'pairs')
        integer(self.delivery_units, 'units', 0, 1000000)
        require(self.source in ('all_protected', 'optimistic_remaining', 'universal'), 'invalid upper bound source')
        require(type(self.certified) is bool, 'certified must be bool')


@dataclass(frozen=True)
class ExperimentCondition:
    scenario_id: str
    budget_percent: int
    budget: int
    method: str
    limit_seconds: float
    algorithm_memory_limit_bytes: int | None = None

    def __post_init__(self):
        validate_hash(self.scenario_id)
        integer(self.budget_percent, 'percent')
        require(self.budget_percent in (20, 40), 'percent must be 20 or 40')
        integer(self.budget, 'budget')
        finite(self.limit_seconds, 'limit', 0)
        require(self.limit_seconds > 0, 'limit must be positive')
        require(self.method in ('exhaustive', 'branch_bound', 'member_1', 'member_2', 'member_3'), 'invalid method')
        if self.method in ('exhaustive', 'branch_bound'):
            require(self.algorithm_memory_limit_bytes is None, 'exact search has no member memory limit')
        elif self.algorithm_memory_limit_bytes is not None:
            integer(self.algorithm_memory_limit_bytes, 'memory limit', 1)


@dataclass(frozen=True)
class OptimalReference:
    protected_ids: tuple[int, ...]
    cost: int
    evaluation: Evaluation
    exact_run_id: str
    environment: tuple[tuple[str, str], ...]
    limit_seconds: float
    search_seconds: float
    method: str = 'exhaustive'
    status: str = 'completed'
    optimality_proven: bool = True

    def __post_init__(self):
        ids_tuple(self.protected_ids)
        integer(self.cost, 'cost')
        require(type(self.evaluation) is Evaluation and self.protected_ids == self.evaluation.protected_ids
                and self.cost == self.evaluation.cost, 'reference/evaluation mismatch')
        require(self.method == 'exhaustive' and self.status == 'completed' and self.optimality_proven is True,
                'only completed exhaustive results are references')
        require(type(self.exact_run_id) is str and bool(self.exact_run_id), 'exact_run_id required')
        environment_tuple(self.environment)
        finite(self.limit_seconds, 'limit_seconds', 0)
        finite(self.search_seconds, 'search_seconds', 0)
        require(self.limit_seconds > 0 and self.search_seconds <= self.limit_seconds, 'invalid reference timing')
        require(type(self.environment) is tuple, 'environment tuple required')


@dataclass(frozen=True)
class ScenarioBundle:
    scenario: Scenario
    budget_percent: int
    budget: int
    case_id: str = ''
    optimal_reference: OptimalReference | None = None
    schema_version: int = 1

    def __post_init__(self):
        integer(self.schema_version, 'schema', 1, 1)
        require(type(self.scenario) is Scenario, 'Scenario required')
        integer(self.budget_percent, 'percent')
        require(self.budget_percent in (20, 40), 'percent must be 20 or 40')
        integer(self.budget, 'budget')
        require(self.budget == sum(e.cost for e in self.scenario.edges) * self.budget_percent // 100,
                'budget does not match percent')
        require(self.optimal_reference is None or type(self.optimal_reference) is OptimalReference,
                'invalid reference')
        expected = case_hash(self)
        require(type(self.case_id) is str and (not self.case_id or self.case_id == expected), 'case_id mismatch')
        object.__setattr__(self, 'case_id', expected)
        if self.optimal_reference is not None:
            r = self.optimal_reference
            require(all(i < len(self.scenario.edges) for i in r.protected_ids), 'reference edge missing')
            require(sum(self.scenario.edges[i].cost for i in r.protected_ids) == r.cost <= self.budget,
                    'reference budget/cost invalid')

    def algorithm_input(self):
        return self.scenario, self.budget


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    condition: ExperimentCondition
    case_id: str = ''
    schema_version: int = 1
    status: str = 'pending'
    termination_reason: str | None = None
    started_at: str | None = None
    environment: tuple[tuple[str, str], ...] = ()
    submitted_protected_ids: tuple[int, ...] | None = None
    submitted_evaluation: Evaluation | None = None
    recovered_protected_ids: tuple[int, ...] | None = None
    recovered_evaluation: Evaluation | None = None
    best_protected_ids: tuple[int, ...] | None = None
    best_evaluation: Evaluation | None = None
    upper_bound: UpperBound | None = None
    optimality_proven: bool = False
    evaluated_combinations: int = 0
    evaluation_calls: int = 0
    cache_hits: int = 0
    search_seconds: float | None = None
    preparation_seconds: float | None = None
    final_scoring_seconds: float | None = None
    shutdown_seconds: float | None = None
    exact_peak_rss_bytes: int | None = None
    algorithm_peak_rss_bytes: int | None = None
    evaluation_peak_rss_bytes: int | None = None
    algorithm_memory_limit_bytes: int | None = None
    memory_measurement_method: str | None = None
    algorithm_peak_memory_bytes: int | None = None
    algorithm_vcpu_limit: int | None = None
    checkpoint_received_elapsed: float | None = None
    error_type: str | None = None
    error_message: str | None = None
    solver_diagnostics: SolverDiagnostics | None = None
    algorithm_seed: int | None = None
    repeat_index: int = 0
    repeat_count: int = 1
    run_kind: str = 'smoke'
    policy_version: str = 'evaluation-v2'
    submission_sha256: str | None = None
    t0_monotonic_ns: int | None = None
    final_received_monotonic_ns: int | None = None
    deadline_monotonic_ns: int | None = None
    memory_sample_interval_ms: int = 10
    observed_max_sample_gap_ms: float | None = None
    resource_monitor_supported: bool = False
    events: tuple[str, ...] = ()
    launch_status: str = 'not_started'

    def __post_init__(self):
        integer(self.schema_version, 'schema', 1, 1)
        environment_tuple(self.environment)
        require(type(self.events) is tuple and all(type(x) is str for x in self.events), 'events must be immutable strings')
        require(type(self.run_id) is str and bool(self.run_id), 'run_id required')
        require(type(self.case_id) is str, 'case_id must be a string')
        if self.case_id:
            validate_hash(self.case_id)
        if self.submission_sha256 is not None:
            validate_hash(self.submission_sha256)
        if self.algorithm_vcpu_limit is not None:
            integer(self.algorithm_vcpu_limit, 'vCPU limit', 1)
        require(self.upper_bound is None or type(self.upper_bound) is UpperBound, 'invalid upper_bound')
        require(self.solver_diagnostics is None or type(self.solver_diagnostics) is SolverDiagnostics, 'invalid solver diagnostics')
        require(type(self.condition) is ExperimentCondition, 'condition required')
        require(self.status in ('pending', 'running', 'completed', 'timeout', 'failed', 'not_implemented', 'memory_limit'), 'invalid status')
        require(self.launch_status in ('started', 'not_started'), 'invalid launch_status')
        require(self.run_kind in ('smoke', 'main', 'scale_probe'), 'invalid run_kind')
        for name in ('optimality_proven', 'resource_monitor_supported'):
            require(type(getattr(self, name)) is bool, name + ' must be bool')
        for name in ('evaluated_combinations', 'evaluation_calls', 'cache_hits', 'repeat_index', 'repeat_count', 'memory_sample_interval_ms'):
            integer(getattr(self, name), name)
        require(self.repeat_count in (1, 5) and self.repeat_index < self.repeat_count, 'invalid repeat metadata')
        if self.repeat_count == 1:
            require(self.algorithm_seed is None, 'deterministic seed must be null')
        else:
            integer(self.algorithm_seed, 'algorithm_seed')
        for f in fields(self):
            v = getattr(self, f.name)
            if v is None:
                continue
            if f.name.endswith(('_bytes', '_ns')):
                integer(v, f.name)
            if f.name.endswith('_seconds') or f.name in ('checkpoint_received_elapsed', 'observed_max_sample_gap_ms'):
                finite(v, f.name, 0)
        for prefix in ('submitted', 'recovered', 'best'):
            ids, ev = getattr(self, prefix + '_protected_ids'), getattr(self, prefix + '_evaluation')
            if ids is not None:
                ids_tuple(ids)
            if ev is not None:
                require(type(ev) is Evaluation and ev.protected_ids == ids, prefix + ' evaluation mismatch')
        if self.status != 'completed':
            require(self.submitted_evaluation is None and not self.optimality_proven, 'incomplete has no official score or proof')
        exact = self.condition.method in ('exhaustive', 'branch_bound')
        if not exact:
            require(self.best_protected_ids is None and self.best_evaluation is None and self.upper_bound is None
                    and not self.optimality_proven, 'member record cannot contain exact incumbent/proof')
        else:
            require(self.submitted_protected_ids is None and self.submitted_evaluation is None, 'exact uses best fields')
        if self.status == 'completed':
            require((self.best_evaluation if exact else self.submitted_evaluation) is not None, 'completed needs actual evaluation')

    def transition(self, status, **changes):
        from dataclasses import replace
        allowed = {'pending': {'running', 'failed'},
                   'running': {'completed', 'timeout', 'failed', 'not_implemented', 'memory_limit'}}
        require(status in allowed.get(self.status, set()), 'invalid state transition')
        return replace(self, status=status, **changes)


def to_data(value):
    from dataclasses import is_dataclass
    if is_dataclass(value):
        return {f.name: to_data(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Fraction):
        return {'numerator': value.numerator, 'denominator': value.denominator}
    if type(value) in (tuple, list):
        return [to_data(v) for v in value]
    if type(value) is dict:
        return {k: to_data(v) for k, v in value.items()}
    if type(value) is float:
        require(math.isfinite(value), 'nonfinite JSON')
    require(value is None or type(value) in (str, bool, int, float), 'unsupported JSON value')
    return value


def from_data(cls, data):
    from dataclasses import is_dataclass
    from types import UnionType
    from typing import get_args, get_origin, get_type_hints
    origin, args = get_origin(cls), get_args(cls)
    if origin is UnionType:
        if data is None and type(None) in args:
            return None
        for candidate in args:
            if candidate is type(None):
                continue
            try:
                return from_data(candidate, data)
            except (InvalidScenarioError, TypeError, ValueError):
                pass
        raise InvalidScenarioError('union field type mismatch')
    if origin is tuple:
        require(type(data) is list, 'JSON array required')
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(from_data(args[0], v) for v in data)
        require(len(data) == len(args), 'tuple length mismatch')
        return tuple(from_data(t, v) for t, v in zip(args, data))
    if cls is Fraction:
        keys(data, {'numerator', 'denominator'})
        require(type(data['numerator']) is int, 'integer numerator required')
        integer(data['denominator'], 'denominator', 1)
        return Fraction(data['numerator'], data['denominator'])
    if is_dataclass(cls):
        names = {f.name for f in fields(cls)}
        optional = {
            ScenarioBundle: {'optimal_reference'},
            RunRecord: {'algorithm_peak_memory_bytes', 'algorithm_vcpu_limit'},
        }.get(cls, set())
        keys(data, names - optional, optional)
        hints = get_type_hints(cls)
        return cls(**{k: from_data(hints[k], v) for k, v in data.items()})
    if cls is float:
        finite(data, 'float field')
        return float(data)
    require(type(data) is cls, f'expected {cls}')
    return data


def keys(data, required, optional=frozenset()):
    require(type(data) is dict, 'object required')
    require(required <= data.keys() and data.keys() <= required | optional,
            f'wrong keys: missing={required-data.keys()}, unknown={data.keys()-required-optional}')


@dataclass(frozen=True)
class ExperimentManifest:
    # Canonical string ensures nested manifest data cannot be mutated by consumers.
    payload_json: str
    source_path: str

    def to_dict(self):
        import json
        return json.loads(self.payload_json)

    @classmethod
    def parse(cls, data, source_path):
        import json
        from pathlib import Path
        d = json.loads(json.dumps(data, allow_nan=False))
        common = {'schema_version', 'kind', 'run_kind', 'owners', 'output_dir'}
        preparation = {'sizes', 'size_groups', 'seeds_by_size', 'budget_percents', 'exact_methods', 'limits'}
        grading = {'bank', 'submission', 'limits', 'resource_policy'}
        require(type(d) is dict and d.get('kind') in ('preparation', 'grading'), 'invalid manifest kind')
        keys(d, common | (preparation if d['kind'] == 'preparation' else grading), {'ready'})
        integer(d['schema_version'], 'schema', 1, 1)
        require(d['run_kind'] in ('smoke', 'main', 'scale_probe'), 'invalid run_kind')
        require(type(d.get('ready', True)) is bool and d.get('ready', True), 'manifest not ready')
        require(type(d['owners']) is dict and bool(d['owners']) and all(type(k) is str and type(v) is str and
                bool(k.strip()) and bool(v.strip()) for k, v in d['owners'].items()), 'owners required')
        base = Path(source_path).resolve().parent
        def path(value):
            require(type(value) is str and bool(value.strip()), 'nonempty path required')
            return str((base / value).resolve())
        def seeds(values, count=None):
            require(type(values) is list and (count is None or len(values) == count), 'invalid seed count')
            for value in values:
                integer(value, 'seed')
            require(len(values) == len(set(values)), 'duplicate seeds')
        d['output_dir'] = path(d['output_dir'])
        if d['kind'] == 'preparation':
            require(type(d['sizes']) is list and bool(d['sizes']), 'empty sizes')
            for n in d['sizes']:
                integer(n, 'n', 3)
            require(len(d['sizes']) == len(set(d['sizes'])), 'duplicate sizes')
            size_keys = {str(n) for n in d['sizes']}
            keys(d['size_groups'], size_keys)
            keys(d['seeds_by_size'], size_keys)
            for n in d['sizes']:
                group = d['size_groups'][str(n)]
                require(group in ('small', 'medium_large', 'probe'), 'invalid size group')
                require(group != 'small' or n in (6, 8), 'small size must be 6 or 8')
                require(group != 'probe' or d['run_kind'] == 'scale_probe', 'probe only for scale_probe')
                s = d['seeds_by_size'][str(n)]
                seeds(s)
                require(bool(s), 'empty generation seeds')
            require(d['budget_percents'] == [20, 40] and all(type(v) is int for v in d['budget_percents']), 'both budgets required')
            require(d['exact_methods'] == ['exhaustive', 'branch_bound'], 'invalid exact methods')
            keys(d['limits'], {'small_exact_seconds', 'large_exact_seconds'})
            require(d['limits']['small_exact_seconds'] == 600 and d['limits']['large_exact_seconds'] == 10800, 'fixed exact limits required')
            for v in d['limits'].values():
                finite(v, 'limit', 1)
        else:
            require(type(d['bank']) is list and bool(d['bank']), 'empty bank')
            case_ids = set()
            for entry in d['bank']:
                keys(entry, {'path', 'case_id'})
                validate_hash(entry['case_id'])
                require(entry['case_id'] not in case_ids, 'duplicate case')
                case_ids.add(entry['case_id'])
                entry['path'] = path(entry['path'])
            s = d['submission']
            keys(s, {'method_id', 'file', 'uses_randomness', 'algorithm_seeds', 'owner', 'strategy_name', 'strategy_version'}, {'class_name'})
            for k in ('method_id', 'owner', 'strategy_name', 'strategy_version'):
                require(type(s[k]) is str and bool(s[k].strip()), f'invalid {k}')
            require(s['method_id'] in ('member_1', 'member_2', 'member_3'), 'unknown member method')
            if 'class_name' in s:
                require(type(s['class_name']) is str and s['class_name'].isidentifier(), 'invalid legacy class name')
            require(type(s['uses_randomness']) is bool, 'randomness must be bool')
            seeds(s['algorithm_seeds'], 5 if s['uses_randomness'] else 0)
            s['file'] = path(s['file'])
            keys(d['limits'], {'algorithm_seconds', 'algorithm_memory_bytes'})
            finite(d['limits']['algorithm_seconds'], 'algorithm seconds', 1)
            integer(d['limits']['algorithm_memory_bytes'], 'memory bytes', 1)
            expected_memory = 4_000_000_000 if 'class_name' in s else 6_000_000_000
            require(d['limits']['algorithm_seconds'] == 300 and d['limits']['algorithm_memory_bytes'] == expected_memory,
                    'fixed member limits required')
            keys(d['resource_policy'], {'sample_interval_ms'})
            integer(d['resource_policy']['sample_interval_ms'], 'sample interval', 10, 10)
        from protection.operations import validate_operational_data
        validate_operational_data(d)
        return cls(json.dumps(d, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False), str(Path(source_path).resolve()))


def validate_hash(value):
    import re
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, 'invalid SHA-256 id')


def canonical_json(value):
    import json
    return json.dumps(to_data(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def hash_data(value):
    import hashlib
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def scenario_hash(scenario):
    # 실행 장비 정보보다 재생성 가능한 입력을 식별자로 사용한다.
    return hash_data({name: getattr(scenario, name) for name in
                      ('schema_version', 'generation', 'seed', 'nodes', 'edges', 'demands')})


def case_hash(bundle):
    # 동일 지도라도 예산이나 평가 정책이 다르면 다른 채점 사례다.
    return hash_data({'schema_version': bundle.schema_version, 'scenario_id': bundle.scenario.scenario_id,
                      'attack_settings': bundle.scenario.attack_settings,
                      'evaluation_policy': bundle.scenario.evaluation_policy,
                      'budget_percent': bundle.budget_percent, 'budget': bundle.budget})


def strict_json_loads(text):
    import json
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, 'duplicate JSON key: ' + k)
            result[k] = v
        return result
    def bad_constant(value):
        raise InvalidScenarioError('nonfinite JSON constant: ' + value)
    def finite_float(value):
        result = float(value)
        require(math.isfinite(result), 'nonfinite JSON number: ' + value)
        return result
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant, parse_float=finite_float)
    except (ValueError, TypeError) as exc:
        raise InvalidScenarioError(str(exc)) from exc


def atomic_json(path, value, *, overwrite=False):
    import os
    import tempfile
    from pathlib import Path
    path = Path(path)
    text = canonical_json(value) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, path)
            temporary = None
        else:
            # Publish the complete inode atomically; existing destinations fail.
            os.link(temporary, path)
            temporary.unlink()
            temporary = None
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_scenario(scenario, path, *, overwrite=False):
    atomic_json(path, {'artifact_kind': 'scenario_input', 'schema_version': 1,
                      'scenario': scenario}, overwrite=overwrite)


def load_scenario(path):
    from pathlib import Path
    d = strict_json_loads(Path(path).read_text(encoding='utf-8'))
    keys(d, {'artifact_kind', 'schema_version', 'scenario'})
    integer(d['schema_version'], 'schema', 1, 1)
    require(d['artifact_kind'] == 'scenario_input', 'not an intermediate scenario input')
    validate_hash(d['scenario'].get('scenario_id') if type(d['scenario']) is dict else None)
    return from_data(Scenario, d['scenario'])


def save_bundle(bundle, path, *, overwrite=False):
    d = to_data(bundle)
    d['artifact_kind'] = 'scenario_bundle'
    if bundle.optimal_reference is None:
        del d['optimal_reference']
    atomic_json(path, d, overwrite=overwrite)


def load_bundle(path, *, require_reference=False):
    from pathlib import Path
    d = strict_json_loads(Path(path).read_text(encoding='utf-8'))
    keys(d, {'artifact_kind', 'schema_version', 'scenario', 'budget_percent', 'budget', 'case_id'}, {'optimal_reference'})
    require(d.pop('artifact_kind') == 'scenario_bundle', 'not a bundle')
    validate_hash(d['case_id'])
    validate_hash(d['scenario'].get('scenario_id') if type(d['scenario']) is dict else None)
    bundle = from_data(ScenarioBundle, d)
    if require_reference:
        require(bundle.optimal_reference is not None, 'distribution requires optimal reference')
    if bundle.optimal_reference is not None:
        validate_bundle_reference(bundle)
    return bundle


def validate_bundle_reference(bundle):
    """Validate stored proof metadata and independently re-score the reference.

    This does not cryptographically attest who performed the exhaustive run.
    The research's trusted local artifact assumption still applies.
    """
    from protection.evaluation import Evaluator
    reference = bundle.optimal_reference
    require(reference is not None, 'optimal reference required')
    require(bool(reference.environment), 'reference environment missing')
    require(reference.limit_seconds > 0 and reference.search_seconds < reference.limit_seconds,
            'reference did not complete before deadline')
    actual = Evaluator(bundle.scenario, require_certificate=True).evaluate(list(reference.protected_ids), bundle.budget)
    require(actual == reference.evaluation, 'reference re-scoring mismatch')
    return bundle


def feasible_protection_count(scenario, budget):
    """빈 집합을 포함해 예산 이내의 방호 집합 개수를 독립적으로 센다."""
    counts = [1] + [0] * budget
    for edge in scenario.edges:
        # 비용을 역순으로 순회해야 현재 간선을 같은 집합에 두 번 넣지 않는다.
        for cost in range(budget, edge.cost - 1, -1):
            counts[cost] += counts[cost - edge.cost]
    return sum(counts)


def bundle_from_record(scenario, record):
    """같은 사례에서 전 조합을 인증한 완료 기록만 배포용 참조로 변환한다."""
    require(type(record) is RunRecord, 'RunRecord required')
    condition = record.condition
    require(condition.method == 'exhaustive' and record.status == 'completed'
            and record.optimality_proven, 'completed exhaustive proof required')
    require(condition.scenario_id == scenario.scenario_id, 'scenario mismatch')
    require(record.policy_version == scenario.evaluation_policy.version, 'policy mismatch')
    require(record.best_evaluation is not None and record.search_seconds is not None,
            'missing exact evaluation/timing')
    reference_case = ScenarioBundle(scenario, condition.budget_percent, condition.budget)
    require(record.evaluated_combinations == feasible_protection_count(scenario, condition.budget),
            'exhaustive evaluation count does not match all feasible protection sets')
    require([event for event in record.events if event.startswith('highs_residual_fallback_solves=')]
            == ['highs_residual_fallback_solves=0'], 'reference requires all delivery scores to be certified')
    reference = OptimalReference(record.best_protected_ids, record.best_evaluation.cost,
        record.best_evaluation, record.run_id, record.environment,
        condition.limit_seconds, record.search_seconds)
    bundle = ScenarioBundle(scenario, condition.budget_percent, condition.budget,
                            optimal_reference=reference)
    require(record.case_id == reference_case.case_id, 'case_id mismatch')
    return validate_bundle_reference(bundle)

