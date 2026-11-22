# Phase 0 — 연구·구현 설계 결정

## 근거와 확인 범위

근거는 프로젝트 원문 `구현_및_제출_기준.txt`, 수정된 spec.md 및 사용자의 직접 확인이다. 대역폭은 10~30 정수 균일 추출로 확정했다. 설계 결정과 아래의 이전 실행 기록을 구분한다. 현행 실행과 재검증 근거는 [연구 작업 목록](tasks.md)과 [코딩 테스트 작업 목록](../002-coding-test/tasks.md)에 기록한다.

## 1. 역할과 인계

- Decision: 세 팀원은 웹에서 독립 Python 소스를 제출한다. 제출 소스의 주석에 전략 설명을 두고 [코딩 테스트 명세](../002-coding-test/spec.md)로 공통 제출 계약을 제공한다.
- Rationale: 사용자 최종 정정이며 코드와 별도 설명의 불일치를 막는다. 서버는 제출 소스를 SQLite에 보관하고 채점 중 임시 파일로 실행한다.
- Alternatives considered: 공통 한 파일에 세 구현, 별도 Markdown 계약, 에이전트의 알고리즘 대리 구현은 제외한다. 공통 데이터 모델 설계 문서는 유지하지만 팀원별 인계 계약을 복제하지 않는다.

## 2. 기술·데이터 보존

- Decision: Python >=3.11, NumPy default_rng(seed), NetworkX, SciPy linprog(method='highs'). pytest로 검사하고 nbformat/nbclient로 노트북을 검증한다. 의존성 설치 후 실제 버전 목록을 저장한다. JSON 시나리오와 JSONL 실행 기록, CSV 결과표를 사용한다.
- Rationale: 원문 기술 제약을 준수하며 시나리오 원본을 도구 버전과 함께 보존한다. frozen dataclass와 tuple을 공개하여 팀원별 입력 변경을 막는다.
- Alternatives considered: pickle은 불투명성과 로딩 보안 때문에 제외한다. 미설치 환경의 가상 버전 목록을 작성하지 않는다.

## 3. 생성·반올림·예산

- Decision: 노드 번호는 0 기반. 좌표 전체 → 연결 전체 → 선 정렬 및 번호 부여 → 대역폭 → 비용 → 수요 쌍 → 요청량 순서로 생성한다. 대역폭은 integers(10,31), 비용은 integers(1,11), 요청은 integers(5,21)로 뽑는다. 후보 기존 노드는 번호순, 선택 직후 현재 차수를 갱신한다. 예산은 정수 분자 20 또는 40으로 total_cost*percent//100을 사용한다.
- Rationale: 배열 순서까지 고정하여 난수 호출 순서와 선 속성 부여를 재현한다. 십진 예산의 부동소수점 버림 오류를 방지한다.
- Alternatives considered: 그래프 반복자의 우연한 순서에 의존하지 않는다. 대역폭 실수 추출은 사용자가 제외했다.
- Proposed design (사용자 별도 확정 아님): 반올림은 Decimal(str(value)).quantize(..., ROUND_HALF_EVEN)로 정의한다. 공격 후보는 9자리 반올림 좌표 자체를 대표 좌표로 사용하고 정렬한다. 전달량 비율의 비교는 6자리 반올림을 백만분율 정수로 저장한다. 원시값도 보존한다.
- Rationale: 반올림 동점 규칙을 통일하고 후보 중복 제거 이후 어떤 좌표를 평가할지 결정적으로 한다. 이 규칙을 경계 시험으로 고정한다.

## 4. 최대 동시 전달량

