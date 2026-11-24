"""Freeze the documented 20 certified cases and six original method hashes."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from protection.runner import initialize_single_thread


def main():
    initialize_single_thread()
    from protection.models import load_bundle
    from protection.program import scenario_input
    old = json.loads((ROOT / 'results/agent-study/2026-11-24/protocol.json').read_text())
    sizes = {'6': [27, 1], '8': [9, 0], '10': [10, 4], '12': [3, 4], '14': [0, 1]}
    cases = []
    for size, seeds in sizes.items():
        for seed in seeds:
            for percent in (20, 40):
                name = f'n{size}-seed{seed}-p{percent}'
                path = f'scenarios/problem-bank/bundles/{name}.json'
                bundle = load_bundle(ROOT / path, require_reference=True)
                cases.append({'name': name, 'n': int(size), 'seed': seed,
                              'budget_percent': percent, 'path': path, 'case_id': bundle.case_id,
                              'stdin_sha256': sha256(scenario_input(bundle)).hexdigest()})
    methods = old['methods']
    for method in methods:
        assert sha256((ROOT / method['path']).read_bytes()).hexdigest() == method['sha256']
    protocol = {'registered_at_utc': datetime.now(timezone.utc).isoformat(),
                'purpose': '오늘 안에 1~3번의 여섯 전략을 동일 인증 20사례에 비교',
                'selection': {'generator': 'numpy.default_rng(202611242028)',
                              'seed_ranges': {'6': 31, '8': 21, '10': 11, '12': 7},
                              'seeds_by_size': sizes,
                              'n14': '기존 인증 시드 0·1 전부',
                              'note': '공개·이전 사용 가능 사례이므로 블라인드 확인 표본 아님'},
                'cases': cases, 'methods': methods,
                'execution': {'wall_seconds_per_run': 300,
                              'memory_bytes_per_process': 6000000000, 'cpu_cores': 1,
                              'randomness': '결정적 방법 각 1회',
                              'implementation': 'local subprocess and RLIMIT_AS, not web cgroup',
                              'score_after_submission': True,
                              'hard_stop_kst': '2026-11-24T23:35:00+09:00'},
                'predefined_contrasts': [['betweenness', 'degree'],
                                         ['demand_bundle', 'demand_single'],
                                         ['local_search', 'connectivity_greedy'],
                                         ['demand_bundle', 'degree']],
                'graph_cluster': '동일 그래프의 두 예산을 묶어 해석',
                'candidate_graphs': {'14': [1284121877, 583423369],
                                     '15': [1227514652, 1851654530]},
                'candidate_generator': 'numpy.default_rng(202611241927)',
                'candidate_budget_percents': [20, 40],
                'candidate_pilot_limit_seconds': 5,
                'candidate_operational_caps_seconds': {'14': {'20': 180, '40': 1800},
                                                       '15': {'20': 300, '40': 2400}}}
    assert len(cases) == 20 and len(methods) == 6
    path = HERE / 'protocol.json'
    if path.exists():
        raise RuntimeError('protocol exists')
    path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + '\n')
    manifest = {'schema_version': 1, 'kind': 'preparation', 'run_kind': 'scale_probe',
                'ready': True, 'owners': {'common': '김대건'}, 'output_dir': 'staging-bank',
                'sizes': [14, 15], 'size_groups': {'14': 'probe', '15': 'probe'},
                'seeds_by_size': protocol['candidate_graphs'], 'budget_percents': [20, 40],
                'exact_methods': ['exhaustive', 'branch_bound'],
                'limits': {'small_exact_seconds': 600, 'large_exact_seconds': 10800}}
    (HERE / 'exact-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('Registered', len(cases), 'cases and', len(methods), 'fixed methods')


if __name__ == '__main__':
    main()
