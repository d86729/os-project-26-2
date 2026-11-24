"""Give a queued web submission priority over the exact retry's shared lock."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import sqlite3
import sys
import time

HERE = Path(__file__).resolve().parent
STATE = Path.home() / '.local/state/protection-judge'


def alive_and_expected(pid):
    try:
        command = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    except FileNotFoundError:
        return False
    return any(x.endswith((b'results/agent-study/2026-11-24-final/retry.py',
                           b'results/agent-study/2026-11-24-final/certify.py')) for x in command)


def holds_lock(pid):
    inode = str((STATE / 'grading.lock').stat().st_ino)
    for row in Path('/proc/locks').read_text().splitlines():
        fields = row.split()
        if '->' not in fields and len(fields) >= 6 and fields[1] == 'FLOCK':
            if fields[4] == str(pid) and fields[5].split(':')[-1] == inode:
                return True
    return False


def main():
    if len(sys.argv) not in (2, 3):
        raise ValueError('usage: watch_queue.py EXACT_PID [SUFFIX]')
    pid = int(sys.argv[1])
    plan = json.loads((HERE / 'retry-plan.json').read_text())
    deadline = datetime.fromisoformat(plan['hard_stop_kst'])
    suffix = sys.argv[2] if len(sys.argv) == 3 else ''
    if suffix and not suffix.isdigit():
        raise ValueError('suffix must be digits')
    log = HERE / f'queue-monitor{suffix}.jsonl'
    if log.exists():
        raise RuntimeError('monitor record exists')
    with log.open('x', encoding='utf-8') as out:
        def emit(event, **extra):
            out.write(json.dumps({'at_utc': datetime.now(timezone.utc).isoformat(),
                                  'event': event, **extra}) + '\n')
            out.flush()
        emit('started', retry_pid=pid)
        while datetime.now(timezone.utc) < deadline and alive_and_expected(pid):
            try:
                connection = sqlite3.connect(f'file:{STATE / "judge.sqlite3"}?mode=ro', uri=True, timeout=3)
                try:
                    count = connection.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]
                finally:
                    connection.close()
                if count and holds_lock(pid) and alive_and_expected(pid):
                    os.kill(pid, signal.SIGALRM)
                    emit('interrupted_for_web_queue', active_jobs=count)
                    print('exact search interrupted to prioritize queued web work', flush=True)
            except (OSError, sqlite3.Error) as error:
                emit('monitor_error', error_type=type(error).__name__)
            time.sleep(5)
        emit('finished')
        print('queue monitor finished', flush=True)


if __name__ == '__main__':
    main()