- Decision: 잔존 무방향 선마다 두 개의 방향 arc를 만든다. 요청 h마다 전달량 t_h와 arc별 흐름 f_h,a를 둔다. 0<=t_h<=d_h, f>=0, 각 방향 arc에서 sum_h f_h,a<=C_a. 출발점의 순유출=t_h, 도착점=-t_h, 나머지=0. 목적함수는 sum_h t_h 최대화이며 linprog에는 음수 목적함수를 전달한다. 희소 행렬로 구성한다.
- Rationale: 요청별 경로 분할, 방향별 독립 용량, 동일 방향의 경쟁을 정확히 표현한다. 연결률과 다르게 수요의 동시성을 반영한다.
- Alternatives considered: 요청별 최대 유량 합산은 공유 용량을 초과하므로 제외한다. 양방향 합산 용량 제약도 원문과 다르다.
- Decision: solver 성공·유한값·흐름 제약 잔차를 검사한다. D-003 evaluation-v2의 유리수 인증을 우선하며 인증 실패에는 제한된 수치 fallback을 허용한다. fallback은 primal 및 dual stationarity·부호·절대 gap의 유한 최대 잔차 <=1e-7을 요구한다. [0,1] 밖 비율을 clip하지 않으며 원시값과 진단을 남긴다.
- Rationale: 실패를 0점으로 둔갑시키지 않는다. 근사 수치 결과가 수학적 기호 최적성을 증명한 것처럼 보고하지 않는다. 정확 탐색의 최적성은 고정된 수치 평가·반올림 규칙 아래의 완전탐색 완료를 뜻한다.

## 5. 상한과 동점 안전성

- Decision: 방호 집합 S와 미결정 집합 U에 대해 S∪U를 모두 방호한 최악 공격 점수를 낙관적 상한으로 사용한다. 비용 제약은 이 상한 평가에서만 면제한다. 상한 점수가 현재 최고 점수보다 엄격히 낮을 때만 점수 가지치기를 한다. 같은 점수는 비용·번호 승자가 남을 수 있으므로 보수적으로 탐색한다.
- Rationale: 선 추가는 각 공격에서 연결 가능성과 전달량을 악화시키지 않는다. 단, 반올림된 사전식 점수의 비교와 수치 오차에 주의한다. 상한 전달량은 전 수요 충족 비율 1을 사용할 수 있으며, 수치 LP 값을 엄밀한 상한으로 증명할 수 없으면 더 느슨한 안전 상한으로 대체한다.
- Alternatives considered: 상한과 최고가 같다는 이유만으로 자르지 않는다. 비용 초과 낙관적 방호안을 실제 해로 내보내지 않는다. 시간 초과 결과에 최적 표시를 하지 않는다.
- Decision: 시간 초과 시 보고하는 전역 상한은 미탐색 및 처리 중인 모든 가지를 포함해야 한다. frontier 전체를 보존하지 못하면 마지막 처리 가지의 상한을 재사용하지 않고 전체 방호 연결 쌍 수와 전달률 1의 안전한 기본 상한으로 돌아간다. 중단 후 탐색 재개는 이번 범위에 포함하지 않으며 체크포인트는 완료 결과 복구용이다.
- Decision: 중·대형 비교용 완전탐색은 단순 완전탐색을 기본으로 한다. 가지치기 결과를 단순 완전탐색 시간으로 혼동하지 않는다. 장비 확인 후 크기를 정하며 이 계획에서 완료 가능한 크기를 추정 확정하지 않는다.

## 6. 초기 클래스 실행기의 시간·중단·메모리

이 절과 D-005~007의 클래스·RSS 설명은 이전 실행기의 설계 이력이다. 현행 제출 실행은 [코딩 테스트 계획](../002-coding-test/plan.md)을 따른다. 공통 실행 환경·입력 준비 완료 후 제출 파일 import 직전부터 최종 반환값이 채점기에 도착할 때까지 300초를 측정한다. 제출 파일 import·클래스 생성·입력 전달·자체 전처리·탐색 중 평가 호출 및 대기·결과 전달을 포함하고, 반환 후 공식 채점은 제외한다. 시간 또는 메모리 초과는 초과 상태를 유지하고 공식 점수를 비워 둔다. 제한 전에 보관한 평가 완료 후보는 진단용으로만 남기며 정식 성적으로 인정하거나 정상 0점으로 바꾸지 않는다. 정상 실행은 반환안을 채점한다. 아래 프로세스·deadline 집행은 구현 설계이며 실제 검증이 필요하다.

