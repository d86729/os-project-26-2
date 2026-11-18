"""팀원 1 전용 전략 파일. 인계 설명은 이 파일에 내장하며 전략은 자유롭게 선택한다."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protection.models import Scenario
    from protection.context import ExecutionContext


class Member1Protector:
    """팀원 1 소유. 담당자 실명·실제 전략명·전략 버전은 제출 전에 기입한다.

    처음 읽는 팀원을 위한 요약:
        해야 할 일은 solve 안에서 '어떤 간선을 방호할지' 정하고 번호 목록을
        return 하는 것이다. 파일 읽기, 공격 계산, 공식 채점, 상태 기록은 공통 코드가 한다.
        print([1])은 반환이 아니다. return [1]처럼 Python list를 반환한다.
        scenario는 dict가 아닌 객체이므로 scenario.edges[1].cost처럼 접근한다.

    작은 입출력 예시 (설명용 가상 입력이며 실험 결과가 아님):
        scenario.nodes: 기지 번호 0, 1, 2
        scenario.edges: 아래 세 Edge 객체의 tuple
            id=0: 기지 0--1, capacity_mbps=10, cost=3
            id=1: 기지 0--2, capacity_mbps=10, cost=4
            id=2: 기지 1--2, capacity_mbps=10, cost=5
        scenario.demands: 기지 0 -> 2로 5 Mbps 요청
        budget=4 (비율 40이 아니라 이미 계산된 비용 상한 4)
        context.limit_seconds=300, context.algorithm_seed=None
        유효 출력: [1] -> 1번 간선만 방호, 비용 4. []나 [0]도 유효하다.
        잘못된 출력: [0, 1]은 비용 7로 예산 초과, [1, 1]은 중복,
            [99]는 없는 번호, (1,)은 tuple, {'answer': [1]}은 dict라서 거부된다.
        방호하지 않은 선이 모두 삭제되는 것은 아니다. 공격 피해는 공통 평가기가 계산한다.
        이 예시는 입력 일부를 풀어 쓴 것으로 Scenario 생성 코드나 최적해가 아니다.

    가장 간단한 API 사용 예시 (아래는 설명이며 실제 solve 구현이 아님):
        def solve(self, scenario, budget, context):
            candidate = []  # API 확인용: 아무 선도 방호하지 않는 유효 후보
            result = context.evaluate(candidate)
            assert result.cost == 0
            return candidate  # result 객체가 아니라 간선 번호 목록을 반환

        위 예시는 좋은 전략이 아니며 제출 알고리즘을 대신하지 않는다.
        실제 구현에서는 본인이 탐색한 후보를 반환한다. evaluate는 선택 사항이며
        호출 시간도 300초에 포함된다. context.remaining_seconds()로 남은 시간을
        확인하고 결과 전달 여유를 두어 반환한다. 남은 시간 확인만으로 다음 평가의
        완료가 보장되지는 않는다. 미구현 상태를 위의 빈 해로 바꾸어 제출하지 않는다.

    실행 결과 예시 (실측 로그가 아닌 RunRecord 일부 필드의 설명용 예):
        아래 상태는 solve가 반환하는 것이 아니라 공통 실행기가 기록한다.
        성공: return [1]이 기한 내 수신되고 최종 채점도 성공한 경우
            {'status': 'completed', 'submitted_protected_ids': [1]}
            submitted_evaluation에는 실제 Evaluation이 들어간다. 점수는 여기서 꾸며 넣지 않는다.
        시간초과: 반환 전에 제한시간을 넘긴 경우
            {'status': 'timeout', 'submitted_evaluation': None}
        메모리 초과: 전체 워커 RSS가 4,000,000,000 bytes를 넘긴 경우
            {'status': 'memory_limit', 'submitted_evaluation': None}
        런타임 오류: solve에서 raise RuntimeError('example failure')가 전파된 경우
            {'status': 'failed', 'error_type': 'RuntimeError',
             'error_message': 'example failure', 'submitted_evaluation': None}
        위 목록은 전체 저장 JSON이 아니다. Python None은 JSON에서 null이 된다.
        실패는 0점이 아니라 공식 점수 없음이다. 시간/메모리 초과는 정상 성공으로
        바뀌지 않는다. 강제 종료 시 워커 안의 중간 후보도 복구되지 않을 수 있다.
        현재 파일 그대로 실행하면 not_implemented이며, 위 성공 예시와 다르다.

    책임 경계:
        공통 실행기는 이 클래스를 무인자로 생성한 뒤 solve를 호출한다.
        이 파일의 알고리즘·시험·전략 설명은 팀원 책임이다. 제출물은 이 파일 하나다.
        채점기가 모든 저장 시나리오를 하나씩 로딩·실행·검사·채점·기록한다.
        팀원이 서버·일괄 실행기·시나리오별 결과 파일을 제출할 필요는 없다.
        김대건은 공통 생성·평가·정확 탐색·실행기·계약 검사를 제공한다.
        어떤 전략을 사용할지는 자유이며 특정 중심성·탐욕·교환을 요구하지 않는다.
        다른 팀원 구현에 대한 공통 선행 의존성이나 대체 전략은 없다.
        입력과 공통 로직, 다른 팀원의 파일을 수정하지 않는다.

    배포 파일과 신뢰 가정:
        시나리오 파일은 맵·가중치·수요·예산·완전탐색 최적 참조를 포함한다.
        팀원은 최적 방호안 및 참조 결과를 보거나 활용하지 않거나 해당 부분을 삭제한다.
        공통 로더는 아래 입력에서 최적 참조를 제외한다. 이는 보안 차단이 아니다.
        예산은 파일에 고정되어 있으며 삭제 사본에서도 같은 입력으로 실행할 수 있다.
        개발·시험은 자유지만 공식 실행에 시나리오별 사전 방호안·탐색 결과·평가
        캐시를 재사용하거나 답을 하드코딩하지 않는다. 조건마다 새 상태로 실행한다.
        이는 신뢰 약속이며 부정행위 탐지나 원본 파일 접근 차단을 요구하지 않는다.

    입력 계약:
        scenario: 불변 Scenario. nodes: tuple[Node,...], edges: tuple[Edge,...],
            demands: tuple[Demand,...], seed:int, scenario_id:str.
            attack_settings와 evaluation_policy에 공격·평가 조건을 공개한다.
            한 곳 공격, 반경 0.15, 기지·선 중점·간격 0.2 격자 후보, 거리 허용오차
            1e-9, 후보 좌표 9자리·전달률 6자리 반올림을 사용한다. 후보는 Decimal(str(value))의 HALF_EVEN으로 9자리 대표 좌표를
            만들고 점수는 evaluation-v2의 6자리 HALF_EVEN을 사용한다.
            정책 혼합 방지를 위해 이전 evaluation-v1 bundle은 거부한다.
            Node(id:int,x:float,y:float): 좌표는 [0,1).
            Edge(id:int,u:int,v:int,capacity_mbps:int,cost:int): u<v,
            두 방향 각각 독립적으로 capacity_mbps의 용량을 가진다.
            Demand(id:int,source:int,target:int,amount_mbps:int): 방향별 요청.
            각 id는 0부터 연속이며 tuple 인덱스와 같다. edges는 (u,v)순이다.
            중첩 자료형은 frozen 객체와 tuple이며 수정하지 않는다.
        budget: bool이 아닌 음이 아닌 int. 이미 계산된 방호 비용 상한이다.
        context: 전략 중립적 ExecutionContext.
            limit_seconds:float, algorithm_seed:int|None, repeat_index:int,
            repeat_count:int (읽기 전용). repeat_index는 0부터이며 결정적은
            (algorithm_seed=None, repeat_index=0, repeat_count=1), 무작위는
            고정 목록의 시드와 (repeat_index=0..4, repeat_count=5)를 받는다.
            remaining_seconds()->float,
            elapsed_seconds()->float, evaluate(edge_ids:list[int])->Evaluation.
            evaluate는 필요할 때 호출한다. 사용 의무나 횟수 요구는 없다.
            자체 단계 배분·전략 선택·다른 방법 호출을 위한 전용 API는 없다.
            evaluate는 같은 worker에서 Evaluator를 직접 호출하며 평가별 JSON IPC는 없다.
            LP 유리수 primal/dual 인증을 우선하되 인증 실패 시 HiGHS success/status=0,
            primal 및 dual stationarity·부호·절대 gap의 유한 최대 잔차 <=1e-7이면
            raw 전달량/총 요청량의 6자리 HALF_EVEN fallback을 허용한다.
            fallback 진단은 certified_lower/upper=None,
            certificate_status=highs_residual_fallback이며 유리수 증명이 아니다.
            fallback 조건도 충족하지 못한 평가 실패는 EvaluationError다.
            정상 Evaluation은 protected_ids:tuple[int,...], cost:int,
            connected_pairs:int, connected_ratio:float, delivered_mbps:float,
            delivery_ratio:float, delivery_units:int, worst_attack:tuple[float,float].
            delivery_units는 6자리 반올림 비율의 백만분율 정수이다.
            공통 비교는 connected_pairs, delivery_units가 큰 순,
            cost가 작은 순, protected_ids 사전식 작은 순이다.
            공격은 두 점수를 순서대로 최소화하며 최종 동점은 좌표순이다.
            이는 공통 평가 규칙이며 전략 내부의 탐색 순서를 강제하지 않는다.

    출력 계약:
        solve는 마감 전에 list[int]를 반환한다. 오름차순, 중복 없음,
        존재하는 선 번호만 포함, 총비용<=budget. bool 원소는 금지한다.
        []도 실제 선택한 유효 방호안이다. 미구현을 []로 대신하면 안 된다.
        최종 반환 전 evaluate를 호출할 의무는 없다. 공통 실행기가 최종 채점한다.
        정상 반환안을 평가 중 최고 후보로 자동 교체하지 않는다.
        평가 결과나 상태를 반환 목록에 섞지 않는다.

    시간·메모리 계약:
        조건별 300초에 자신의 사전 계산과 평가 호출 대기/계산 시간을 포함한다.
        공통 생성·피해 목록 준비·종료 후 최종 채점은 별도로 측정한다.
        알고리즘 전체 프로세스 RSS 상한은 십진 4GB=4,000,000,000 bytes다.
        Python·라이브러리·입력 사본·Evaluator·LP·평가 캐시를 모두 포함한다.
        부모가 worker 하나의 300초와 전체 RSS를 감시하며 초기값/평가 메모리를 차감하지 않는다.
        기본 안전 제어/결과 채널과 반환 후 공식 재채점은 유지한다. 정확 탐색에는
        이 한도를 적용하지 않는다. Linux /proc의 VmRSS/VmHWM를 목표 10ms 간격과 최종 수신 시
        관측하고 실제 최대 표본 간격을 남긴다. 관측값이 한도를 초과하면 종료한다.
        표본 관측은 연속 하드 제한이 아니며 계측 미지원은 공식 실행을 막는다.
        U-001: 공통 환경·입력 준비 후 제출 파일 import 직전부터 최종 반환값이
        채점기에 도착할 때까지 측정한다. import·클래스 생성·입력 전달·자체
        전처리·평가 대기·결과 전달을 포함하고 반환 후 공식 채점은 제외한다.
        U-002: 시간/메모리 초과 후보는 진단 전용이다. 공식 점수는 비워 두며
        초과 상태를 유지하고 정상 완료나 0점으로 바꾸지 않는다.
        U-003: 문제은행은 사전 생성·저장하며 공식 실행 때 재생성하지 않는다.
        내부 난수를 사용하는 전략만 같은 문제에서 고정한 전략 시드 5개로 5회,
        결정적 전략은 1회 실행한다. 매번 새 상태·빈 캐시·300초·4GB를 적용한다.
        문제 생성 시드와 전략 시드는 별개이며 무작위 전략을 강제하지 않는다.
        모든 실행을 보관하고 성공 지표별 중앙값·최솟값·최댓값, 실행 시간과
        전체 성공 횟수를 보고한다. 최고 실행만 선택하거나 실패를 0점 처리하지
        않는다. 요약 통계는 실제 단일 방호안의 점수가 아니다.
        제한 우회를 위한 별도 프로세스·외부 계산 서비스는 허용하지 않는다.
        평가 완료 후보는 공통 실행기가 자동 보관한다. 시간/메모리 한도 초과 시
        마감 전 보관한 유효 후보만 진단·복구 대상으로 삼고 초과 상태를 명시한다.
        이 보존이 정식 성적 인정이나 정상 완료로의 전환을 뜻하지 않는다.
        반환도 보관 후보도 없으면 유효 결과 없음이며 점수를 만들어내지 않는다.

    오류 계약:
        NotImplementedError: 담당자 미구현. 현재 골격은 이것만 발생시킨다.
        InvalidProtectionError: 잘못된 후보 입력. 구현 오류로 전파한다.
        EvaluationError: 공통 평가 실패. 0점으로 치환하지 말고 전파한다.
        DeadlineExceeded: 전체 시간 종료. 완료 후보가 있으면 반환할 수 있으나
        마감 이후 반환은 정상 완료가 아니다. 강제 종료 시 후보 복구는 진단 전용이다.
        위 공통 예외는 protection.errors에서 필요한 것만 import한다.
        실행 API는 protection.runner.run_submission(bundle, file, class_name)이다.
        저장 문제은행은 grade_manifest(manifest)로 직렬 실행한다. 반환 RunRecord의
        submitted_*는 실제 반환안/공식 점수, recovered_*는 진단 후보이며 별개다.
        메모리 한도 초과는 감독자가 memory_limit 상태로 기록할 수 있다.

    검수·제출:
        유효/잘못된 번호·중복·예산·빈 해·입력 불변성·미구현·평가 실패·시간 및
        메모리 초과를 시험한다. 특정 전략의 선택 경로와 성능 개선을 요구하지 않는다.
        내부 무작위 사용 시 자기 RNG를 사용하고 seed 및 설정을 실행 메타데이터로
        공개한다. 고정 전략 시드는 context.algorithm_seed로 받으며
        scenario.seed(문제 생성 시드)를 알고리즘 시드로 대신 사용하지 않는다.
        공통 계층은 팀원 RNG나 전역 RNG를 대신 초기화하지 않는다.
        실행별 RNG는 solve 진입 후 context.algorithm_seed로 초기화한다.
        import/생성자에서는 실행별 무작위 선택이나 시나리오 의존 계산을 하지 않는다.
        입력 시나리오의 RNG/전역 상태를 변경하지 않는다.
        실제 방법·설정·버전과 실행 결과를 설명할 책임은 팀원에게 있다.
        시험 대역 결과를 실제 연구 성능으로 제출하지 않는다.
    """

    def solve(self, scenario: Scenario, budget: int, context: ExecutionContext) -> list[int]:
        """불변 시나리오·예산·공통 문맥을 받아 정렬된 방호 선 번호를 반환한다.

        상세 입출력·자원·예외·검수 계약은 이 클래스 docstring에 있다.
        """
        # TODO(팀원 1): 자유롭게 선택한 전략을 이 본문에 직접 구현·검증한다.
        raise NotImplementedError("Member1Protector: 팀원 1의 구현이 필요합니다.")
