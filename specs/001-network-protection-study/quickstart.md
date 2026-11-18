# Quickstart — 초기 smoke 구현과 본 실험 관문

## 범위와 실제 근거

공통 생성·평가·정확 탐색·참조 검증·CLI·결과표 및 초기 노트북이 구현되어 있다. `main`/`scale_probe`는 명시적인 준비 완료 manifest가 필요하다. `exact --manifest PATH`는 해당 manifest의 고정 한도를 사용하며 smoke 외 시간 덮어쓰기를 거부한다. `scale-probe --manifest PATH`는 저장 입력을 직렬 처리하고 성공/실패 원본을 보존한다. 이 운영 연결은 시험으로 검증했지만 실제 장시간 본 실험은 실행하지 않았다. `configs/experiment.json`은 `ready=false`, 크기·시드는 빈 값이므로 현재 템플릿의 실행은 종료 코드 2로 거부된다. 사용자 운영 입력이나 장시간 승인을 대신 만들어 넣지 않았다.

실제 검수: `results/validation/cli-notebook-tests.txt`, `results/validation/notebook.json`, 실행된 노트북 `results/validation/submission-executed.ipynb`. 재실행마다 실제 smoke 산출물은 `results/notebook-smoke/run-*/`에 남는다. 이는 최종 연구 제출이나 중대형 규모 확보 근거가 아니다.

세 팀원 파일의 solve는 `NotImplementedError`를 유지한다. 인계·전략 설명의 단일 원본은 `algorithms/member_1.py`~`member_3.py`이다. 미확정 실명·전략·논문 설명은 각 담당자가 작성한다. 공통 생성법은 Dong·Tian (2022), DOI 10.1155/2022/3108327 참고이며 전체 논문 실험 재현·현실 대표성·최적 설정을 주장하지 않는다.

## 최신 정책과 재검증 순서

- evaluation-v2는 유리수 인증 실패 시 HiGHS success/status=0, primal 및 dual stationarity·부호·절대 gap의 유한 최대 잔차 <=1e-7인 경우만 fallback을 허용한다. raw/총 요청량의 6자리 HALF_EVEN을 사용하고 certified_lower/upper=None, certificate_status=highs_residual_fallback으로 구분한다. 유리수 증명이라고 보고하지 않는다.
- evaluation-v1 bundle은 의도적으로 거부한다. 기존 파일의 버전/해시만 바꾸지 말고 v2 입력·정확 탐색·참조·bundle·grading manifest의 실제 case_id를 새 출력 경로에서 다시 준비한다. 아래 기존 검수 기록은 이 정책 변경 후 회귀 통과를 뜻하지 않는다.
- 정확 탐색 T022~T028을 우선 확인한 뒤 runner → CLI → 노트북을 통합 검증한다. runner는 worker 하나에서 Evaluator를 직접 호출하고 부모가 300초와 Evaluator·LP·캐시 포함 전체 RSS 4GB를 감독한다. 평가별 JSON IPC는 없으며 기본 안전 제어/결과 채널과 반환 후 공식 재채점은 유지한다.
- 아래 명령은 재현 안내이며 이 문서 수정 과정에서는 실행하지 않았다. 장시간/main 실행은 별도 승인 없이는 시작하지 않는다.

## 환경

프로젝트 루트 `/root/my-project`에서 실행한다. 기존 `.venv`가 없다면 생성 후 설치한다.

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

smoke의 120초는 본 실험 한도가 아니다. 완료된 `exhaustive` 기록만 bundle로 결합할 수 있다. timeout은 기록을 보존하지만 배포할 수 없다. `--method branch_bound`도 지원하며 완료 비교는 `tests/integration/test_exact_pipeline.py`에서 별도 검수한다. 생성 단계는 최적 참조가 없는 **중간 입력**만 만든다.

## 단일 제출 파일 전체 채점과 보고서