- Decision: 한 조건마다 알고리즘 worker 하나에서 Evaluator를 직접 호출한다. 부모는 조건을 직렬 실행하며 전체 시간/RSS를 감시한다. solver time_limit과 단조 deadline을 함께 사용하고 마감에 worker를 종료하며 지연을 별도 기록한다. 기본 결과 채널로 마감 전에 부모가 수신·보관한 완료 후보만 진단 복구 가능하다. 평가 요청/응답별 JSON IPC는 사용하지 않는다.
- Rationale: 평가 사이에서만 시계를 보는 것으로는 긴 LP나 팀원 무한 루프를 제한할 수 없다. 강제 종료 후 메모리 안의 최고 해를 잃지 않도록 완료 후보를 즉시 전달한다. 운영체제 스케줄링 때문에 물리적 종료 시각을 정확히 보장한다고 주장하지 않는다.
- Alternatives considered: Thread 강제 종료, 제한 없는 LP 호출, 마감 후 완료 후보 채택은 제외한다. 종료 후 재채점은 최종 검증용일 뿐 새 후보 선택 기회가 아니다.
- Decision: 시작 전 OMP_NUM_THREADS, OPENBLAS_NUM_THREADS, MKL_NUM_THREADS를 1로 지정하고 HiGHS threads=1 전달 및 실제 동작을 설치 버전에서 시험한다. SciPy가 옵션 전달 경고를 내면 이를 숨기지 않고 설치 버전으로 동작 확인한다. 전략별 중첩 호출 지원은 제공하지 않는다.
- Decision: 평가 대상 worker 전체 RSS에 십진 4GB=4,000,000,000 bytes 상한을 적용한다. Python·라이브러리·입력·Evaluator·최악 공격·LP native 메모리·캐시를 포함하며 초기 RSS/평가 메모리를 차감하지 않는다. 부모 준비와 반환 후 공식 재채점은 별도 경계이며 정확 탐색에는 이 한도를 적용하지 않는다. tracemalloc만으로 RSS를 대체하지 않고 관측·종료는 실제 환경에서 검증한다. Colab 가용 메모리를 보장하지 않는다.

## 7. 실험 구성과 검증의 경계

- Decision (사용자 확정): 단일 알고리즘 파일을 받아 모든 저장 시나리오를 순차 채점한다. 정식 시나리오는 하나의 예산과 완료된 완전탐색 최적 참조를 포함하며 예산마다 별도 파일이다. 채점 시 정확 탐색을 재실행하지 않는다. 팀원은 참조를 보거나 활용하지 않거나 삭제하는 신뢰 약속을 지킨다. 보안 시스템은 추가하지 않는다.
- Decision (사용자 확정): 개발·시험은 허용하지만 공식 실행에서 시나리오별 사전 방호안·탐색 상태·평가 캐시 재사용은 금지한다. 실행마다 새 상태를 사용하고 정확 탐색이나 다른 조건의 평가 캐시를 공유하지 않는다.
- Rationale: 동일 입력·자원 조건으로 제출 알고리즘을 비교하며 사전 계산으로 제한을 우회하지 않는다.
- Alternatives considered: 팀원별 서버, 결과 파일 제출, 매 제출마다 최적해 재계산, 정답 접근 통제는 요구하지 않는다.
- Decision: 문제은행은 난수로 미리 생성·저장하고 모든 전략에 동일한 파일을 사용한다. 공식 채점이나 반복 실행 때 시나리오를 새로 생성하지 않는다. 알고리즘 내부에서 난수를 사용하는 전략만 동일 시나리오에서 사전 고정·기록한 전략용 시드 다섯 개로 5회 독립 실행하고, 결정적 전략은 1회 실행한다. 전략용 시드 목록은 문제 생성 시드와 분리하며 본 실험 전에 고정한다. 반복마다 새 상태와 제출 경로별 독립 자원 한도를 적용한다. 모든 실행의 점수·상태·시간을 보관하고 성공 실행의 연결률·전달량 비율 각각의 중앙값·최솟값·최댓값, 실행 시간, 전체 성공 횟수를 함께 보고한다. 실패는 누락하거나 0점으로 바꾸지 않고, 최고 실행만 대표 성적으로 선택하거나 두 지표를 가중합하지 않는다. 지표별 요약 통계는 실제 단일 방호안의 점수가 아니다. 성공 실행이 없으면 점수 통계는 비워 둔다. 반올림 경계의 LP 잔차 검사만으로 점수 정확성을 보장하지 않는다. 경계 불안정 처리·검증 절차는 구현 전 보완한다.

