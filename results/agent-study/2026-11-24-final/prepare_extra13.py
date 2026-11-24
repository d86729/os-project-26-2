"""Register four newly certified cases as a separate supplementary comparison."""
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
    base = json.loads((HERE / 'protocol.json').read_text())
    cases = []
    for seed in (2128805146, 824558948):
        for percent in (20, 40):
            name = f'n13-seed{seed}-p{percent}'
            path = f'scenarios/problem-bank/bundles/{name}.json'
            bundle = load_bundle(ROOT / path, require_reference=True)
            cases.append({'name': name, 'n': 13, 'seed': seed, 'budget_percent': percent,
                          'path': path, 'case_id': bundle.case_id,
                          'stdin_sha256': sha256(scenario_input(bundle)).hexdigest()})
    data = {'registered_at_utc': datetime.now(timezone.utc).isoformat(),
            'purpose': '새로 인증한 n=13 네 사례의 별도 추가 확인; 기존 20사례 본 분석에 합산하지 않음',
            'cases': cases, 'methods': base['methods'], 'execution': base['execution'],
            'predefined_contrasts': base['predefined_contrasts'],
            'selection': '사전 고정 시드 2개에 대한 인증 성공 여부만으로 선택; 성적 무관',
            'graph_cluster': '동일 그래프의 두 예산을 묶어 해석'}
    for method in data['methods']:
        assert sha256((ROOT / method['path']).read_bytes()).hexdigest() == method['sha256']
    path = HERE / 'protocol-extra13.json'
    if path.exists():
        raise RuntimeError('extra protocol exists')
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print('Registered', len(cases), 'separate cases and', len(data['methods']), 'methods')


if __name__ == '__main__':
    main()
