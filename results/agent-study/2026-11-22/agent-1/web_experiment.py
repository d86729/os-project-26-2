"""Explicitly run the two preregistered web jobs; credentials stay in memory.

Run manually; the reproduction notebook never calls this network script.
Password prompt accepts JSON [account, password] using terminal echo suppression.
"""
import argparse
import csv
import getpass
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.parse

HERE = Path(__file__).resolve().parent
BASE = 'https://algorithm.586729.xyz'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, default=HERE / 'protocol.json')
    parser.add_argument('--output', type=Path, default=HERE)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    account, password = json.loads(getpass.getpass('Credential JSON (hidden): '))
    cookie_dir = tempfile.TemporaryDirectory(prefix='agent1-cookies-')
    cookie_path = str(Path(cookie_dir.name) / 'cookies')

    def fetch(path, fields=None):
        command = ['curl', '-sS', '-L', '--max-time', '30', '-b', cookie_path, '-c', cookie_path,
                   '-w', '\n%{http_code}\n%{url_effective}', BASE + path]
        data = None
        if fields is not None:
            data = urllib.parse.urlencode(fields).encode()
            command.extend(['-H', 'Content-Type: application/x-www-form-urlencoded', '--data-binary', '@-'])
        response = subprocess.run(command, input=data, capture_output=True, check=True).stdout
        body, status, url = response.rsplit(b'\n', 2)
        if status != b'200':
            raise RuntimeError('HTTP ' + status.decode() + ' at ' + path)
        return body, url.decode()

    def csrf(page):
        return re.search(rb'name="csrf" value="([^"]+)"', page).group(1).decode()

    page, _ = fetch('/login')
    page, url = fetch('/login', [('csrf', csrf(page)), ('account', account), ('password', password)])
    password = None
    if urllib.parse.urlparse(url).path != '/':
        raise RuntimeError('Login did not succeed')
    protocol = json.loads(args.protocol.read_text())
    for case in protocol['cases']:
        downloaded, _ = fetch('/bank/' + case + '/input')
        if downloaded != (args.protocol.parent / 'inputs' / (case + '.txt')).read_bytes():
            raise RuntimeError('web/local input mismatch: ' + case)
    print('Verified', len(protocol['cases']), 'downloaded inputs against local canonical stdin', flush=True)
    manifest = {'account': account, 'url': BASE, 'jobs': [], 'input_match_count': len(protocol['cases'])}
    for method in ('degree', 'betweenness'):
        page, _ = fetch('/')
        source = (HERE / (method + '.py')).read_bytes()
        fields = [('csrf', csrf(page)), ('source', source.decode()), ('seconds', '10'),
                  ('memory', '512'), ('selection', 'direct')]
        fields.extend(('case', case) for case in protocol['cases'])
        page, url = fetch('/submit', fields)
        path = urllib.parse.urlparse(url).path
        if not re.fullmatch('/jobs/[0-9]+', path):
            raise RuntimeError('Submission did not redirect to job')
        job = {'method': method, 'job_id': int(path.rsplit('/', 1)[1]), 'job_url': url,
               'source_sha256': hashlib.sha256(source).hexdigest()}
        manifest['jobs'].append(job)
        (args.output / 'web_jobs.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(method, 'submitted', job['job_id'], flush=True)
        deadline = time.monotonic() + 1800
        last_state = None
        while True:
            page, _ = fetch(path)
            state = re.search(rb'<p><strong>(.*?)</strong>', page).group(1).decode()
            if state != last_state:
                print(method, state, flush=True)
                last_state = state
            if state not in ('대기', '채점 중'):
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Job still active; inspect without resubmitting')
            time.sleep(5)
        raw, _ = fetch(path + '/csv')
        (args.output / (method + '-web.csv')).write_bytes(raw)
        rows = list(csv.DictReader(io.StringIO(raw.decode())))
        job.update(state=state, result_rows=len(rows), status_counts={s: sum(r['status'] == s for r in rows) for s in set(r['status'] for r in rows)})
        (args.output / 'web_jobs.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
        print(method, 'rows', len(rows), 'statuses', job['status_counts'], flush=True)


if __name__ == '__main__':
    main()
