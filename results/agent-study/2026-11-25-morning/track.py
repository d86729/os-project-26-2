"""Record distinct live progress snapshots without affecting the search."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('first', 'second'):
        raise ValueError('usage: track.py first|second')
    mode = sys.argv[1]
    plan = json.loads((HERE / 'protocol.json').read_text())
    deadline = datetime.fromisoformat(plan['hard_stop_kst'])
    expected = f'n14-seed{plan[mode + "_graph"]["seed"]}-'
    path = HERE / f'progress-{mode}.jsonl'
    if path.exists():
        raise RuntimeError('progress history already exists')
    last = None
    with path.open('x', encoding='utf-8') as out:
        while datetime.now(timezone.utc) < deadline:
            try:
                snapshot = json.loads((HERE / 'status.json').read_text())
                if not snapshot.get('case', '').startswith(expected):
                    time.sleep(1)
                    continue
                token = snapshot.get('updated_at_utc') or snapshot.get('actual_finished_at_utc')
                if token != last:
                    out.write(json.dumps(snapshot, ensure_ascii=False, allow_nan=False) + '\n')
                    out.flush()
                    last = token
                if snapshot.get('status') in ('completed', 'timeout', 'failed'):
                    break
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            time.sleep(30)


if __name__ == '__main__':
    main()