- Decision: 스모크는 n=6, seed=0, 두 예산으로 제한한다. 본 실험 시드 목록·규모 목록은 명시적 manifest 입력으로 받고 결과 조회 전에 고정한다. 비어 있으면 정식 batch 실행을 거부한다. 사용자가 아직 정하지 않은 본 실험 시드 수를 임의 확정하지 않는다.
- Rationale: 구현 계획에는 임의의 과학적 표본 수 결정이 필요 없다. 다양한 크기의 고정 시나리오를 채택하되 저장할 모든 실제 그래프는 두 예산 각각 단순 완전탐색이 10800초(3시간) 내 완료된 실측 근거가 필요하다. 이를 넘는 대형 도전군은 제외하며 실패·초과 이력은 보존한다. 이는 해당 장비·저장 문제별 완료 확인이지 전체 그래프 공간의 최악 수행 시간 보장이 아니다.
- Alternatives considered: 스모크 결과를 본 실험으로 대체하거나 시간 초과 시드를 누락하는 방식은 제외한다.

전략별 지원은 제공하지 않는다. 문제은행 manifest·전략 시드 목록·팀원 실명·실제 알고리즘 제출은 본 실험 전 준비할 운영 입력이다.

## 8. 구현 기준선 D-001~D-008

이 절은 위 Proposed design을 해소하는 구현 설계 결정이다. 사용자 연구 규칙의 추가 확정이나 실제 검증 통과가 아니다. 위 제안과 충돌하면 이 절을 따른다. 정책 변경은 버전과 case_id를 바꾸며 참조를 재생성한다. 검증 실패 시 배포/공식 채점 관문을 닫고 진단을 남긴다.

### D-001 생성 호출 순서 — T007/T010/T014
- Decision: generation-v1. NumPy default_rng(seed) 하나로 rng.random((n,2)) 한 번 → 초기 삼각형 (0,1),(0,2),(1,2) → 신규 노드 번호순 연결. 기존 후보 번호순으로 degree/max(distance,1e-9)^3를 float64로 계산·정규화하고 rng.choice(candidate_ids,p=weights)를 두 번 호출한다. 첫 연결 즉시 차수를 갱신하고 선택 상대를 제외해 두 번째 확률을 다시 계산한다. 모든 선을 (u,v)순 정렬 후 rng.integers(10,31,size=m), rng.integers(1,11,size=m) 각각 한 번. 방향쌍은 source,target 번호순 열거하고 rng.choice(n*(n-1),size=n,replace=False)의 반환 순서로 demand id를 부여한다. 요청량은 rng.integers(5,21,size=n) 한 번. seed는 bool이 아닌 음이 아닌 정수다. 실제 rng.bit_generator 클래스명·NumPy 버전·generation-v1을 생성 메타데이터에 기록하며 비유한 가중치/합계 또는 정규화 불가 시 InvalidScenarioError로 중단한다. 균일 추출로 대체하지 않는다.
- Rationale: 분포뿐 아니라 배열·호출 순서도 고정한다. 공식 입력은 저장본이며 NumPy 버전 간 재생성 동일성은 보장하지 않는다.
- Alternatives considered: 노드별 속성 혼합 생성, 연결 두 개 일괄 추출, 수요 쌍 추출 후 재정렬은 제외한다.

### D-002 반올림·기하 — T006/T011/T018
- Decision: evaluation-v2는 Decimal(str(value)), precision=50, ROUND_HALF_EVEN. 후보 좌표는 1e-9 단위 정수 (x_units,y_units)로 양자화하여 중복 제거·좌표순 정렬하고 그 대표 좌표 자체를 공격 중심으로 사용한다. -0은 0으로 정규화한다. 중점은 원래 float64 좌표의 (u+v)/2, 격자는 정수 i/5로 만든 뒤 같은 양자화를 적용한다. 원래 노드 좌표를 덮어쓰지 않는다. 선분 투영은 [0,1]로 제한하고 영길이 선은 점 거리로 계산한다. 공격 거리는 기존 R+1e-9 경계를 유지한다. 이전 evaluation-v1 bundle은 정책 혼합 방지를 위해 의도적으로 거부하며 기존 참조를 v2로 단순 재표기하지 않는다.
- Rationale: 중복 제거 후 최초 후보를 임의 대표로 쓰지 않으며 좌표 동점과 실제 평가 위치를 통일한다.
- Alternatives considered: float round 혼용, HALF_UP 혼용은 제외한다. HALF_EVEN은 구현 선택이며 사용자 확정으로 소급하지 않는다.

