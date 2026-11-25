"""진명호의 전수 검사에 표준 입출력을 연결한 작은 문제 시연용 코드다.

공통 채점 모듈이 필요하며, 프로그램이 출력하는 것은 방호할 선 번호다.
이 실행은 모든 후보를 조사하지만 별도의 엄밀한 최적해 인증은 아니다.
"""
from itertools import combinations
import sys

from protection.attacks import prepare_attacks
from protection.evaluation import Evaluator
from protection.models import Demand, Edge, Node, Scenario


def read_problem():
    """텍스트 입력에서 그래프와 예산을 읽고 공격 후보를 확인한다."""
    n, m, demand_count, attack_count = map(int, sys.stdin.readline().split())
    budget_fields = sys.stdin.readline().split()
    budget = int(budget_fields[0])
    legacy = len(budget_fields) > 1  # 일부 입력에는 예산 뒤에 부가 값이 있습니다.
    nodes = []
    for node_id in range(n):
        x, y = map(float, sys.stdin.readline().split())
        nodes.append(Node(node_id, x, y))
    edges = []
    for edge_id in range(m):
        start, end, capacity, cost = map(int, sys.stdin.readline().split()[-4:])
        edges.append(Edge(edge_id, start, end, capacity, cost))
    demands = []
    for demand_id in range(demand_count):
        start, end, amount = map(int, sys.stdin.readline().split()[-3:])
        demands.append(Demand(demand_id, start, end, amount))
    attacks = []
    for attack_id in range(attack_count):
        fields = sys.stdin.readline().split()
        if legacy:
            fields = fields[1:]  # 입력에 포함된 공격 번호를 제외합니다.
        x, y, count = float(fields[0]), float(fields[1]), int(fields[2])
        damaged = tuple(map(int, fields[3:]))
        if len(damaged) != count:
            raise ValueError('공격의 선 개수가 맞지 않습니다.')
        attacks.append((attack_id, x, y, damaged))

    # 시나리오는 이미 입력으로 주어졌으며, 이 기본값으로 새 문제를 만들지 않는다.
    scenario = Scenario(tuple(nodes), tuple(edges), tuple(demands), seed=0)
    prepared = prepare_attacks(scenario)
    expected = [(a.id, a.x, a.y, a.damaged_edge_ids) for a in prepared.candidates]
    if attacks != expected:
        raise ValueError('입력의 공격 목록이 공통 생성 규칙과 다릅니다.')
    return scenario, budget


def run_exhaustive(scenario, budget):
    m = len(scenario.edges)  # 전체 통신선 개수
    # 공통 평가기를 사용한다.
    evaluator = Evaluator(scenario)
    best_eval = None  # 최고 점수 기록
    best_edges = []  # 최고 점수를 낸 방호 선 목록
    checked_count = 0  # 예산을 만족해서 실제 계산한 조합 수

    # 통신선을 0개 고르는 경우부터 m개 모두 고르는 경우까지 전부 확인
    for k in range(m + 1):
        for comb in combinations(range(m), k):
            # 선택한 선들의 비용 합계가 예산을 넘으면 건너뜀
            cost = sum(scenario.edges[e].cost for e in comb)
            if cost > budget:
                continue
            # 공통 평가기로 최악 공격 후 점수 계산
            result = evaluator.evaluate(list(comb), budget)
            checked_count += 1
            # 기존 최고 점수보다 더 좋으면 정답 교체
            if best_eval is None or result.defender_key < best_eval.defender_key:
                best_eval = result
                best_edges = list(comb)
    return best_edges


if __name__ == '__main__':
    answer = run_exhaustive(*read_problem())
    print(len(answer), *answer)
