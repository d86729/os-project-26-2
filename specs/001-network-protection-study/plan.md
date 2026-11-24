# Implementation Plan: 통신망 방호 연구와 팀원별 문서 내장 골격

**Feature ID**: `001-network-protection-study` | **Spec**: [spec.md](spec.md)

**Input**: 연구 명세와 [코딩 테스트 명세](../002-coding-test/spec.md).

## 현행 구성과 책임

김대건은 합성 시나리오와 공통 점수, 정확 탐색, 결과 기록 및 통합을 담당한다. 세 팀원은 독립 프로그램의 전략 본문과 설명을 작성한다. 제출과 채점 경계는 [코딩 테스트 계획](../002-coding-test/plan.md)을 따른다. 제출 실행은 표준 입출력과 cgroup v2 채점기로 통합한다.

저장 사례는 맵·수요·공격 조건·예산 하나를 포함한다. 배포용 번들은 그 예산의 완전탐색 참조도 담는다. 완전탐색은 점수에 사용된 전달량을 유리수로 인증하고 예산 내 전체 조합을 별도 계산해 평가 건수를 대조한다. 일반 공통 채점은 evaluation-v2의 제한된 잔차 fallback을 허용한다. 공개 문제은행의 데이터와 실행 기록은 [실행 안내](quickstart.md)에 연결한다.

통합 노트북은 소형 사례를 준비하고 별도 표준 입출력 프로그램으로 실행 경로를 검증한다. 본 실험은 승인된 manifest와 팀원 제출을 확보한 뒤 진행한다. 이전 기록과 현행 검증 결과는 [작업 목록](tasks.md)에 남긴다.

## Technical Context

**Language/Version**: Python >=3.11. 현재 호스트 python3는 3.13.5. 프로젝트 venv 설치·검증 후 실제 버전 고정.

**Primary Dependencies**: NumPy(default_rng), NetworkX(공통 그래프 처리), SciPy(linprog method='highs', sparse); 개발 검증 pytest, nbformat, nbclient, ipykernel. stdlib dataclasses/json/decimal/fractions/multiprocessing/resource 사용.

**Storage**: 버전이 있는 JSON 시나리오·manifest, JSONL 실행 기록, CSV 보고서, .ipynb. 시나리오·환경 정보와 계산 실패도 보관한다.

**Testing**: 단위·수작업 오라클·계약·통합 pytest, 실제 작은 LP, 단순/가지치기 일치, 종료·복구·메모리 측정 시험, 노트북 clean-kernel 실행. 성능 결과는 실제 실행 후에만 기록.

**Target Platform**: 단일 Linux 장비. 현행 제출 채점은 cgroup v2 위임과 Bubblewrap이 필요하다. 본 실험 장비는 승인된 manifest에서 확정한다.

**Project Type**: 연구 라이브러리, CLI, 통합 노트북 및 팀원용 웹 코딩 테스트.

**Performance Goals**: 빠른 방법 조건별 300초, 소형 정확 탐색 방법별 600초, 중·대형 단순 완전탐색 조건별 10800초(3시간) 탐색 예산. deadline 후 후보 채택 금지, 종료 정리 시간은 별도 보고. 다양한 크기의 고정 시나리오를 위해 중·대형 크기 세 개를 실측 선정하며 저장할 모든 실제 그래프의 두 예산 각각 단순 완전탐색 10800초(3시간) 내 완료 근거를 요구한다. 이를 넘는 대형 도전군은 제외한다. 이는 저장 문제별 실측 완료 기준이지 전체 그래프 공간의 최악 수행 시간 보장이 아니다.

**Constraints**: 저장 시나리오·예산·정책을 공유하고 조건을 직렬로 실행한다. 수치 계산용 스레드는 하나다. 제출 프로그램은 반복마다 새 상태에서 실행한다.

**Scale/Scope**: 소형 비교는 n=6,8과 두 예산을 사용한다. 공개 문제은행은 n=6,8,10,12,14 사례를 포함한다. 본 실험 크기·시드는 별도 manifest로 확정한다.

