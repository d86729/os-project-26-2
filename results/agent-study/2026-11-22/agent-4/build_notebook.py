"""Build a notebook that validates/reproduces the stored exact-study analysis."""
import json
from pathlib import Path
import nbformat as nbf
HERE=Path(__file__).resolve().parent
nb=nbf.v4.new_notebook(cells=[
nbf.v4.new_markdown_cell('''# 정확 탐색과 가지치기 비교 재현
AI 연구 보조 산출물(agent 4). 김대건의 개인 기여 완료를 뜻하지 않는다.

기존 `protection.exact.search`를 재사용한 실험 harness가 담당 코드이다.
노드 6·8, 시드 0·1, 예산 20%·40%, 방법당 60초, 16개 실제 기록을 분석한다.
기본 실행은 저장된 기록과 입력·코드 해시 및 독립 조합 수 DP를 검증한다. 새로운 탐색은 자동 실행하지 않는다.

새 실험은 저장 결과를 덮어쓰지 않는 별도 연구 디렉토리를 준비한 후 저장소 루트에서
`.venv/bin/python results/agent-study/2026-11-22/agent-4/run_experiment.py`를 명시적으로 실행한다.
원래 경로에 records.json이 있으면 runner는 재실행을 거부하여 최초 결과를 보존한다.'''),
nbf.v4.new_code_cell('''from pathlib import Path
import importlib.util, json
root = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p/'protection/exact.py').exists())
here = root/'results/agent-study/2026-11-22/agent-4'
spec = importlib.util.spec_from_file_location('agent4_analysis', here/'analyze.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
summary = module.analyze(write=False)
print('16개 기록·입력/코드 해시·완전탐색 조합 수·참조 점수/동점 규칙 검증 완료')'''),
nbf.v4.new_code_cell('''for name, value in summary['methods'].items():
    print(name, json.dumps(value, ensure_ascii=False))
print('사례별 branch_bound/exhaustive 탐색시간 비의 중앙값:', summary['median_paired_time_ratio'])
print('평가 횟수 총 감소율:', summary['aggregate_evaluation_reduction'])'''),
nbf.v4.new_code_cell('''print('case, exhaustive evaluations, branch_bound evaluations, upper bounds, time ratio')
for row in summary['pairs']:
    print(row['case'], row['exhaustive_evaluations'], row['branch_bound_evaluations'],
          row['upper_bound_calls'], round(row['branch_bound_time_ratio'], 3), sep=', ')
assert all(v['completed']==8 and v['full_tiebreak_matches']==8 for v in summary['methods'].values())
assert all(v['fallback_solves']==0 for v in summary['methods'].values())'''),
nbf.v4.new_markdown_cell('''## 해석과 한계
모든 사례에서 가지치기의 평가 횟수는 줄었지만 n=8 네 조건에서는 시간이 늘었다. 상한 계산 부담과 공통 평가 캐시 때문에 평가 횟수만으로 속도를 예측하기 어렵다는 설명과 부합한다. 원인별 시간 분해를 측정하지 않았으므로 특정 원인의 효과를 확정하지 않는다.

4개 그래프의 두 예산은 독립 8개 그래프로 볼 수 없다. 각 조건의 시간 측정도 1회이므로 유의한 속도 차이로 일반화하지 않는다. 탐색시간은 준비·종료를 제외하며 웹 제출 시간과 직접 비교하지 않는다. 소형·합성 문제의 정확해 검증이지 대형 문제의 계산 가능성 보장이 아니다.

개인 제출 전 김대건이 코드를 이해·수정·직접 실행하고 결과와 문헌을 자신의 말로 설명해야 한다. AI 사용 내역과 기존 공통 코드 재사용 출처를 남긴다.''')])
nb.metadata.kernelspec={'display_name':'Python (protection-study)','language':'python','name':'protection-study'}
nbf.write(nb,HERE/'reproduce.ipynb')