### D-003 LP와 점수 경계 — T012/T017/T018
- Decision: linprog(method='highs'), presolve=True, primal_feasibility_tolerance=1e-9, dual_feasibility_tolerance=1e-9, ipm_optimality_tolerance=1e-10, threads=1, 호출별 남은 deadline을 time_limit으로 전달한다. solver success·유한값·흐름 보존/용량/요청 경계 잔차 <=1e-7*max(1,해당 우변 절댓값)를 모두 검사한다. 성공 플래그만으로 점수를 확정하지 않는다.
- Decision: 반올림 안정성은 잔차와 별개다. 정수 계수 LP의 primal/dual 해를 Fraction(str(value)).limit_denominator(1_000_000_000)로 복원해 원래 LP와 변수 경계에 대한 가능성을 정확한 유리수 연산으로 검증한다. 흐름 변수에는 해당 arc 용량의 중복 상한도 둔다. 최소화 부호와 상하한 marginal을 원래 최대화 dual로 변환해 검증한다. 검증된 primal 목적값 L과 dual 목적값 U만 인증 구간으로 사용한다. 유리수 인증 경로에서는 L<=U이고 [L,U]/총 요청량 전체가 동일한 6자리 HALF_EVEN 정수로 반올림될 때 인증된 delivery_units를 확정한다. 불일치는 아래 v2 fallback 조건으로 별도 판정한다. 정확한 midpoint L=U도 Fraction 기반 정수 나눗셈의 HALF_EVEN으로 처리한다. 복원은 기존 LP 해의 검증이지 다른 최적화 solver가 아니다.
- Decision: evaluation-v2는 유리수 인증 실패 또는 반올림 구간 불일치 시 HiGHS success 및 status=0, 유한 최대 수치 잔차 <=1e-7인 경우 fallback을 허용한다. primal 보존·용량·변수 경계·목적값 일치와 dual stationarity·marginal 부호·절대 primal-dual 목적값 gap까지 검사한다. 단순 성공 플래그나 primal 가능성만으로 허용하지 않는다. 원시 전달량/총 요청량을 6자리 HALF_EVEN으로 반올림하여 units를 만들고 diagnostics.certified_lower/upper=None, certificate_status='highs_residual_fallback'으로 기록한다. 이는 유리수 인증이나 엄밀한 목적값 오차 증명이 아니다. raw가 [0,total] 밖이면 실패하며 epsilon/clip은 금지한다. fallback 조건도 실패하면 남은 시간 안에서 presolve=False로 한 번 재시도하고 최대 두 번 후 EvaluationError로 미완료 처리한다. 원시값·잔차·시도·상태를 보존하고 모든 시간은 평가 호출 시간에 포함한다.
- Decision: 인증의 부호/경계 정의를 고정한다. SciPy 최소화는 c의 t 성분=-1, f 성분=0, Gx<=b, Ax=0, 0<=x<=u이며 t 상한은 수요, f 상한은 해당 arc 용량이다. 복원된 dual y(부등식)<=0, z(등식)는 자유, p(하한)>=0, q(상한)<=0에 대해 c=G^T y+A^T z+p+q를 정확히 확인한다. dual 최소화 하한 D=b^T y+u^T q이며 최대 전달량의 인증 상한 U=-D, primal 인증 하한 L=sum(t)이다. primal은 모든 제약/경계를 정확히 만족해야 한다. L/U/총 수요는 유리수로 계산하며 float 잔차 허용치를 이 인증에 쓰지 않는다. 최종 채점처럼 알고리즘 deadline이 없는 호출은 time_limit을 생략하며 최대 두 번의 solver 시도만 허용한다.
- Rationale: 잔차나 반복 결과 일치는 최적 목적값 오차의 증명이 아니다. 정확 최적성은 evaluation-v2 평가 정책 아래의 완전탐색 완료를 뜻한다. 허용된 fallback과 실제 평가 실패를 구분하며 fallback 수치를 인증 상한으로 사용하지 않는다. 평가 미완료이면 배포하지 않는다.
- Alternatives considered: 잔차를 목적함수 오차로 간주, 경계에서 임의 epsilon, 재실행 일치만으로 인증은 제외한다.

