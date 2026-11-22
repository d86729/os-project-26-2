"""Build a transparent local reproduction notebook; does not submit new web jobs."""
from pathlib import Path
import nbformat as nbf

p=Path(__file__).resolve().parent
cells=[]
def section(title, prose, code):
    cells.append(nbf.v4.new_markdown_cell('## '+title+'\n\n**작성: AI agent 2 / 실제 조원 검토·수정·실행 기록은 별도.**\n\n'+prose))
    cells.append(nbf.v4.new_code_cell(code))
cells.append(nbf.v4.new_markdown_cell('# 공격별 수요 경로 복구 묶음: 재현 노트북\n\n2026-11-22 AI 연구 보조 산출물. 저장된20 개발사례에 대해 소스 실행·입출력 해시·예산을 재검증하고, 실제 웹 CSV를 분석한다. 웹 재제출이나 공식 점수 재계산은 수행하지 않는다. 공식 결과는 job2 및 job4의 CSV이다. 이것은 전체 본 실험 또는 실제 조원의 개인 기여 완료를 뜻하지 않는다.'))
section('1. 저장소와 산출물 확인','문제은행은 이 저장소에서 생성·저장한 합성 데이터이다. 공개 웹 입력20개와 동일한 SHA256을 확인했다. 데이터 경로: scenarios/problem-bank; 접근일2026-11-22.', '''from pathlib import Path
import csv, hashlib, importlib.util, json, subprocess, sys, time
here=Path.cwd().resolve()
root=next(p for p in (here,*here.parents) if (p/'protection/program.py').is_file())
folder=root/'results/agent-study/2026-11-22/agent-2'
sys.path.insert(0,str(root))
from protection.models import Scenario, ScenarioBundle, from_data
from protection.program import scenario_input, protected_ids
metadata=json.loads((folder/'web-metadata.json').read_text())
assert len(metadata['cases'])==20
for run in metadata['runs']:
    assert hashlib.sha256((folder/run['source']).read_bytes()).hexdigest()==run['sha256']
print('고정 소스 확인:',[(r['source'],r['job_id']) for r in metadata['runs']])''')
section('2. 입력과 실제 소스 재실행','최적 참조를 제외한 Scenario 객체만 사용하여 입력을 만든다. 각 프로그램은 별도 프로세스에서10초 안에 종료되어야 한다. 이 로컬 실행은 웹 sandbox와 별개이며 로컬 시간을 공식 시간으로 대체하지 않는다.', '''known=json.loads((folder/'local-validation.json').read_text())
known={(r['case'],r['source']):r for r in known}
reproduced=[]
for case in metadata['cases']:
    raw=json.loads((root/'scenarios/problem-bank/bundles'/f'{case}.json').read_text())
    scenario=from_data(Scenario,raw['scenario'])
    bundle=ScenarioBundle(scenario,raw['budget_percent'],raw['budget'])
    data=scenario_input(bundle)
    for run in metadata['runs']:
        expected=known[(case,run['source'])]
        assert hashlib.sha256(data).hexdigest()==expected['stdin_sha256']
        process=subprocess.run([sys.executable,str(folder/run['source'])],input=data,
                               capture_output=True,check=True,timeout=10)
        ids=protected_ids(process.stdout,bundle)
        assert list(ids)==expected['selected'],(case,run['source'])
        reproduced.append((case,run['source'],list(ids)))
print('입력 해시·결정적 출력·예산 검증:',len(reproduced),'회')''')
section('3. 웹 결과와 그래프 단위 비교','공식 순서는 연결 쌍 우선, 전달 점수 차순이다. 한 그래프의20%·40% 예산은 관련된 관측이므로10개 그래프 블록으로 묶는다. 개발 표본이므로 유의성 주장을 하지 않는다.', '''spec=importlib.util.spec_from_file_location('agent2_analysis',folder/'analyze.py')
analysis=importlib.util.module_from_spec(spec); spec.loader.exec_module(analysis)
summary=analysis.summarize()
print(json.dumps({k:v for k,v in summary.items() if k!='graph_blocks'},ensure_ascii=False,indent=2))
for block in summary['graph_blocks']:
    print(block['graph'],[r['bundle_vs_single'] for r in block['budget_results']],
          '평균 연결률 차이:',round(block['mean_connected_ratio_difference'],6))''')
cells.append(nbf.v4.new_markdown_cell('## 해석과 한계\n\n묶음 후보는1사례에서 공식 점수가 개선되고19사례에서는 동점이었다. 최적 점수 일치는2/20에서3/20으로 늘었으나, 실제 전달 용량을 무시하는 대리지표 때문에 다수 사례의 전달 점수 격차가 남는다. 예산40%에서 같은 그래프의 다른 보호 조합이 필요할 수 있으며, 현재 방법은 선택을 취소하지 않는다. 복잡도는 후보 수를 C, 공격 수를 A, 수요 수를 D, 간선 수를 E라 할 때 최대 E회 반복하며 대략 O(E[AD(E+N)logN + CAN(E+N+D)]) (현재 연결성 구현의 find 연산은 보수적으로 O(N) 상한을 적용)이다. C≤E+AD. 메모리는 후보 전체를 저장하므로 O(E(E+AD)+AE+N+D) 상한이다.\n\n실험은10개 합성 그래프의 예비 비교다. 평균 연결률 차이는 설명 통계일 뿐, 사전식 공식 점수를 하나의 가중 평균으로 바꾸지 않는다. 속도는 CPU 독점 반복 실험이 아니므로 작은 시간 차이는 주의해서 해석한다. 미사용 시드 확인실험과 실제 사람의 설명·수정·실행이 후속 과제다.'))
nb=nbf.v4.new_notebook(cells=cells,metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}})
nbf.write(nb,p/'reproduction.ipynb')
