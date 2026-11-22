# Phase 1 — 공통 데이터 모델

공통 데이터와 파일 계약을 정의한다. 현행 팀원 프로그램의 표준 입출력 형식은 [코딩 테스트 실행 안내](../002-coding-test/quickstart.md#제출-프로그램)에 있다.

## 배포 컨테이너 — ScenarioBundle

최신 파일 스키마는 맵만 저장하던 이전 설계를 확장한다. Scenario는 알고리즘에 전달하는 불변 맵·가중치·수요 모델로 유지하고, 디스크 파일은 ScenarioBundle로 정의한다.

- schema_version:int, scenario:Scenario, budget_percent:int, budget:int, case_id:str, optimal_reference:OptimalReference (배포 원본 필수, 팀원 삭제 사본에서는 생략 허용).
- OptimalReference: protected_ids, cost, evaluation, method=exhaustive, status=completed, optimality_proven=true, exact_run_id, 환경·제한·실행 시간 등 완료 근거.
- 생성 단계의 중간 맵 파일과 미완료 탐색 기록은 배포 원본과 구분한다. 배포 번들 생성은 인증 완전탐색 완료, 배낭 DP와 일치하는 평가 건수, `highs_residual_fallback_solves=0`을 원 실행 기록에서 확인한다. 번들 검증은 참조 방호안의 유효성과 인증 재채점 결과를 확인한다.
- case_id는 맵·수요·예산·공격 및 평가 정책 등 문제 입력의 canonical JSON 해시이며 최적 참조를 제외한다. 따라서 참조 삭제 전후 동일한 실험 조건으로 인식한다. scenario_id는 기존 맵 입력 식별자로 유지한다.
- 전체 파일 체크섬을 별도로 기록하는 경우 참조 삭제에 따라 바뀌는 것이 정상이며 case_id와 혼동하지 않는다.
- 제출 프로그램에는 번들의 사례·예산·전략 시드를 stdin으로 전달한다. 번들과 최적 참조는 채점기가 읽는다.
- 최적 참조 없이도 실행·최악 공격 채점은 가능하다. 최적 격차 계산에는 case_id가 일치하는 평가자 원본 참조가 필요하다. 예산만 바꿔 기존 참조를 재사용하면 오류로 처리한다.

## 불변 입력 — protection.models

모두 frozen dataclass, 중첩 컬렉션은 tuple로 정의한다. 번호는 0 기반이며 인덱스와 같다. float에는 NaN/Infinity를 허용하지 않는다.

### Node
- id:int, x:float, y:float
- 0<=x,y<1, id 중복 없음.

### Edge
- id:int, u:int, v:int, capacity_mbps:int, cost:int
- u<v, 양 끝점 존재, 자기·평행 선 금지. (u,v) 사전식 정렬 후 id 부여.
- 10<=capacity_mbps<=30, 1<=cost<=10. 두 방향 각각 capacity_mbps를 공유 용량으로 사용한다.

### Demand
- id:int, source:int, target:int, amount_mbps:int
- source!=target, 기지 존재, 방향별 쌍 중복 없음, 5<=amount_mbps<=20.

### Scenario
- attack_settings:AttackSettings, evaluation_policy:EvaluationPolicy — 최적 참조 없이도 공격·채점 조건을 확인할 수 있는 불변 공개 정보. 반경·후보 규칙·거리 허용오차·점수 우선순위·반올림 자릿수 및 정책 버전을 포함한다. 반올림·인증/fallback 규칙은 아래 evaluation-v2 및 research.md D-002~003을 따른다.
- schema_version:int (=1), scenario_id:str, seed:int
- nodes:tuple[Node,...], edges:tuple[Edge,...], demands:tuple[Demand,...]
- generation:GenerationSettings (alpha=1,beta=3,m0=2,rho=1,min_distance=1e-9), environment:tuple[tuple[str,str],...]
- n>=3, 공격 전 연결 그래프, 수요 개수 n. 순서 및 ID 불변.
- scenario_id는 schema_version 및 생성 설정·시드·nodes/edges/demands를 canonical JSON으로 직렬화한 SHA-256. 생성 시각과 환경의 비본질적 메타데이터는 해시에서 제외한다. 이 ID는 생성된 맵·수요를 식별하며 예산·공격·평가 정책까지 포함한 실험 동일성은 case_id로 판단한다.
- JSON 로딩 때 범위·중복·연결·해시를 검증한다. 저장 형식은 dataclass 필드 이름을 그대로 쓰고 tuple은 배열로 표현한다. 쓰기는 임시 파일 후 원자적 교체로 한다.

### ExperimentCondition
- scenario_id:str, budget_percent:int (20|40), budget:int
- method:str (exhaustive|branch_bound|member_1|member_2|member_3)
- limit_seconds:float, algorithm_memory_limit_bytes:int|None; generation_seed는 Scenario에 보관한다. algorithm_seed와 repeat_index는 별도 실행 메타데이터로 전달하고 전략용 시드 목록은 사전에 고정·기록한다. 무작위 전략은 동일 저장 문제에서 5회, 결정적 전략은 1회 실행한다. 현행 로컬 채점 한도는 6,000,000,000 bytes이며 웹은 256~6000MB를 선택한다. 정확 탐색에는 제출 프로그램의 메모리 한도를 적용하지 않는다. stdin에는 전략 시드만 전달하며 repeat_index와 repeat_count는 RunRecord 메타데이터로 보존한다.
- budget=sum(cost)*budget_percent//100. 본 실험 시간은 소형 정확 탐색 600, 중·대형 단순 완전탐색 10800, 빠른 방법 300초.
- 스모크·단위 시험의 짧은 제한은 명시적 test/smoke 표식을 기록하며 본 실험 결과와 섞지 않는다.

## 공통 준비 데이터

### AttackCandidate / PreparedAttacks
- AttackCandidate: id:int, x:float, y:float, damaged_edge_ids:tuple[int,...]
- 기지·중점·격자 합집합을 9자리 반올림 후 중복 제거·좌표순 정렬.
- 반경 0.15, tolerance=1e-9. 선분이 영길이이면 점 거리로 계산한다.
- PreparedAttacks: scenario_id, attack_settings 및 정책 버전, candidates:tuple[AttackCandidate,...], preparation_seconds:float.
- 잔존선은 전체 선에서 damaged_edge_ids 중 비방호 선만 제외한다.

## 평가 출력 — protection.models

### Evaluation
- protected_ids:tuple[int,...], cost:int
- connected_pairs:int, connected_ratio:float
- delivered_mbps:float, delivery_ratio:float, delivery_units:int
- worst_attack:tuple[float,float]
- delivery_units는 6자리 HALF_EVEN 반올림 비율의 백만분율 정수. evaluation-v2의 유리수 인증 구간 또는 명시적인 HiGHS 잔차 fallback을 사용한다. 0<=delivery_units<=1000000. fallback은 유리수 증명이 아니다.
- 비교는 (connected_pairs,delivery_units) 최대화, cost 최소화, protected_ids 사전식 최소화. 전달량 원시값과 잔차·solver 상태는 별도 진단 레코드에 기록한다.
- 정수 연결 쌍은 성분 크기별 s*(s-1)//2 합이며 비율 분모 n*(n-1)//2. 반올림 연결률로 비교하지 않는다.
- 최악 공격 선택은 점수 최소화, 최종 좌표순. 동일 잔존망 점수 캐시는 scenario_id+잔존선 bitmask+평가 정책 버전으로 키를 만든다. 실패·미완료는 캐시하지 않는다.
- 캐시는 실행 조건마다 빈 상태에서 시작한다. 공통 피해 목록만 공유하며 다른 방법 실행으로 데워진 평가 캐시는 공유하지 않는다.

### UpperBound
- connected_pairs:int, delivery_units:int, source:str, certified:bool
- source는 all_protected 또는 optimistic_remaining 또는 universal.
- 비용·번호 순위는 상한 점수에 포함하지 않는다. 같은 점수 가지는 보수적으로 유지한다.
- 전달량 LP 결과가 증명 가능한 상한이 아니면 delivery_units=1000000으로 느슨하게 둔다. 상한 실패 때문에 가상 점수를 만들어 내지 않는다.

## 제출 실행

웹 소스는 SQLite에 저장된다. 채점 워커는 프로그램에 시나리오를 표준 입력으로 전달하고 출력한 간선 목록을 공통 평가기로 평가한다. 시간·메모리·CPU 한도는 실행별 cgroup v2와 감독자가 집행한다. 구체적 계약은 코딩 테스트 명세를 따른다.

## 오류 — protection.errors

- InvalidScenarioError: 저장 데이터·생성 설정 오류.
- InvalidProtectionError: 잘못된 정수(불리언 포함), 순서·중복·선 번호·예산 위반.
- EvaluationError: LP 실패 또는 유효성 검사 실패. 정상 점수는 반환하지 않는다.
- DeadlineExceeded: 전체 시간 종료. 완료 후보는 진단용으로만 복구하며 정상 완료나 정식 성적으로 전환하지 않는다.
- 표준 입출력의 미구현은 종료 코드 75다. 종료 코드 75는 not_implemented 상태로 기록한다.

## 실행 기록·상태 전이

현행 CLI는 사례를 검증하고 단일 Python 프로그램을 조건별로 새로 실행한다. 개별 실행 오류는 행을 남기며 manifest·사례·파일 읽기 오류는 배치 입력 오류로 처리한다.

공통 schema/manifest v1과 evaluation-v2는 별도 버전이다. 구현 및 검증 상태는 작업 목록을 따른다.

### RunRecord
- run_id, condition, status, termination_reason, started_at, environment
- submitted_protected_ids 및 submitted_evaluation: nullable — 정상 실행의 실제 반환안과 최종 채점.
- recovered_protected_ids 및 recovered_evaluation: nullable — 제한 초과·오류 전 보관된 진단용 후보. 정식 성적으로 인정하지 않으며 공식 점수와 분리한다.
- best_protected_ids 및 best_evaluation: nullable — 정확 탐색의 incumbent 전용. upper_bound:nullable. 세 종류를 혼용하거나 정상 반환안을 최고 후보로 바꾸지 않는다.
- optimality_proven:bool, evaluated_combinations:int, evaluation_calls:int, cache_hits:int
- search_seconds, preparation_seconds, final_scoring_seconds, shutdown_seconds
- exact_peak_rss_bytes:nullable (정확 탐색 worker 전체, 평가 포함), algorithm_peak_rss_bytes:nullable (실행기·라이브러리·입력·Evaluator·LP·캐시 포함 전체 RSS, 초기값/평가 메모리 차감 없음), evaluation_peak_rss_bytes:nullable (단일 worker 경로는 null; 평가 RSS 분리 추정 없음), algorithm_memory_limit_bytes:nullable, memory_measurement_method, checkpoint_received_elapsed:nullable
- error_type/error_message/solver_diagnostics: nullable
- pending → running → completed | timeout | failed | not_implemented | memory_limit.
- 미구현 실행은 `not_implemented`로 저장한다. 다른 팀원의 제출 여부와 독립적으로 실행한다.
- timeout 또는 memory_limit은 공식 점수·최적해 대비 차이를 비워 둔다. 보관 후보는 recovered 필드에만 기록하며 optimality_proven=false이고 정상 completed로 바꾸지 않는다. failed의 이전 후보도 진단용이다.
- completed 정확 탐색만 optimality_proven=true. 빠른 방법은 완료하더라도 false.
- 최종 재채점 실패 시 최종 상태 failed이며 탐색 종료 원인은 별도로 보존한다.
- 평가 조합 수는 상한 호출과 구분한다. 단순/가지치기에서 실제 방호 조합 평가 완료 건수를 같은 정의로 집계한다.

### ExperimentManifest / 제출 결과
- 생성/정확 탐색 manifest: schema_version, run_kind(smoke|main|scale_probe), sizes, seeds_by_size, budget_percents, methods, limits, owners.
- 일괄 채점 manifest: 고정 문제은행의 배포 시나리오 목록·case_id, 제출 프로그램·자원 한도·기록 위치, 무작위 사용 여부·사전 고정한 전략 시드 목록·반복 정보를 포함한다. 예산은 파일에서 읽고 덮어쓰지 않는다. 문제 생성 시드와 전략 실행 시드를 분리한다.
- main에는 빈 시드·중복 조건을 허용하지 않는다. scale_probe는 각 실제 그래프의 두 예산 각각 단순 완전탐색이 10800초(3시간) 내 완료되는지 원본 기록으로 남긴다. 다양한 크기의 고정 문제은행에는 이 조건을 충족한 실제 그래프만 채택하고 이를 넘는 대형 도전군은 제외한다. 저장된 모든 문제별 실측 완료 근거가 필요하며 전체 그래프 공간의 최악 수행 시간 보장을 뜻하지 않는다.
- owners는 역할→실명. 초기 실행은 역할 표식 허용, 최종 제출 검수에서는 실명 누락을 표시한다.
- CSV는 각 조건/방법/실행당 한 행이며 실패·미구현도 포함한다. 문제은행은 난수로 미리 생성·저장하고 모든 전략에 동일한 파일을 사용한다. 공식 채점이나 반복 실행 때 시나리오를 새로 생성하지 않는다. 알고리즘 내부에서 난수를 사용하는 전략만 동일 시나리오에서 사전 고정·기록한 전략용 시드 다섯 개로 5회 독립 실행하고, 결정적 전략은 1회 실행한다. 전략용 시드 목록은 문제 생성 시드와 분리하며 본 실험 전에 고정한다. 반복마다 새 상태와 현행 제출 경로의 독립된 자원 한도를 적용한다. 모든 실행의 점수·상태·시간을 보관하고 성공 실행의 연결률·전달량 비율 각각의 중앙값·최솟값·최댓값, 실행 시간, 전체 성공 횟수를 함께 보고한다. 실패는 누락하거나 0점으로 바꾸지 않고, 최고 실행만 대표 성적으로 선택하거나 두 지표를 가중합하지 않는다. 지표별 요약 통계는 실제 단일 방호안의 점수가 아니다. 성공 실행이 없으면 점수 통계는 비워 둔다. nullable 점수는 빈 값과 상태로 표현한다.
- 최적성 확인 조건에서 첫 기준 차이를 보고하며 그 차이가 0인 경우만 둘째 기준 차이를 채운다. 미증명 기준과의 차이를 최적해 격차라고 부르지 않는다.

### 표준 입출력의 자원 기록

- `RunRecord.algorithm_peak_memory_bytes`는 cgroup v2의 `memory.peak`에서 읽은 제출 그룹 전체의 최대 메모리다. 이전 RSS 계측값과 다른 필드다.
- `RunRecord.algorithm_vcpu_limit`는 설정한 vCPU 개수이며, 입력 값이 있으면 1 이상의 정수다. 표준 입출력 경로는 1을 기록한다. 두 필드는 이전 RunRecord에서 생략될 수 있고 null로 읽힌다.

## 구현 기준선 v1 — 공통 운영 계약

아래 정의는 research.md D-001~D-008에 대응하는 공통 직렬화·운영 인터페이스 설계다. 팀원별 계약을 복제하지 않는다. 정책 변경의 실제 검증 상태는 tasks.md 및 검증 기록으로 추적한다.

### 정책과 인증 자료형

- GenerationSettings: version='generation-v1', alpha=1, beta=3, m0=2, rho=1, min_distance=1e-9. 생성의 호출·ID 순서는 D-001.
- AttackSettings: version='attack-v1', count=1, radius=0.15, distance_tolerance=1e-9, grid_denominator=5, coordinate_digits=9, candidate_sources=('nodes','midpoints','grid'). 다른 값은 main에서 거부한다.
- EvaluationPolicy: version='evaluation-v2', rounding='ROUND_HALF_EVEN', decimal_precision=50, delivery_digits=6, residual_relative_tolerance=1e-7, primal_tolerance=1e-9, dual_tolerance=1e-9, ipm_tolerance=1e-10, certificate_denominator_limit=1_000_000_000, max_solver_attempts=2, threads=1. 인증 모드는 유리수 primal-dual 구간 우선 및 제한된 HiGHS 잔차 fallback이다. 정책 필드는 case_id 입력이며 불변이다. 이전 evaluation-v1 bundle은 정책 혼합 방지를 위해 의도적으로 거부하고 v2 참조를 재생성한다. schema/manifest/CLI v1과 평가 정책 v2는 별도 버전이다.
- SolverDiagnostics: success, status, message, attempts, raw_delivered_mbps, maximum_residual, certified_lower, certified_upper, certificate_status, elapsed_seconds. 유리수는 {'numerator':int,'denominator':positive int}로 저장하며 NaN/Infinity는 금지한다. 인증 성공은 인증 구간의 동일 HALF_EVEN 반올림을 확인한다. 인증 실패/구간 불일치 시 HiGHS success·status=0 및 primal 제약·dual stationarity/부호/절대 gap의 유한 최대 잔차 <=1e-7이면 raw_delivered_mbps/총 요청량을 6자리 HALF_EVEN으로 반올림한다. fallback은 certified_lower=certified_upper=None(JSON null), certificate_status='highs_residual_fallback'이며 유리수 증명이나 가지치기용 인증 상한이 아니다. fallback 조건까지 실패하면 재시도 후 EvaluationError이며 임의 clip/epsilon은 금지한다.
- 이전 클래스 실행기의 ExecutionContext는 `algorithm_seed`, `repeat_index`, `repeat_count`를 사용한다. 현행 실행은 stdin의 전략 시드에 결정적 실행의 -1 또는 실행별 고정 시드를 전달한다. RunRecord에는 결정적 시드를 null로 저장한다.
- RunRecord 추가: case_id, algorithm_seed, repeat_index, repeat_count, run_kind, policy_version, submission_sha256, t0_monotonic_ns, final_received_monotonic_ns:nullable, deadline_monotonic_ns, memory_sample_interval_ms=10, observed_max_sample_gap_ms, resource_monitor_supported:bool, events:list[사건], launch_status='started'|'not_started'. 모니터 실패 reason은 resource_monitor_unavailable, 인증 실패 reason은 certificate_failed/numeric_ambiguity. failed/timeout/memory_limit/not_implemented의 공식 점수와 격차는 null이다.
- 이전 클래스 실행기의 제출 로딩 실패는 `submission_load_error`로 기록했다. 현행 CLI의 제출 파일 읽기 실패는 배치 입력 오류다. 제출 실행의 시작 이후 오류는 해당 행의 실패 원인으로 기록한다.
- RunRecord 상태는 `pending`, `running`, `completed`, `timeout`, `memory_limit`, `failed`, `not_implemented`로 구분한다. 표준 입출력 취소는 `failed`와 `termination_reason=cancelled`를 기록한다. 웹 제출 자체의 상태는 별도다.

### 정규 JSON과 식별자

- UTF-8, json.dumps(sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False). 배열 순서는 유지하고 ID는 소문자 64자리 SHA-256 hex. bool은 모든 int 필드에서 금지한다. 객체의 중복 키와 알 수 없는 필드는 거부한다. `ScenarioBundle.optimal_reference`와 이전 기록에서 생략 가능한 두 RunRecord 자원 필드를 제외한 필수 필드 누락은 오류다.
- scenario_id 입력은 schema_version, generation, seed, nodes, edges, demands만이다. 환경·시간·공격/평가 정책·예산·참조는 제외한다. case_id 입력은 schema_version, scenario_id, attack_settings, evaluation_policy, budget_percent, budget이다. scenario_id는 로딩한 실제 데이터로 먼저 재계산한다.
- 해시 대상 원시 float는 JSON 직렬화 표현을 사용하며 좌표를 반올림해 넣지 않는다. 이 프로파일은 Python 생성/검증 경로용이며 범용 언어간 canonical JSON을 주장하지 않는다.
- 중간 파일: {'artifact_kind':'scenario_input','schema_version':1,'scenario':Scenario}. 배포 파일: {'artifact_kind':'scenario_bundle','schema_version':1,'scenario':Scenario,'budget_percent':20|40,'budget':int,'case_id':str,'optimal_reference':OptimalReference}. 참조 삭제 사본은 optimal_reference 키만 생략한다. 그 외 키는 동일해야 한다.
- 저장은 같은 디렉터리 임시 파일에 write/flush/fsync 후 os.replace. 기본은 기존 파일 덮어쓰기 거부다. JSONL 각 행은 완결 JSON이며 읽기 시 마지막 불완전 행은 별도 복구 진단으로 남기고 성공으로 파싱하지 않는다.

### Manifest v1

공통 필수 키: schema_version=1, run_kind=smoke|main|scale_probe, owners:역할→이름, ready:bool(생략 시 true, false이면 실행 거부). 경로는 manifest 부모 디렉터리 기준으로 해석하고 내부 처리에서는 절대 경로로 정규화한다. main에는 소유자 표식/빈 이름·미준비 상태를 허용하지 않는다. smoke의 seed=0과 역할 표식은 본 실험 선정이 아니다.

생성 manifest: kind='preparation', sizes:list[int>=3], size_groups:문자열 n→small|medium_large|probe (sizes와 정확히 같은 키; small은 6 또는 8, probe는 scale_probe 전용), seeds_by_size:문자열 n→중복 없는 음이 아닌 int 목록, budget_percents=[20,40], exact_methods=['exhaustive','branch_bound'] — 소형 검수용, limits:{small_exact_seconds:600,large_exact_seconds:10800}, output_dir, owners. smoke는 sizes=[6], size_groups={'6':'small'}, seeds_by_size={'6':[0]}; main의 소형은 n=6/8, 중·대형은 규모 확인 근거가 있는 서로 다른 세 크기와 각 한 시드. 규모 확인 후보/실행 이력과 최종 선정값은 구분한다.

채점 manifest: `kind='grading'`, `bank=[{path,case_id}, …]`, `submission={method_id,file,uses_randomness,algorithm_seeds,owner,strategy_name,strategy_version}`, `limits={algorithm_seconds:300,algorithm_memory_bytes:6000000000}`, `resource_policy={sample_interval_ms:10}`, `output_dir`, `owners`. 단일 Python 파일과 고유한 사례 ID를 사용한다. 무작위는 서로 다른 음이 아닌 정수 시드 5개, 결정적은 빈 시드 목록이다. main은 원본 참조가 필요하고 smoke에서 참조 삭제 사본을 채점하면 격차는 null이다. `resource_policy.sample_interval_ms`는 manifest v1 호환 필드이며 현재 제출의 최대 메모리는 cgroup에서 읽는다. `class_name`이 있는 이전 manifest는 읽을 수 있지만 `grade` 실행에는 그 필드를 제거하고 메모리를 6,000,000,000바이트로 변경해야 한다.

검증 manifest 예제 파일은 T004에서 configs/smoke.json(preparation), T049에서 configs/smoke-grading.json(grading)을 생성한다. 본 실험 configs/experiment.json은 사용자 입력 전에는 생성하지 않거나 ready=false로 두고 main을 거부한다. 실제 실험값을 채우지 않고 문서상으로만 인터페이스를 확정한다.

### CLI v1

진입점은 `python -m protection.cli`와 `protection`이다. `--help`는 산출물을 생성하거나 제출 파일을 import하지 않는다.

| 명령 | 입력 | 출력/거부 조건 |
|---|---|---|
| generate --manifest PATH | preparation manifest | output_dir/inputs/n{n}-seed{seed}.json, 준비 환경; 최적 참조 없는 중간 입력 |
| exact --input PATH --budget-percent 20\|40 --method exhaustive\|branch_bound --run-kind smoke\|main\|scale_probe --output PATH | 중간 입력, 예산, 방법 | 단일 RunRecord JSON. main/scale_probe는 --manifest PATH를 필수로 받아 case가 manifest에 있는지 확인하고 소형 main은 600초, scale_probe/중대형 main은 10800초; --limit-seconds는 smoke에서만 허용 |
| bundle --input PATH --exact-record PATH --output PATH | 입력과 완료 단순 완전탐색 기록 | 원본 bundle; case_id·한도·환경·해/점수 재채점 확인, 미완료/다른 조건은 거부 |
| validate --bundle PATH [--require-reference] | 원본 또는 참조 삭제 사본 | 구조·해시·예산·있다면 참조 검증 결과 JSON stdout; 원본 요구 시 참조 없으면 오류 |
| input --bundle PATH | 원본 또는 참조 삭제 번들 | 결정적 시드 표식 -1을 포함한 stdin 텍스트 |
| grade --manifest PATH | grading manifest의 단일 제출·전체 bank | output_dir/runs.jsonl, batch.json, environment.json. 생성기/정확 탐색을 호출하지 않음 |
| report --records PATH --bank-manifest PATH --output-dir PATH | 실행 기록과 bank 목록 | runs.csv, summary.csv, report.json; 조건/예산/정책이 다른 행 혼합 금지 |

종료 코드는 명령 성공 0, 기록된 실패·미구현·초과·미완료가 있는 채점/탐색 1, CLI·manifest·입력 오류 2다. 환경 준비 실패는 실행별 `failed/environment_blocked`로 기록한다. 종료 후 공식 채점은 실행 한도 밖에서 별도 측정한다.

### 공개 문제은행 인덱스

`scenarios/problem-bank/bank.json`의 `bank` 항목은 인덱스 기준 상대 `path`와 `case_id`로 공개 번들을 가리킨다. 같은 그래프의 두 예산을 검증한 뒤 인덱스에 함께 추가한다. `records/`에는 각 예산의 RunRecord, `progress.json`에는 활성 조건과 실행 상태, `manifest.json`에는 고정 입력과 실행 한도를 보존한다. 재개 시 고정 manifest와 기존 기록을 다시 확인한다. 이전 탐색의 미공개 입력과 별도 실행 기록은 `history/`에 보존한다.

### 집계와 격차

- runs.csv: RunRecord의 식별/시드/상태/시간/RSS·공식 두 점수·진단 후보·오류. 복잡한 진단은 JSONL 참조. 실패 점수는 빈 셀이다.
- summary.csv: case_id/method_id/submission_sha256/환경/정책으로 묶고 success_count, total_count, 각 성공 지표의 median/min/max, 모든 실행의 시간 및 상태별 횟수를 보존한다. 실제 반환 방호안 대신 이 통계 벡터를 방호안 점수로 취급하지 않는다.
- gap_connected_pairs=reference.connected_pairs-submitted.connected_pairs. 이것이 0일 때만 gap_delivery_units=reference.delivery_units-submitted.delivery_units. 최적 참조보다 좋은 결과(음수 격차)는 조용히 0으로 보정하지 않고 reference_mismatch로 검수 실패 처리한다. 참조 없음/미증명/실패 실행의 gap은 null이다. 웹 HTML의 부호 있는 전달률 차이(%p)는 화면에서 별도로 계산한다.

