"""Prepare the registered size probes without touching the public problem bank."""
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def build_one(n, seed):
    from protection.generation import generate_scenario
    from protection.evaluation import budget_for
    from protection.models import ScenarioBundle, feasible_protection_count, to_data
    from protection.program import scenario_input

    start = time.monotonic()
    scenario = generate_scenario(n, seed)
    generation_seconds = time.monotonic() - start
    inputs = []
    started = time.monotonic()
    first = ScenarioBundle(scenario, 20, budget_for(scenario, 20))
    first_bytes = scenario_input(first)
    input_seconds = time.monotonic() - started
    first_lines = first_bytes.splitlines(keepends=True)
    for percent in (20, 40):
        bundle = ScenarioBundle(scenario, percent, budget_for(scenario, percent))
        name = f'n{n}-seed{seed}-p{percent}'
        bundle_path = HERE / 'bundles' / (name + '.json')
        input_path = HERE / 'inputs' / (name + '.txt')
        if bundle_path.exists() or input_path.exists():
            raise RuntimeError('refusing to overwrite existing input')
        data = to_data(bundle)
        data.pop('optimal_reference', None)
        data['artifact_kind'] = 'scenario_bundle'
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        if percent == 20:
            stdin = first_bytes
        else:
            lines = list(first_lines)
            lines[1] = f'{bundle.budget} {percent} {seed} -1\n'.encode('ascii')
            stdin = b''.join(lines)
            if n == 64:
                assert stdin == scenario_input(bundle), 'derived input differs from common input'
        input_path.write_bytes(stdin)
        started = time.monotonic()
        feasible = feasible_protection_count(scenario, bundle.budget)
        inputs.append({
            'name': name, 'n': n, 'seed': seed, 'budget_percent': percent,
            'budget': bundle.budget, 'edge_count': len(scenario.edges),
            'demand_count': len(scenario.demands), 'case_id': bundle.case_id,
            'bundle_path': str(bundle_path.relative_to(ROOT)),
            'input_path': str(input_path.relative_to(ROOT)),
            'stdin_sha256': sha256(stdin).hexdigest(), 'stdin_bytes': len(stdin),
            'feasible_sets': str(feasible), 'feasible_count_seconds': time.monotonic() - started,
            'reference_available': False,
        })
    return {'n': n, 'seed': seed, 'generation_seconds': generation_seconds,
            'first_input_preparation_seconds': input_seconds, 'cases': inputs}


def set_limits():
    resource.setrlimit(resource.RLIMIT_AS, (6_000_000_000, 6_000_000_000))


def main():
    protocol = json.loads((HERE / 'protocol.json').read_text())
    if len(sys.argv) == 4 and sys.argv[1] == '--one':
        print(json.dumps(build_one(int(sys.argv[2]), int(sys.argv[3])), ensure_ascii=False))
        return
    if (HERE / 'preparation.jsonl').exists():
        raise RuntimeError('results exist; preserve the original run')
    from protection.runner import collect_environment, initialize_single_thread
    initialize_single_thread()
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    env = collect_environment()
    env.update(affinity=sorted(os.sched_getaffinity(0)),
               source='local; no web cgroup or bubblewrap',
               per_process_address_space_limit_bytes=6_000_000_000,
               protocol_sha256=sha256((HERE / 'protocol.json').read_bytes()).hexdigest(),
               prepare_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    (HERE / 'environment.json').write_text(json.dumps(env, ensure_ascii=False, indent=2) + '\n')
    child_env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                     MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1', BLIS_NUM_THREADS='1')
    with (HERE / 'preparation.jsonl').open('x', encoding='utf-8') as out:
        for n in protocol['runtime_probe_sizes']:
            for seed in protocol['seeds_by_size'][str(n)]:
                start = time.monotonic()
                try:
                    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--one',
                                           str(n), str(seed)], text=True, capture_output=True,
                                          env=child_env, timeout=180, preexec_fn=set_limits)
                    if proc.returncode:
                        result = {'n': n, 'seed': seed, 'status': 'failed',
                                  'error': proc.stderr[-4096:], 'cases': []}
                    else:
                        result = json.loads(proc.stdout)
                        result['status'] = 'completed'
                except subprocess.TimeoutExpired:
                    result = {'n': n, 'seed': seed, 'status': 'timeout', 'cases': []}
                result['total_wall_seconds'] = time.monotonic() - start
                out.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + '\n')
                out.flush()
                print(f"n={n} seed={seed} {result['status']} {result['total_wall_seconds']:.3f}s", flush=True)


if __name__ == '__main__':
    main()
