"""4번 설명용 완전탐색: 공통 평가기로 모든 유효한 방호안을 비교한다.

표준 입력은 팀 전략과 같은 문제 형식이다. 출력은 최적 방호안이다.
작은 사례 시연용이며, 공식 장시간 인증의 실행 기록을 대신하지 않는다.
"""
from itertools import combinations
import sys

from protection.attacks import prepare_attacks
from protection.evaluation import Evaluator
from protection.models import Demand, Edge, Node, Scenario, feasible_protection_count


def read_problem():
    n, m, demand_count, attack_count = map(int, sys.stdin.readline().split())
    budget = int(sys.stdin.readline())
    nodes = []
    for node_id in range(n):
        x, y = map(float, sys.stdin.readline().split())
        nodes.append(Node(node_id, x, y))
    edges = []
    for edge_id in range(m):
        start, end, capacity, cost = map(int, sys.stdin.readline().split())
        edges.append(Edge(edge_id, start, end, capacity, cost))
    demands = []
    for demand_id in range(demand_count):
        start, end, amount = map(int, sys.stdin.readline().split())
        demands.append(Demand(demand_id, start, end, amount))
    attacks = []
    for attack_id in range(attack_count):
        fields = sys.stdin.readline().split()
        x, y, count = float(fields[0]), float(fields[1]), int(fields[2])
        damaged = tuple(map(int, fields[3:]))
        if len(damaged) != count:
            raise ValueError('공격의 선 개수가 맞지 않습니다.')
        attacks.append((attack_id, x, y, damaged))
    # 문제는 이미 생성돼 있으므로 이 내부 기본값은 생성에 사용되지 않는다.
    scenario = Scenario(tuple(nodes), tuple(edges), tuple(demands), seed=0)
    prepared = prepare_attacks(scenario)
    expected = [(a.id, a.x, a.y, a.damaged_edge_ids) for a in prepared.candidates]
    if attacks != expected:
        raise ValueError('입력의 공격 목록이 공통 생성 규칙과 다릅니다.')
    return scenario, prepared, budget


def solve(scenario, prepared, budget):
    # 제출 채점과 같은 Evaluator를 사용한다. 참조용은 유리수 인증을 요구한다.
    judge = Evaluator(scenario, prepared, require_certificate=True)
    best = None
    checked = 0
    edge_ids = range(len(scenario.edges))
    for count in range(len(scenario.edges) + 1):
        for choice in combinations(edge_ids, count):
            if sum(scenario.edges[i].cost for i in choice) > budget:
                continue
            result = judge.evaluate(list(choice), budget)
            checked += 1
            if best is None or result.defender_key < best.defender_key:
                best = result
    if checked != feasible_protection_count(scenario, budget) or judge.fallback_solves:
        raise RuntimeError('모든 방호안의 인증을 완료하지 못했습니다.')
    return best.protected_ids


if __name__ == '__main__':
    answer = solve(*read_problem())
    print(len(answer), *answer)