#### D-003 이전 evaluation-v1 검증 기록 — 현재 v2 검증과 구분

- 현재 계약: `protection/flow.py::maximum_delivery`는 유리수 인증을 시도하고 실패 시 위 v2 잔차 검사를 통과한 수치 fallback도 반환한다. `DeliveryResult`의 units는 인증 경로 또는 명시적 fallback 경로에서 나오며 `SolverDiagnostics`로 구분한다. 아래 수치/시험 로그는 **이전 v1 정책의 역사적 기록**으로만 보존한다. v2 통과 근거나 새 benchmark가 아니며, 특히 작은 잔차의 인증 실패를 항상 거부했던 시험 기대값은 v2에 맞게 재검증해야 한다.
- 재현 명령: `.venv/bin/python results/validation/run_numeric_policy.py`. 실제 환경·12개 생성망 원시 인증 결과·전체 pytest stdout/stderr·명령·종료 코드는 `results/validation/numeric-policy.json`; 개별 로그는 `numeric-focused.txt`, `numeric-regression.txt`이다. n=3/6/8, seed=0에서 빈/전체/짝수/홀수 잔존선 각각을 직렬 실행했고 12개 모두 첫 시도에 L=U 인증을 통과했다. 이는 작은 개발 검증이며 본 실험 시드 선정이나 일반적인 인증 성공률 추정이 아니다.
- 집중 명령 `.venv/bin/python -m pytest tests/unit/test_flow.py tests/unit/test_policy.py tests/unit/test_numeric_policy.py -q`: **29 passed, 22 warnings in 2.05s**. 기존 flow 6개를 수정 없이 통과했다. 실제 설치 HiGHS에 정수 계수 `2000000*t<=1` 및 `<=3` LP를 풀어 정확 비율 1/2000000, 3/2000000의 HALF_EVEN units 0, 2를 확인했다. 이 midpoint 시험은 일반 정수 LP이며 시나리오 입력 범위의 통신망이라고 주장하지 않는다.
- 명시적 시험 대역은 실제 solver 결과의 primal/marginal을 오염시켜 sign/stationarity·정확 가능성 실패, 유한성/잔차 실패, presolve=False 재시도와 최종 실패를 확인한다. 1e-8 보존 잔차는 float 검사에는 통과해도 정확 인증에서 거부되고, 2e-7은 잔차 단계에서 거부된다. 가능하지만 비최적인 영 primal과 실제 dual의 [0,20] 구간은 numeric_ambiguity로 거부한다. solver 및 인증 도중 deadline 초과 결과도 채택하지 않는다. 대역 결과는 실제 solver 성능 자료로 사용하지 않는다.
- 필터/스킵 없는 `.venv/bin/python -m pytest -q`의 해당 공유 작업공간 실행 결과: **155 passed, 23 warnings in 6.40s**, exit 0. 실행 당시 다른 작업에서 추가된 `Evaluator`가 존재하여 이전의 3개 Evaluator 부재 실패는 재현되지 않았다. 이번 수치 작업은 evaluation.py·캐시·T019 이후를 구현하거나 완료 표시하지 않았으며, 이 통과 기록을 전체 연구/MVP 완료로 해석하지 않는다. 초기 flow+numeric 예상 실패 로그는 `numeric-before.txt` (flow 모듈 부재, 20 failed)로 보존한다.
- 당시 v1에서는 Fraction 복원 불가/구간 불안정을 미완료 처리했다. 현재는 위 v2 fallback 조건으로 대체되며 가상 인증·epsilon·clip은 여전히 금지한다. `threads=1` 경고를 숨기지 않고 인증/수치 검사 시간도 elapsed_seconds에 포함한다. 대형망 비용·범용 성공률·새 정책의 통합 검증을 이 이전 로그로 주장하지 않는다.


