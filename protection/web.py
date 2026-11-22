"""팀원별 로그인, 시나리오 제공, 제출 큐와 비교 결과를 제공하는 웹 서비스다."""
import argparse
from contextlib import contextmanager
import csv
from functools import cache
import hmac
import io
import json
import logging
import os
from pathlib import Path
import random
import secrets
import shutil
import socket
import sqlite3
import time

from flask import (Flask, Response, abort, g, redirect, render_template,
                   request, send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from protection.runner import initialize_single_thread
from protection.program import (MAX_MEMORY_BYTES, MAX_SECONDS, MAX_SOURCE_BYTES, MIN_MEMORY_MB,
                                grade_program, grading_lock, scenario_input, scope_root, state_directory)
from protection.models import load_bundle
from protection.reporting import _row

BANK = Path(__file__).resolve().parent.parent / 'scenarios/problem-bank'
EXAMPLE_CASE = 'n6-seed0-p20'
ACCOUNTS = ('member1', 'member2', 'member3')
PRACTICE_SEEDS = (0, 1, 2, 3, 4)
LABELS = {'queued': '대기', 'running': '채점 중', 'finished': '채점 종료',
          'cancelled': '취소', 'failed': '중단'}
RESULT_LABELS = {'completed': '채점 완료', 'timeout': '시간 초과',
                 'memory_limit': '메모리 초과', 'not_implemented': '미구현', 'failed': '채점 실패'}
FIELDS = ('scenario', 'case_id', 'status', 'termination_reason', 'seconds_limit',
          'memory_limit_mb', 'vcpu_limit', 'algorithm_seed', 'search_seconds', 'worker_peak_mb',
          'connected_ratio', 'delivery_ratio', 'gap_connected_pairs', 'gap_delivery_units',
          'chosen_edges', 'error_message')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS accounts (name TEXT PRIMARY KEY, password TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts (account TEXT PRIMARY KEY, count INTEGER NOT NULL, since REAL NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, source BLOB NOT NULL,
    cases TEXT NOT NULL, seconds INTEGER NOT NULL, memory_mb INTEGER NOT NULL,
    random_strategy INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
    cancel INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    job INTEGER NOT NULL, position INTEGER NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (job, position)
);
'''


@contextmanager
def database():
    """요청 또는 워커 동작마다 별도 연결을 열어 트랜잭션 경계를 분리한다."""
    state = state_directory()
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    conn = sqlite3.connect(state / 'judge.sqlite3', timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def setup():
    with database() as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.executescript(SCHEMA)
        conn.execute('INSERT OR IGNORE INTO settings VALUES (?, ?)', ('session_key', secrets.token_hex(32)))
        return conn.execute('SELECT value FROM settings WHERE name=?', ('session_key',)).fetchone()[0]


def bank_files():
    """공개 인덱스에 있는 사례를 기존 사례 이름으로 제공한다."""
    index = json.loads((BANK / 'bank.json').read_text(encoding='utf-8'))
    files = {}
    for entry in index['bank']:
        path = Path(entry['path'])
        if path.parent != Path('bundles') or path.suffix != '.json' or path.stem in files:
            raise ValueError(f'invalid problem bank path: {path}')
        files[path.stem] = BANK / path
    return dict(sorted(files.items()))


@cache
def bank_case(path):
    return load_bundle(path, require_reference=True) if path else None


def get_owned(conn, job_id, owner):
    """페이지, CSV, 취소 요청에서 로그인한 팀원의 제출만 조회할 수 있다."""
    job = conn.execute('SELECT * FROM jobs WHERE id=? AND owner=?', (job_id, owner)).fetchone()
    if job is None:
        abort(404)
    rows = conn.execute('SELECT payload FROM results WHERE job=? ORDER BY position', (job_id,)).fetchall()
    return job, [json.loads(row['payload']) for row in rows]


def comparison_row(row, bundle):
    """저장된 행에 동일 케이스의 최적 점수를 붙이고 화면용 격차를 계산한다."""
    result = dict(row, status_label=RESULT_LABELS.get(row['status'], '채점 실패'))
    if row['termination_reason'] == 'cancelled':
        result['status_label'] = '취소'
    if bundle is None or row['case_id'] != bundle.case_id:
        return result

    scenario = bundle.scenario
    nodes = len(scenario.nodes)
    total_pairs = nodes * (nodes - 1) // 2
    reference = bundle.optimal_reference.evaluation
    result.update(nodes=nodes, budget_percent=bundle.budget_percent, scenario_seed=scenario.seed,
                  total_pairs=total_pairs, budget=bundle.budget, reference_pairs=reference.connected_pairs,
                  reference_delivery=reference.delivery_ratio)
    if row['status'] == 'completed':
        # 이전 레코드에도 연결률이 있으므로 전체 쌍 수에서 제출안의 정수 쌍 수를 복원한다.
        connected_pairs = round(row['connected_ratio'] * total_pairs)
        ids = [int(edge_id) for edge_id in row['chosen_edges'].split()]
        result.update(submitted_pairs=connected_pairs, used_cost=sum(scenario.edges[edge_id].cost for edge_id in ids),
                      delta_pairs=reference.connected_pairs - connected_pairs,
                      delta_delivery_pp=(reference.delivery_ratio - row['delivery_ratio']) * 100)
    return result


def create_app():
    initialize_single_thread()
    app = Flask(__name__)
    app.config.update(SECRET_KEY=setup(), SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax', MAX_CONTENT_LENGTH=512 * 1024)
    files = bank_files()

    example = None
    if EXAMPLE_CASE in files:
        bundle = bank_case(files[EXAMPLE_CASE])
        selected = bundle.optimal_reference.protected_ids
        stdin = scenario_input(bundle).decode('ascii')
        header = stdin.split('\n', 1)[0]
        example = dict(name=EXAMPLE_CASE, stdin=stdin, header=header, counts=header.split(),
                       stdout=' '.join(map(str, (len(selected), *selected))), budget=bundle.budget,
                       costs=[bundle.scenario.edges[edge_id].cost for edge_id in selected])

    @app.before_request
    def authenticate():
        g.owner = session.get('owner')
        if request.method == 'POST':
            # 사용자 브라우저의 세션에서 발급한 토큰이 있어야 상태 변경을 수락한다.
            token = session.get('csrf', '')
            if not token or not hmac.compare_digest(token, request.form.get('csrf', '')):
                abort(403)
        if request.endpoint != 'login' and g.owner not in ACCOUNTS:
            return redirect(url_for('login'))

    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                                 'Referrer-Policy': 'no-referrer',
                                 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    def page(**context):
        csrf = session.setdefault('csrf', secrets.token_urlsafe(32))
        return render_template('judge.html', csrf=csrf, labels=LABELS, **context)

    @app.route('/login', methods=('GET', 'POST'))
    def login():
        error = None
        if request.method == 'POST':
            account = request.form.get('account', '')
            password = request.form.get('password', '')
            now = time.time()
            if account in ACCOUNTS and len(password) <= 256:
                with database() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    failures = conn.execute('SELECT count, since FROM login_attempts WHERE account=?', (account,)).fetchone()
                    if failures and failures['since'] + 300 < now:
                        conn.execute('DELETE FROM login_attempts WHERE account=?', (account,))
                        failures = None
                    if failures and failures['count'] >= 10:
                        return page(view='login', error='잠시 후 다시 시도해 주세요.'), 429
                    row = conn.execute('SELECT password FROM accounts WHERE name=?', (account,)).fetchone()
                    if row and check_password_hash(row['password'], password):
                        conn.execute('DELETE FROM login_attempts WHERE account=?', (account,))
                        session.clear()
                        session['owner'] = account
                        return redirect(url_for('index'))
                    conn.execute('INSERT INTO login_attempts VALUES (?, 1, ?) ON CONFLICT(account) DO UPDATE SET count=count+1', (account, now))
            error = '계정 또는 비밀번호를 확인해 주세요.'
        return page(view='login', error=error)

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.get('/')
    def index():
        with database() as conn:
            jobs = conn.execute('SELECT id, state, seconds, memory_mb FROM jobs WHERE owner=? ORDER BY id DESC LIMIT 30', (g.owner,)).fetchall()
        return page(view='index', files=bank_files(), jobs=jobs, example=example, max_seconds=MAX_SECONDS,
                    max_memory=MAX_MEMORY_BYTES // 1_000_000, min_memory=MIN_MEMORY_MB)

    @app.get('/bank/<name>/<kind>')
    def download_case(name, kind):
        files = bank_files()
        if name not in files or kind not in ('reference', 'input'):
            abort(404)
        path = files[name]
        if kind == 'reference':
            return send_file(path, as_attachment=True)
        return Response(scenario_input(bank_case(path)), mimetype='text/plain',
                        headers={'Content-Disposition': f'attachment; filename="{name}.txt"'})

    @app.post('/submit')
    def submit():
        files = bank_files()
        form = request.form
        upload = request.files.get('file')
        source = form.get('source', '').encode('utf-8')
        if upload and upload.filename:
            if source.strip():
                abort(400, '파일 또는 소스 입력 중 하나만 사용하세요.')
            source = upload.stream.read(MAX_SOURCE_BYTES + 1)
        if not source.strip() or len(source) > MAX_SOURCE_BYTES:
            abort(400, '128KiB 이하의 Python 소스를 입력하세요.')
        try:
            compile(source, 'submission.py', 'exec', dont_inherit=True)
            seconds = int(form.get('seconds', ''))
            memory = int(form.get('memory', ''))
            if not 1 <= seconds <= MAX_SECONDS or not MIN_MEMORY_MB <= memory <= MAX_MEMORY_BYTES // 1_000_000:
                raise ValueError('제한 범위를 확인해 주세요.')
            if form.get('selection') == 'random':
                count = int(form.get('count', ''))
                if not 1 <= count <= len(files):
                    raise ValueError('무작위 시나리오 개수를 확인해 주세요.')
                cases = random.SystemRandom().sample(sorted(files), count)
            else:
                cases = list(dict.fromkeys(form.getlist('case')))
                if not cases or any(name not in files for name in cases):
                    raise ValueError('한 개 이상의 시나리오를 선택하세요.')
        except (ValueError, SyntaxError) as error:
            abort(400, str(error))
        with database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            # 동일 계정의 동시 요청도 활성 제출 한 건 제한을 우회할 수 없다.
            if conn.execute("SELECT 1 FROM jobs WHERE owner=? AND state IN ('queued','running')", (g.owner,)).fetchone():
                abort(409, '대기 또는 실행 중인 제출을 완료하거나 취소한 뒤 제출하세요.')
            job = conn.execute('INSERT INTO jobs (owner, source, cases, seconds, memory_mb, random_strategy, created) VALUES (?, ?, ?, ?, ?, ?, ?)',
                               (g.owner, source, json.dumps(cases), seconds, memory,
                                form.get('random_strategy') == 'yes', time.time()))
            job_id = job.lastrowid
        return redirect(url_for('job_detail', job_id=job_id))

    @app.get('/jobs/<int:job_id>')
    def job_detail(job_id):
        with database() as conn:
            job, rows = get_owned(conn, job_id, g.owner)
        files = bank_files()
        rows = [comparison_row(row, bank_case(files.get(row['scenario']))) for row in rows]
        return page(view='job', job=job, rows=rows, selected_cases=json.loads(job['cases']))

    @app.post('/jobs/<int:job_id>/cancel')
    def cancel(job_id):
        with database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            get_owned(conn, job_id, g.owner)
            conn.execute("UPDATE jobs SET cancel=1, state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END "
                         "WHERE id=? AND state IN ('queued','running')", (job_id,))
        return redirect(url_for('job_detail', job_id=job_id))

    @app.get('/jobs/<int:job_id>/csv')
    def download_csv(job_id):
        with database() as conn:
            _, rows = get_owned(conn, job_id, g.owner)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            message = row.get('error_message')
            # 제출 프로그램의 오류 문구가 스프레드시트 수식으로 실행되지 않도록 한다.
            if message and message.lstrip().startswith(('=', '+', '-', '@')):
                row['error_message'] = "'" + message
            writer.writerow(row)
        return Response('\ufeff' + output.getvalue(), mimetype='text/csv',
                        headers={'Content-Disposition': f'attachment; filename="submission-{job_id}.csv"'})

    return app


def result_row(name, job, record, bundle):
    row = _row(record, {bundle.case_id: bundle})
    result = {key: row[key] for key in FIELDS if key in row}
    result.update(scenario=name, seconds_limit=job['seconds'], memory_limit_mb=job['memory_mb'],
                  vcpu_limit=record.algorithm_vcpu_limit,
                  worker_peak_mb=None if record.algorithm_peak_memory_bytes is None
                  else round(record.algorithm_peak_memory_bytes / 1_000_000, 2),
                  chosen_edges=None if record.submitted_protected_ids is None
                  else ' '.join(map(str, record.submitted_protected_ids)))
    return result


def is_cancelled(job_id):
    with database() as conn:
        return bool(conn.execute('SELECT cancel FROM jobs WHERE id=?', (job_id,)).fetchone()[0])


def grade_job(job, bank):
    """제출 시 확정된 시나리오와 반복 시드를 사용하고, 실행별 결과를 즉시 저장한다."""
    def cancelled():
        return is_cancelled(job['id'])

    seeds = PRACTICE_SEEDS if job['random_strategy'] else (None,)
    position = 0
    for name in json.loads(job['cases']):
        bundle = bank[name]
        for index, seed in enumerate(seeds):
            record = grade_program(bundle, job['source'], seconds=job['seconds'],
                                   memory_bytes=job['memory_mb'] * 1_000_000,
                                   seed=seed, repeat_index=index, repeat_count=len(seeds),
                                   method='member_' + job['owner'][-1],
                                   cancelled=cancelled)
            row = result_row(name, job, record, bundle)
            with database() as conn:
                conn.execute('INSERT INTO results VALUES (?, ?, ?)', (job['id'], position, json.dumps(row)))
            position += 1


def run_worker():
    """격리 도구를 확인한 뒤 준비를 알리고, 대기 중인 제출을 차례로 처리한다."""
    initialize_single_thread()
    setup()
    scope_root()
    if not bank_files():
        raise RuntimeError('validated problem bank is empty')
    if shutil.which('bwrap') is None:
        raise RuntimeError('bubblewrap is required')
    if address := os.environ.get('NOTIFY_SOCKET'):
        if address.startswith('@'):
            address = '\0' + address[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notifier:
            notifier.sendto(b'READY=1', address)
    while True:
        with grading_lock():
            with database() as conn:
                conn.execute('BEGIN IMMEDIATE')
                # 이전 워커 중단으로 남은 실행은 실패로 마감한다. 이미 기록된 행은 보존된다.
                conn.execute("UPDATE jobs SET state=CASE WHEN cancel=1 THEN 'cancelled' ELSE 'failed' END WHERE state='running'")
                job = conn.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY id LIMIT 1").fetchone()
                if job:
                    conn.execute("UPDATE jobs SET state='running' WHERE id=?", (job['id'],))
            if job:
                state = 'finished'
                try:
                    files = bank_files()
                    bank = {name: bank_case(files[name]) for name in json.loads(job['cases'])}
                    grade_job(job, bank)
                except Exception:
                    state = 'failed'
                    logging.exception('grading job %s', job['id'])
                with database() as conn:
                    conn.execute("UPDATE jobs SET state=CASE WHEN cancel=1 THEN 'cancelled' ELSE ? END WHERE id=?",
                                 (state, job['id']))
        if not job:
            time.sleep(.5)


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('action', choices=('worker', 'accounts'))
    args.add_argument('--reset', choices=ACCOUNTS)
    parsed = args.parse_args()
    if parsed.action == 'worker':
        run_worker()
        return
    setup()
    with database() as conn:
        for account in ((parsed.reset,) if parsed.reset else ACCOUNTS):
            if parsed.reset or not conn.execute('SELECT 1 FROM accounts WHERE name=?', (account,)).fetchone():
                password = secrets.token_urlsafe(20)
                conn.execute('INSERT OR REPLACE INTO accounts VALUES (?, ?)', (account, generate_password_hash(password)))
                print(f'{account}: {password}')


if __name__ == '__main__':
    main()
