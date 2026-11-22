# 실행 안내 — 연구 검증과 본 실험

현행 제출 형식과 운영 서버 안내는 [코딩 테스트 실행 안내](../002-coding-test/quickstart.md)에 있다. 이 문서는 공통 평가·시나리오 준비·연구 보고를 다룬다.

## 저장 문제은행

`scenarios/problem-bank/`에 노드 수 6·8·10·12·14인 그래프 72개와 예산별 공개 사례 144개가 있다. 웹과 채점 워커는 `bank.json`의 상대 경로 목록을 공유한다. `inputs/`, `bundles/`, `records/`에 저장 입력, 배포 번들, 원본 탐색 기록이 있다. 사례별 실행 장비와 버전은 각 실행 기록의 `environment`에서 확인한다.

`history/initial-probe/`에는 초기 탐색의 manifest, 진행 및 환경 기록, 미공개 입력 3개, 이후 별도 장비에서 다시 계산한 `n14-seed0-p20`의 초기 기록을 보존한다. `history/expansion-manifest.json`은 후속 탐색에서 사전에 고정한 표본 목록이다.

완전탐색 참조는 유리수 인증, 가능한 조합 전체와 평가 건수의 일치, 예산별 최적안 재채점을 요구한다. 일반 공통 평가에서만 검증 기준에 맞는 제한된 HiGHS 잔차 fallback을 사용할 수 있다. evaluation-v1 번들은 평가 정책이 다르므로 새 스키마로 사용하려면 해당 입력의 정확 탐색·참조·case_id를 다시 준비한다.

## 환경

프로젝트 루트에서 실행한다. 기존 `.venv`가 없다면 생성 후 설치한다.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m ipykernel install --user --name protection-study --display-name 'Protection study (.venv)'
.venv/bin/python -m protection.cli --help
.venv/bin/protection --help
```

CLI는 과학 라이브러리 import 전에 OMP/OPENBLAS/MKL 스레드를 1로 초기화한다. `--help`는 입력·제출 파일을 import하거나 환경/산출물을 변경하지 않는다. 수동 Python 사용에서는 `protection.runner.initialize_single_thread()`를 NumPy/SciPy보다 먼저 호출한다. 기존 수치 라이브러리가 로딩된 커널은 재시작한다.

## 소형 문제은행 사전 준비

아래는 처음 실행할 경로 기준이다. 입력·정확 기록·bundle·채점 산출물은 기본적으로 덮어쓰기를 거부한다. 재실행 시 기존 근거를 삭제하지 말고 manifest의 output_dir 및 명령 출력 경로를 새로운 디렉터리로 바꾼다. 상대 경로는 manifest 부모 기준이다.

```sh
.venv/bin/python -m protection.cli generate --manifest configs/smoke.json
for budget in 20 40; do
  .venv/bin/python -m protection.cli exact --input scenarios/smoke/inputs/n6-seed0.json --budget-percent "$budget" --method exhaustive --run-kind smoke --limit-seconds 120 --output "results/smoke/exact-$budget.json"
  .venv/bin/python -m protection.cli bundle --input scenarios/smoke/inputs/n6-seed0.json --exact-record "results/smoke/exact-$budget.json" --output "scenarios/smoke/case-$budget.json"
  .venv/bin/python -m protection.cli validate --bundle "scenarios/smoke/case-$budget.json" --require-reference
done
```

smoke의 120초는 본 실험 한도가 아니다. 전체 조합과 전달 점수가 인증된 완료 `exhaustive` 기록을 번들로 결합한다. timeout은 기록을 보존하지만 배포할 수 없다. `--method branch_bound`도 지원하며 완료 비교는 `tests/integration/test_exact_pipeline.py`에서 별도 검수한다. 생성 단계는 최적 참조가 없는 **중간 입력**만 만든다.

## 로컬 채점 및 연구 보고

`configs/smoke-grading.json`은 공개 은행에서 n6/seed0의 두 예산을 골라 채점한다. 다른 사례를 쓰려면 각 `bank` 항목의 번들 경로와 실제 `case_id`를 함께 지정한다. 출력 디렉터리를 새로 지정한 후 [위임 서비스 실행 절차](../002-coding-test/quickstart.md#로컬-채점)로 `grade`를 실행한다. 이 파일은 `ready=false`인 로컬 재현용 템플릿이다. `submission.file`을 실제 소스 경로로 지정하고 `ready=true`로 바꿔 사용한다. 웹 제출 소스는 서버의 SQLite에 저장된다.

```sh
.venv/bin/protection report --records results/smoke/member_1/runs.jsonl \
  --bank-manifest configs/smoke-grading.json --output-dir results/smoke/member_1/report
```

채점은 `runs.jsonl`, `batch.json`, `environment.json`을 남긴다. 보고는 `runs.csv`, `summary.csv`, `report.json`을 생성한다. 실패 행은 공식 점수와 격차를 비운다. 성공한 실행은 지표별 중앙값과 범위 및 성공 횟수를 집계한다. 종료 코드는 성공 0, 기록된 실패·미구현·초과나 미완료가 있는 채점/탐색 1, CLI·manifest·입력 오류 2다.

## 소형 노트북

`notebooks/submission.ipynb`는 소형 저장 입력과 두 예산의 인증 참조를 준비하고, 실제 팀원 제출과 구분된 시험 프로그램으로 표준 입출력 채점 및 보고를 실행한다. 초기 노트북의 검증 이력은 `results/validation/notebook.json`과 `submission-executed.ipynb`에 있다. 현행 노트북의 재검증은 위임 서비스 안에서 실행한다.

```sh
systemd-run --user -p Delegate=yes -p DelegateSubgroup=supervisor \
  --working-directory="$PWD" "$PWD/.venv/bin/python" -m pytest tests/integration/test_notebook.py -q
```

## 본 실험 관문

`configs/experiment.json`은 `ready=false`이며 크기·시드가 비어 있다. T054~T056/T060은 [연구 작업 목록](tasks.md)에 둔다. 규모 확인은 승인된 입력으로 직렬 실행하며 실패 기록과 실행 환경을 보존한다. 본 실험에서는 최종 장비·시드·사례를 확정하고 실제 세 팀원 제출로 비교한다. 공개 은행 144개는 별도 사전 준비 데이터다.

## 2026-11-22 연구 보조 실험 재현

`results/agent-study/2026-11-22/study.ipynb`는 저장된 웹 결과와 정확 탐색 기록을 통합한다. 저장소 venv의 protection-study 커널로 처음부터 실행한다. 통계만 다시 계산하려면 다음을 실행한다.

```sh
.venv/bin/python results/agent-study/2026-11-22/analyze_study.py
```

`protocol.json`과 `source-freeze.json`을 먼저 확인한다. 개발20사례와 소스 고정 후 확인32사례를 분리했고, 각 그래프의 두 예산을 묶어 분석한다. `verified_rows.csv` 312행은 원시 웹 CSV의 선택 간선을 공통 평가기로 다시 채점한 결과다. `verify_results.py`는 명시적으로 재채점 검증하며 웹 제출을 생성하지 않는다. agent-1~4/에는 개별 프로그램·원시 결과·문헌·재현 노트북이 있다. `web_experiment.py`는 사용자가 명시적으로 실행할 때 새 실제 제출을 만들므로 저장 결과 재현에는 필요 없다. 알고리즘 프로그램은 웹에 소스로 제출하며 서비스 런타임의 등록 디렉터리는 아니다.

이 자료는 AI 연구 보조 산출물이다. 사람의 개인 과제 기여 확인과 전체 본 실험 완료를 대신하지 않는다.