### D-004 안전한 정확 탐색 — T022~T028
- Decision: 선 id 순 include/exclude DFS. 빈 집합부터 유효 incumbent를 평가한다. 빈 집합 사전 평가도 deadline 안이며 leaf에서 중복 평가하지 않는다. 나머지 조합은 DFS leaf에서 한 번씩 평가한다. 단순 완전탐색은 예산 초과 제외 외 점수 가지치기 없이 유효 조합을 한 번씩 평가한다. 가지치기는 S∪U 가상 방호에서 공격별 정수 연결 쌍의 최솟값 c를 구하고 기본 상한 (c,1_000_000)을 사용한다. 전달률을 조이려면 D-003의 검증된 dual 상한이 있어야 하며 인증 불가면 1_000_000으로 돌아간다. 예산 면제는 내부 상한 함수에만 허용한다.
- Decision: 정확 탐색의 실행 감독은 T024/T026에서 먼저 구현한다. 정확 탐색 worker는 자체 평가하며 팀원용 메모리 한도가 없고 공통 평가 RSS를 빼지 않는다. 감독자는 monotonic deadline·완료 incumbent 수신·강제 종료를 담당한다. LP/유리수 인증/그래프 순회 중에도 종료가 동작해야 한다. 이는 T035 이후에 의존하지 않는 US2 경로이며 exact_peak_rss_bytes를 기록한다. T022~T028을 runner·CLI·노트북보다 우선 확인한다. D-005~006은 이전 클래스 실행기 설계다.
- Rationale: 상한이 incumbent보다 사전식으로 엄격히 낮을 때만 가지치기한다. 같은 점수는 비용/번호 tie 때문에 보존한다. 중단 전역 상한은 incumbent와 모든 미해결/처리 중 가지 상한의 사전식 최댓값으로 전체 frontier를 덮거나 universal=(n*(n-1)//2,1_000_000)로 기록한다.
- Alternatives considered: float 목적값을 상한으로 바로 사용, 동점 가지 제거, 단일 가지 상한을 전역 상한으로 사용은 제외한다.

### D-005 이전 클래스 실행기의 실행 경계와 통신 — T031/T035~T038
- Decision: multiprocessing spawn으로 부모 감독자와 알고리즘 worker 하나를 둔다. worker의 ExecutionContext는 같은 프로세스의 Evaluator를 직접 동기 호출한다. 평가 worker·평가별 JSON 요청/응답 IPC는 없다. 공통 환경·입력·공격 준비·빈 캐시·채널 준비 후 READY, 부모가 monotonic_ns로 t0를 찍고 START를 보내면 제출 import·생성·입력/context 전달·solve를 시작한다. 사전 검수에서 제출 코드를 실행/import하지 않는다.
- Decision: 기본 안전 제어/결과 채널은 유지한다. READY/START, 완료 후보 진단 통지, FINAL/오류를 제한된 크기의 검증 가능한 데이터로 전달하고 임의 제출 객체를 unpickle하지 않는다. 후보 평가 결과 전체를 매 호출 직렬화하지 않는다. 반환 list 길이·타입·중복·범위를 검사한다. 부모가 최종 결과 전체를 수신한 tr<t0+limit일 때만 정상 반환이며 worker 자체 시각은 증거가 아니다. 최종 RSS 관측 뒤 ACK/정리하고 반환안은 부모가 공식 재채점한다. tr 이후 공식 채점 시간은 300초 밖이며 중간 최고로 반환안을 대체하지 않는다. 마감 전에 실제 수신·보관한 완료 후보만 진단 복구한다.
- Decision: timeout이면 worker 내 진행 중 LP도 worker 종료로 중단한다. worker terminate → 최대 0.2초 join → 남으면 kill → 최대 1초 join. 잔류 시 환경 실패로 batch를 중단한다. 기본 채널 EOF/잘못된 결과는 명시적 실패로 처리하며 평가 IPC 전용 fault matrix는 만들지 않는다. 동시 RSS 초과/deadline은 memory_limit 우선으로 둘 다 기록하고 최종 RSS·종료 지연을 보존한다.
- Rationale: import/생성/전달 지연 포함과 완료 후보의 수신 경계를 구현 가능한 절차로 고정한다.
- Alternatives considered: fork 캐시 상속, worker 시각 신뢰, timeout 이후 반환 채택은 제외한다.

### D-006 이전 클래스 실행기의 RSS 관측 — T032/T039
- Decision: Linux /proc/<pid>/status의 VmRSS/VmHWM를 KiB→bytes 변환한다. START 직전 기본 RSS, 실행 중 목표 간격 10ms, FINAL 수신/종료 직전 표본을 기록한다. 감독자는 IPC·종료·다음 표본·deadline 중 가장 빠른 이벤트까지 대기하며 큰 frame이 감시를 굶기지 않게 한다. 실제 최대 관측 간격을 기록한다. 생존 중 VmRSS 또는 VmHWM>4_000_000_000이면 memory_limit이며 같으면 허용한다. peak는 가용 VmHWM와 표본 최대의 최댓값이고 초기값을 차감하지 않는다.
- Decision: /proc 미지원·권한 오류·생존 중 측정 실패는 failed/resource_monitor_unavailable, main 거부. 종료로 /proc이 사라지면 마지막 표본과 종료 원인을 보존하고 근거 없는 OOM을 memory_limit으로 단정하지 않는다. 평가/LP/캐시는 worker 전체 RSS에 포함하며 별도 평가 RSS를 추정·차감하지 않는다. 기존 evaluation_peak_rss_bytes 필드가 남으면 null로 둔다. 관측 초과 증거 없는 MemoryError/OS 종료는 확인 범위에 따라 failed로 기록한다.
- Rationale: 표본 감시는 연속 하드 제한이 아니며 짧은 spike 누락 가능성이 있다. T032에서 실제 장비 동작을 검증한다. 별도 process/외부 계산 금지는 신뢰 조건이며 감시 기능을 추가하지 않는다.
- Alternatives considered: tracemalloc, RLIMIT_AS를 RSS로 보고, 평가 peak 사후 차감은 제외한다.

### D-007 초기 시드와 클래스 등록 — T034/T035/T040/T042
- Decision: 채점기 manifest에 method_id/file/class_name/uses_randomness/algorithm_seeds/owner/strategy_name/strategy_version을 둔다. 무작위는 서로 다른 음이 아닌 정수 시드 정확히 5개, 결정적은 빈 목록과 1회 algorithm_seed=null. 읽기 전용 context.algorithm_seed:int|None, context.repeat_index:int(0부터), context.repeat_count:int(5 또는 1)를 제공하고 solve 시그니처는 유지한다. 문제 생성 seed와 별도 namespace이며 우연히 같은 숫자는 허용한다. 공통 계층은 팀원 RNG를 대신 만들거나 전역 RNG를 seed하지 않는다. 실행별 RNG는 solve 진입 후 전달 시드로 초기화하며 import/무인자 생성자는 실행별 무작위 선택이나 시나리오 의존 계산을 하지 않는다.
- Rationale: 모든 문제에 같은 고정 목록을 같은 순서로 전달하며 팀원에게 추가 설정 파일 제출을 요구하지 않는다.
- Alternatives considered: solve 인자 추가, scenario.seed 덮어쓰기, 특정 난수 전략 강제는 제외한다.

### D-008 초기 운영 인터페이스 — T009/T046/T049/T050
- Decision: CLI/manifest/결과 형식을 data-model.md의 공통 운영 계약과 quickstart.md 목표 명령으로 고정한다. contracts/는 생성하지 않으며 팀원별 인계는 계속 클래스 docstring에만 둔다.
- Rationale: 구현 단계에 인터페이스 결정을 떠넘기지 않고 기존 Spec Kit 산출물 안에서 설계를 완결한다.
- Alternatives considered: CLI 철자를 구현 때 결정, 별도 웹 서비스는 제외한다.

## 9. 현행 완전탐색 참조와 표준 입출력

- 완전탐색은 `require_certificate=True`로 전달 점수를 계산한다. 점수에 사용할 유리수 증명이 없으면 해당 탐색을 실패로 기록한다. 가능한 집합 수를 배낭 DP로 독립 계산하고, 탐색이 보고한 평가 건수와 대조한다. 참조 생성은 실행 기록의 fallback 0건도 검사한다.
- 공개 문제은행은 조건별로 채점 잠금을 사용한다. 고정 시드의 두 예산 각각 준비·탐색·종료 시간의 합이 10,800초 미만이며 번들 검증까지 완료된 그래프를 공개한다.
- 현행 제출은 새 Python 프로세스의 stdin/stdout을 사용한다. 실행별 cgroup v2에서 제출과 자손을 제한하고 제출 종료 후 별도 공통 평가를 한다. 제출의 구체적 자원 한도와 웹 결과 계약은 [코딩 테스트 명세](../002-coding-test/spec.md)에 있다.