`configs/smoke-grading.json`에는 n6/seed0/두 예산의 실제 계산된 case_id가 고정되어 있다. 파일은 위 준비 단계에서 생성해야 한다. 다른 입력 사용 시 각 저장 bundle의 실제 case_id와 경로를 함께 변경한다. 예산은 bundle에 고정되어 있으며 grade에 예산 덮어쓰기 옵션은 없다.

```sh
.venv/bin/python -m protection.cli grade --manifest configs/smoke-grading.json
# 현재 member_1은 미구현이므로 위 명령의 기대 종료 코드는 1이다.
.venv/bin/python -m protection.cli report --records results/smoke/member_1/runs.jsonl --bank-manifest configs/smoke-grading.json --output-dir results/smoke/member_1/report
```

실제 runner의 `grade_manifest()`를 사용한다. 생성기/정확 탐색을 채점 중 호출하지 않는다. 각 대상의 `not_implemented`를 보존하며 공식 점수와 격차는 null/CSV 빈 셀이다. 단일 제출 파일만 로딩하며 다른 팀원 제출은 선행 조건이 아니다. 무작위 전략은 별도 사전 고정 시드 5개, 결정적은 빈 목록과 1회 실행이다. 최고 실행만 대표로 선택하지 않는다.

출력: `runs.jsonl`, `batch.json`, `environment.json`; report는 `runs.csv`, `summary.csv`, `report.json`을 생성한다. report는 동일 출력 경로의 보고서를 갱신할 수 있으므로 원본 기록은 별도 보관한다.

종료 코드: **0** 성공, **1** 기록된 실행 실패/미구현/timeout 포함, **2** CLI·manifest·입력 오류. 실패 행을 포함한 보고서 생성 자체는 0이다.

## 초기 clean-kernel 재현

```sh
.venv/bin/python -m pytest tests/unit/test_reporting.py tests/integration/test_cli_pipeline.py tests/integration/test_notebook.py -q
```

노트북은 clean kernel에서 생성/저장 → 두 예산 정확 참조 → 배포 검증 → 실제 member_1 미구현 → 원본 결과표 순으로 실행한다. 채점 구역은 정확해를 재계산하지 않는다. 모든 코드 셀 담당자는 김대건이다. 미제출 팀원은 성능 비교에서 제외하며 빈 방호안이나 다른 방법 점수로 대체하지 않는다.

## 외부 관문 — 실행하지 않은 것

- T029/T049/T050 운영 코드는 구현·검증했다. 실제 규모 확인 및 본 실험 실행은 아래 관문과 구분한다.
- T054: 사용자 소형 크기·생성 시드·장비·버전·실명·전략 시드, 별도 장시간 승인, 중대형 서로 다른 세 크기의 실측 규모 확인. 다양한 크기의 고정 문제은행에는 저장할 모든 실제 그래프가 두 예산 각각 단순 완전탐색 10800초(3시간) 내 완료된 경우만 채택하며 이를 넘는 대형 도전군은 제외한다. 이는 저장 문제별 실측 완료 기준이며 전체 그래프 공간의 최악 수행 시간 보장이 아니다. 소형 정확 탐색 600초·팀원 전략 300초는 유지한다. 문서의 시간정책 갱신은 새 실행이나 검증 완료를 뜻하지 않는다.
- T055: 승인된 조건의 본 문제은행과 실제 완료 완전탐색 참조.
- T056/T060: 실제 세 팀원 구현·연구 설명 제출 후 최종 전체 실행과 최종 판정.

초기 테스트 통과는 위 외부 관문 완료를 뜻하지 않는다. 부모 통합 검수는 전체 287 passed, 실패/스킵 0이며 clean-kernel 노트북과 실제 CLI smoke를 포함한다. 실행기 별도 재검증은 47 passed이며 정상/timeout/알고리즘 및 평가 메모리 초과를 실제 확인했다. SciPy의 threads 옵션 전달 경고는 숨기지 않는다.

검증 근거: `results/validation/regression.json`, `exact.json`, `runner.json`, `notebook.json`, `initial_acceptance.json`. 재현 명령은 프로젝트 루트에서 `.venv/bin/python results/validation/run_regression.py`다. 이 명령은 본 실험을 수행하지 않는다.
