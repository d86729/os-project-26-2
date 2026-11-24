"""Publish one fully certified graph, preserving existing local JSON formatting edits."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from protection.runner import initialize_single_thread


@contextmanager
def lock_until(deadline):
    path = Path.home() / '.local/state/protection-judge/grading.lock'
    with path.open('a') as handle:
        while True:
            if datetime.now(timezone.utc) >= deadline:
                raise RuntimeError('23:35 deadline while waiting for lock')
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(.2)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


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
    from protection.models import (RunRecord, bundle_from_record, from_data, load_bundle,
                                   load_scenario, to_data)
    if len(sys.argv) != 2:
        raise ValueError('usage: publish.py n14-seed123')
    graph = sys.argv[1]
    protocol = json.loads((HERE / 'protocol.json').read_text())
    allowed = {f'n{n}-seed{seed}' for n, seeds in protocol['candidate_graphs'].items() for seed in seeds}
    extra_protocol = json.loads((HERE / 'protocol12.json').read_text())
    allowed.update(f'n{n}-seed{seed}' for n, seeds in extra_protocol['candidate_graphs'].items() for seed in seeds)
    if graph not in allowed:
        raise ValueError('graph not registered')
    deadline = datetime.fromisoformat(protocol['execution']['hard_stop_kst'])
    stage = HERE / 'staging-bank'
    scenario = load_scenario(stage / 'inputs' / f'{graph}.json')
    n, seed = len(scenario.nodes), scenario.seed
    data = []
    with lock_until(deadline):
        for percent in (20, 40):
            name = f'{graph}-p{percent}'
            record = record_path = bundle_path = None
            for prefix in (stage / 'retry', stage):
                candidate = prefix / 'records' / f'{name}.json'
                if candidate.exists():
                    tested = from_data(RunRecord, json.loads(candidate.read_text()))
                    if tested.status == 'completed' and tested.optimality_proven:
                        record, record_path = tested, candidate
                        bundle_path = prefix / 'bundles' / f'{name}.json'
                        break
            if record is None:
                raise RuntimeError(f'{name} has no completed certification record')
            elapsed = sum(x or 0 for x in (record.preparation_seconds, record.search_seconds,
                                           record.shutdown_seconds))
            assert record.run_kind == 'scale_probe' and record.condition.limit_seconds == 10800
            assert record.status == 'completed' and record.optimality_proven and elapsed < 10800
            bundle = bundle_from_record(scenario, record)
            assert load_bundle(bundle_path, require_reference=True) == bundle
            data.append((name, record, bundle, elapsed, record_path, bundle_path))
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
    manifest['sizes'] = sorted(set(manifest['sizes']) | {n})
    manifest['size_groups'][str(n)] = 'probe'
    manifest['seeds_by_size'].setdefault(str(n), []).append(seed)
    progress['target_graphs'] += 1
    bank['accepted_graphs'].append(graph)
    bank['accepted_sizes'] = sorted(set(bank['accepted_sizes']) | {n})
    for name, record, bundle, elapsed, record_path, bundle_path in data:
        bank['bank'].append({'path': f'bundles/{name}.json', 'case_id': bundle.case_id})
        progress['cases'].append({'case': name, 'status': record.status,
                                  'elapsed_seconds': elapsed, 'eligible': True,
                                  'error': record.error_message,
                                  'evaluated_combinations': record.evaluated_combinations})
        for folder, source in (('records', record_path), ('bundles', bundle_path)):
            destination = public / folder / f'{name}.json'
            if destination.exists():
                raise RuntimeError(f'destination exists: {destination}')
            shutil.copyfile(source, destination)
    input_destination = public / 'inputs' / f'{graph}.json'
    if input_destination.exists():
        raise RuntimeError('input destination exists')
    write_atomic(input_destination, json.loads((stage / 'inputs' / f'{graph}.json').read_text()))
    # Existing local formatting changes are kept; only three semantic additions are made.
    for filename in ('manifest.json', 'progress.json', 'bank.json'):
        write_atomic(public / filename, metadata[filename])
    # Temporary canonical versions permit a content-only Git index update without
    # staging the user's unrelated JSON beautification changes.
    tempdir = Path('/tmp') / f'os26-publish-{graph}'
    tempdir.mkdir(exist_ok=False)
    for filename, value in metadata.items():
        (tempdir / filename).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                                    separators=(',', ':'), allow_nan=False) + '\n')
    print('PUBLISHED', graph, 'cases', ', '.join(name for name, *_ in data),
          'canonical_index_files', tempdir, flush=True)


if __name__ == '__main__':
    main()
