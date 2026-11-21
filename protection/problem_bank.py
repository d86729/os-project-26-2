"""고정된 시드의 두 예산을 인증하고, 검증을 마친 쌍을 문제은행에 공개한다."""
import argparse
import fcntl
from pathlib import Path

from protection.models import (
    ExperimentManifest, RunRecord, atomic_json, bundle_from_record, from_data,
    load_bundle, load_scenario, save_bundle, save_scenario, strict_json_loads,
)


def read_json(path):
    return strict_json_loads(path.read_text(encoding='utf-8'))


def build_bank(manifest, *, resume=False):
    """한 번에 한 생성기만 기록을 쓰도록 하고, 동일한 manifest로 재개를 허용한다."""
    manifest = ExperimentManifest.parse(manifest.to_dict(), manifest.source_path)
    data = manifest.to_dict()
    if data['run_kind'] != 'scale_probe' or data['kind'] != 'preparation':
        raise ValueError('scale_probe preparation manifest required')
    if data['sizes'] != sorted(data['sizes']):
        raise ValueError('candidate sizes must be ascending')
    output = Path(data['output_dir'])
    output.mkdir(parents=True, exist_ok=resume)
    with (output / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _build_locked(manifest, data, output)


def _build_locked(manifest, data, output):
    from protection.exact import search
    from protection.generation import generate_scenario
    from protection.program import grading_lock
    from protection.runner import collect_environment

    frozen = output / 'manifest.json'
    if frozen.exists():
        if read_json(frozen) != data:
            raise ValueError('manifest differs from the frozen bank manifest')
    else:
        atomic_json(frozen, data)
    if not (output / 'environment.json').exists():
        atomic_json(output / 'environment.json', collect_environment())

    # 점수나 실행 시간을 보기 전에 모든 입력을 저장해 표본 선택 기준을 고정한다.
    scenarios = []
    for n in data['sizes']:
        for seed in data['seeds_by_size'][str(n)]:
            name = f'n{n}-seed{seed}'
            input_path = output / 'inputs' / f'{name}.json'
            if not input_path.exists():
                save_scenario(generate_scenario(n, seed), input_path)
            scenario = load_scenario(input_path)
            if len(scenario.nodes) != n or scenario.seed != seed:
                raise ValueError(f'{name}: stored scenario differs from manifest')
            scenarios.append((name, scenario))

    limit = data['limits']['large_exact_seconds']
    state = {'status': 'running', 'time_limit_per_budget_seconds': limit, 'active': None,
             'target_graphs': len(scenarios), 'cases': []}
    index = output / 'bank.json'
    bank = read_json(index) if index.exists() else {
        'schema_version': 1, 'status': 'building', 'bank': [], 'accepted_graphs': [],
        'excluded_graphs': [], 'accepted_sizes': [], 'excluded_sizes': [], 'not_started_sizes': [],
    }
    bank['status'] = 'building'

    def persist():
        # 웹은 공개 목록만 읽는다. 두 파일은 각각 임시 파일을 거쳐 원자적으로 교체한다.
        atomic_json(output / 'progress.json', state, overwrite=True)
        atomic_json(index, bank, overwrite=True)

    persist()
    try:
        for name, scenario in scenarios:
            references = []
            for percent in data['budget_percents']:
                case = f'{name}-p{percent}'
                path = output / 'records' / f'{case}.json'
                state['active'] = case
                persist()
                if path.exists():
                    # 재개 시 종료 기록이 있는 조건은 계산 없이 검증부터 다시 한다.
                    record = from_data(RunRecord, read_json(path))
                else:
                    print(f'START {case}', flush=True)
                    # 공개 채점과 완전탐색이 동시에 CPU를 쓰지 않도록 조건마다 잠금을 공유한다.
                    with grading_lock():
                        record = search(scenario, percent, method='exhaustive', run_kind='scale_probe',
                                        manifest=manifest)
                    atomic_json(path, record)
                if (record.condition.scenario_id != scenario.scenario_id
                        or record.condition.budget_percent != percent
                        or record.run_kind != 'scale_probe'
                        or record.condition.limit_seconds != limit):
                    raise ValueError(f'{case}: stored run does not match the manifest')

                elapsed = sum(value or 0 for value in (
                    record.search_seconds, record.preparation_seconds, record.shutdown_seconds))
                eligible = (record.status == 'completed' and record.optimality_proven
                            and elapsed < limit)
                if eligible:
                    references.append((case, bundle_from_record(scenario, record)))
                state['cases'].append(dict(case=case, status=record.status, elapsed_seconds=elapsed,
                                           eligible=eligible, error=record.error_message,
                                           evaluated_combinations=record.evaluated_combinations))
                print(f'END {case} status={record.status} seconds={elapsed:.3f} eligible={eligible}', flush=True)
                persist()

            n = len(scenario.nodes)
            if len(references) == len(data['budget_percents']):
                # 두 번의 재채점과 파일 읽기 검증이 끝난 후에만 두 항목을 인덱스에 함께 넣는다.
                entries = []
                for case, bundle in references:
                    relative = Path('bundles') / f'{case}.json'
                    path = output / relative
                    if not path.exists():
                        save_bundle(bundle, path)
                    if load_bundle(path, require_reference=True) != bundle:
                        raise ValueError(f'{case}: bundle readback mismatch')
                    entries.append({'path': str(path), 'case_id': bundle.case_id})
                if name not in bank['accepted_graphs']:
                    bank['bank'].extend(entries)
                    bank['accepted_graphs'].append(name)
                    bank['accepted_sizes'] = sorted(set(bank['accepted_sizes']) | {n})
            elif name not in bank['excluded_graphs']:
                bank['excluded_graphs'].append(name)
                bank['excluded_sizes'] = sorted(set(bank['excluded_sizes']) | {n})
            persist()
        bank['status'] = 'ready' if bank['bank'] else 'empty'
        state.update(status='finished', active=None)
        persist()
        print(f"FINISHED accepted graphs={len(bank['accepted_graphs'])}", flush=True)
        return bank
    except BaseException as error:
        state.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                     error=f'{type(error).__name__}: {error}')
        bank['status'] = 'partial'
        persist()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    from protection.runner import initialize_single_thread
    initialize_single_thread()
    path = Path(args.manifest)
    manifest = ExperimentManifest.parse(read_json(path), path)
    build_bank(manifest, resume=args.resume)


if __name__ == '__main__':
    main()
