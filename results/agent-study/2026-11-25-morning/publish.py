"""Publish a graph only after both separate single-run references validate."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PREVIOUS = ROOT / 'results/agent-study/2026-11-24-final/staging-bank'
sys.path.insert(0, str(ROOT))
from protection.runner import initialize_single_thread


def write_atomic(path, data):
    text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                         suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    initialize_single_thread()
    from datetime import datetime
    from hashlib import sha256
    from protection.models import RunRecord, bundle_from_record, from_data, load_bundle, load_scenario
    import importlib.util
    spec = importlib.util.spec_from_file_location('morning_run', HERE / 'run.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    if len(sys.argv) != 2 or sys.argv[1] not in ('1284121877', '583423369'):
        raise ValueError('usage: publish.py registered_seed')
    seed = int(sys.argv[1])
    graph = f'n14-seed{seed}'
    mode = 'first' if seed == 1284121877 else 'second'
    protocol = json.loads((HERE / 'protocol.json').read_text())
    deadline = datetime.fromisoformat(protocol['delivery_deadline_kst'])
    env = json.loads((HERE / f'environment-{mode}.json').read_text())
    assert runner.source_hashes() == env['source_sha256'], 'exact sources changed; certification rejected'
    scenario = load_scenario(PREVIOUS / 'inputs' / f'{graph}.json')
    checked = []
    with runner.grading_lock_until(deadline):
        for percent in (20, 40):
            name = f'{graph}-p{percent}'
            if seed == 1284121877 and percent == 20:
                record_path = ROOT / protocol['first_graph']['previous_record']
                bundle_path = ROOT / protocol['first_graph']['previous_bundle']
                reused = json.loads((HERE / 'reused-20-percent.json').read_text())
                assert sha256(record_path.read_bytes()).hexdigest() == reused['record_sha256']
                assert sha256(bundle_path.read_bytes()).hexdigest() == reused['bundle_sha256']
            else:
                record_path = HERE / 'staging-bank/records' / f'{name}.json'
                bundle_path = HERE / 'staging-bank/bundles' / f'{name}.json'
            record = from_data(RunRecord, json.loads(record_path.read_text()))
            elapsed = sum(x or 0 for x in (record.preparation_seconds, record.search_seconds,
                                           record.shutdown_seconds))
            assert record.run_kind == 'scale_probe' and record.condition.limit_seconds == 10800
            assert record.status == 'completed' and record.optimality_proven and elapsed < 10800
            bundle = bundle_from_record(scenario, record)
            assert load_bundle(bundle_path, require_reference=True) == bundle
            checked.append((name, record, bundle, elapsed, record_path, bundle_path))
        assert runner.source_hashes() == env['source_sha256'], 'exact sources changed during verification'
    public = ROOT / 'scenarios/problem-bank'
    metadata = {}
    for filename in ('manifest.json', 'progress.json', 'bank.json'):
        path = public / filename
        tracked = json.loads(subprocess.check_output(['git', 'show', f'HEAD:scenarios/problem-bank/{filename}'],
                                                      cwd=ROOT, text=True))
        working = json.loads(path.read_text())
        if working != tracked:
            raise RuntimeError(f'{filename} has other semantic edits; refusing to overwrite')
        metadata[filename] = working
    bank, manifest, progress = (metadata[x] for x in ('bank.json', 'manifest.json', 'progress.json'))
    if graph in bank['accepted_graphs']:
        raise RuntimeError('graph already accepted')
    manifest['sizes'] = sorted(set(manifest['sizes']) | {14})
    manifest['size_groups']['14'] = 'probe'
    manifest['seeds_by_size'].setdefault('14', []).append(seed)
    progress['target_graphs'] += 1
    bank['accepted_graphs'].append(graph)
    bank['accepted_sizes'] = sorted(set(bank['accepted_sizes']) | {14})
    for name, record, bundle, elapsed, record_path, bundle_path in checked:
        bank['bank'].append({'path': f'bundles/{name}.json', 'case_id': bundle.case_id})
        progress['cases'].append({'case': name, 'status': record.status, 'elapsed_seconds': elapsed,
                                  'eligible': True, 'error': record.error_message,
                                  'evaluated_combinations': record.evaluated_combinations})
        for folder, source in (('records', record_path), ('bundles', bundle_path)):
            destination = public / folder / f'{name}.json'
            if destination.exists():
                raise RuntimeError(f'destination exists: {destination}')
            shutil.copyfile(source, destination)
    input_destination = public / 'inputs' / f'{graph}.json'
    if input_destination.exists():
        raise RuntimeError('input destination exists')
    write_atomic(input_destination, json.loads((PREVIOUS / 'inputs' / f'{graph}.json').read_text()))
    for filename in ('manifest.json', 'progress.json', 'bank.json'):
        write_atomic(public / filename, metadata[filename])
    tempdir = Path('/tmp') / f'os26-publish-morning-{graph}'
    tempdir.mkdir(exist_ok=False)
    for filename, value in metadata.items():
        (tempdir / filename).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                                    separators=(',', ':'), allow_nan=False) + '\n')
    print('PUBLISHED', graph, 'cases', ', '.join(name for name, *_ in checked),
          'canonical_index_files', tempdir, flush=True)


if __name__ == '__main__':
    main()