## Constitution Check

프로젝트 `.specify/memory/constitution.md`는 존재하지 않는다. 존재하지 않는 헌법 조항을 만들어 통과했다고 주장하지 않는다. 검토 기준은 연구 명세와 코딩 테스트 명세다.

| 게이트 | 설계 전 | 설계 후 근거 |
|---|---|---|
| 사람과 AI 작업의 출처 구분 | PASS | 2026-11-22 승인된 에이전트 연구는 별도 산출물로 기록하고 개인 기여 완료로 간주하지 않음 |
| 인계 형식 | PASS | 파일 내 전략 설명과 코딩 테스트의 제출 규격 |
| 원문 실험·기술 조건 보존 | PASS | 연구 결정과 데이터 모델에 생성·평가·시간·도구 명시 |
| 실패/시간 초과/미구현 은폐 금지 | PASS | 상태 모델, deadline, 실패 예외, nullable 점수 |
| 재현 가능성 및 비교 공정성 | PASS | 저장 번들과 고정 시드, 직렬 실행 |
| 운영 규칙 명확화 | PASS | 표준 입출력 자원 및 상태 기록, 본 실험 승인 관문 |

구현과 환경별 검수 근거는 [연구 작업 목록](tasks.md)과 [코딩 테스트 작업 목록](../002-coding-test/tasks.md)에 기록한다.

## Project Structure

### Documentation (this feature)

```text
specs/001-network-protection-study/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── tasks.md
└── checklists/
    ├── requirements.md
    └── implementation-readiness.md
```

`contracts/`는 사용자 정정으로 사용하지 않는다. 제출 계약은 코딩 테스트 명세가 단일 원본이다. 구현 작업 목록은 [tasks.md](tasks.md)에 생성했다. 작업별 의존성·검증·요구사항 추적 및 초기/최종 관문을 구분하며 실제 구현 완료를 뜻하지 않는다.

### Source Code (repository root)

```text
protection/                  # 공통 구현은 김대건 담당, 진행 상태는 tasks.md 참조
├── __init__.py
├── models.py                # frozen 데이터 모델 및 저장 검증
├── generation.py            # 결정적 시나리오 생성
├── attacks.py               # 기하 피해 목록 사전 준비
├── flow.py                  # 다중 수요 흐름 LP
├── evaluation.py            # 사전식 점수, 최악 공격, 조건별 캐시
├── errors.py
├── exact.py                 # 단순 완전탐색과 가지치기
├── runner.py                # 로컬 채점 배치와 환경 기록
├── program.py               # 표준 입출력과 제출 실행
├── problem_bank.py          # 인증 결과의 예산별 공개
├── web.py                   # 팀원 로그인·제출·워커
├── reporting.py             # 기록·차이·결과표
└── cli.py                   # 사전 준비·일괄 채점·보고 인터페이스 (data-model.md의 CLI v1)
notebooks/submission.ipynb
configs/experiment.json      # 본 실험 전 사용자가 확정하는 manifest
scenarios/                   # 저장 문제은행과 생성 입력
results/                     # 실행 시 생성
pyproject.toml               # 설치·테스트 설정
requirements-lock.txt        # 검증 환경의 실제 고정 버전
tests/
├── unit/
├── contract/
└── integration/
```

**Structure Decision**: 공통 평가·정확 탐색은 Python 패키지에서 공유한다. 로컬 CLI와 웹 워커는 같은 표준 입출력 채점기를 호출한다. 웹 계정·큐·운영 서비스는 코딩 테스트 계획에 정의한다.

## Phase 0 결과

[research.md](research.md)에 역할·도구·생성·LP·반올림·상한·시간·메모리·본 실험 manifest 결정을 정리했다. D-001~008로 생성 호출·수치 인증·안전 상한·프로세스·시드 API·운영 계약을 정했다. 수치 LP와 deadline 구현은 설치 환경에서 반드시 실험 검증한다. 상한의 수치 안전성이 불명확하면 전달률 상한 1로 완화하여 잘못된 가지치기를 방지한다.

## Phase 1 결과

- [data-model.md](data-model.md): 불변 입력, 평가·상한, 상태 및 오류, 캐시, 실행 기록.
- 웹 제출 소스는 SQLite의 `jobs.source`에 보관한다. 채점 시 임시 디렉토리의 `submission.py`로 실행하고 종료 시 정리한다. 제출 계약은 [코딩 테스트 실행 안내](../002-coding-test/quickstart.md#제출-프로그램)를 공유한다.
- [quickstart.md](quickstart.md): 소형 준비, 현재 로컬 채점, 공개 문제은행 및 본 실험 관문.
- 기존 명세·품질 체크리스트의 별도 인계 문서 요구를 최신 사용자 지시로 수정.

## 구현 및 검증 순서

1. 생성·저장·공격 조건과 점수를 수작업 예제로 검증한다. (FR-002~012, FR-025)
2. 소형 사례에서 단순 완전탐색과 가지치기를 비교한다. 공개 은행은 인증 완전탐색의 평가 건수, 재채점 점수 및 두 예산의 등록 조건을 확인한다. (FR-013~016, FR-032~033)
3. 표준 입출력 프로그램을 저장 번들로 실행하고 동일 평가기에서 공식 점수와 실패를 기록한다. 로컬 보고서는 사전식 격차와 성공 실행의 지표별 집계를 사용한다. (FR-017~024, FR-026~027, FR-030~031, FR-034~039)
4. 소형 노트북은 사전 준비와 채점을 분리한다. 본 실험은 T054~T056의 운영 입력과 장시간 실행 승인, 세 실제 팀원 프로그램을 확보한 뒤 시작한다. (FR-028~029)

## 승인된 연구 보조 실행 계획 (2026-11-22)

공통 정리를 262개 테스트로 확인한 뒤 agent 1~3은 서로 다른 휴리스틱을 구현하고 공통 20사례를 웹에서 채점한다. agent 4는 김대건의 정확 탐색·가지치기 비교 코드를 담당한다. 메인은 조건·근거·문헌 중복을 조정하고 Google Docs 날짜 탭에 평가 항목별 결과를 통합한다. 세 개의 하위 실행 슬롯을 사용하므로 agent 4는 먼저 끝난 에이전트 뒤에 투입한다. 각 역할의 실행 가능한 코드와 원시 자료는 results/agent-study/2026-11-22/에 보존한다. 이 승인 범위의 준비 실험은 FR-040~043을 따른다. 전체 본 실험과 실제 조원의 기여 확인은 별도다.

## 2026-11-24 추가 실험과 과제 준비

기존에 고정한 휴리스틱 6개를 동일한 표준 입력으로 새 프로세스에서 각각 실행하고 제출된 방호안을 공통 평가기로 채점한다. 사전 고정한 추가 사례와 실행 조건은 작업 목록 T069와 실험 계획 파일에 둔다. 생성·공격·예산·평가 규칙은 기존 연구 명세를 따른다. 평가 참조는 미리 인증된 번들을 사용한다. 웹 cgroup을 사용할 수 없는 환경에서는 적용한 자원 한도와 시간 경계를 원래 웹 측정과 구분한다.

원자료를 남기고 공식 점수의 사전식 승·무·패, 최적점수 일치, 크기와 예산별 결과 및 그래프 단위 불확실성을 산출한다. 연구 초안, 실행 가능한 기준선 노트북과 면담용 슬라이드를 작성한다. AI가 작성한 전략과 담당자 본인의 기여 여부는 출처를 정확히 기록한다. (FR-044~046, SC-013~014)

발표 준비에서는 네 번호를 사용자의 2026-11-24 배정에 연결한다. Google Docs 체크리스트와 결과 자료의 역할 표를 동기화하며 기존 공통 코드의 작성 이력은 보존한다. (FR-047, SC-015)
