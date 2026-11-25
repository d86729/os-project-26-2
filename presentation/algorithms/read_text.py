"""표준 텍스트 문제를 공통 평가기가 사용하는 자료형으로 읽는다."""
from protection.attacks import prepare_attacks
from protection.models import Demand, Edge, Node, Scenario


def read_problem(stream):
    n, m, d, a = map(int, stream.readline().split())
    budget = int(stream.readline())
    nodes = []
    for i in range(n):
        x, y = map(float, stream.readline().split())
        nodes.append(Node(i, x, y))
    edges = []
    for i in range(m):
        u, v, capacity, cost = map(int, stream.readline().split())
        edges.append(Edge(i, u, v, capacity, cost))
    demands = []
    for i in range(d):
        source, target, amount = map(int, stream.readline().split())
        demands.append(Demand(i, source, target, amount))
    attacks = []
    for _ in range(a):
        fields = stream.readline().split()
        x, y, count = float(fields[0]), float(fields[1]), int(fields[2])
        damaged = tuple(map(int, fields[3:]))
        if len(damaged) != count:
            raise ValueError('공격 대상 선의 개수가 일치하지 않습니다.')
        attacks.append((x, y, damaged))
    # 생성은 이미 끝났으므로 seed=0은 내부 자료형을 위한 기본값입니다.
    scenario = Scenario(tuple(nodes), tuple(edges), tuple(demands), seed=0)
    prepared = prepare_attacks(scenario)
    expected = [(a.x, a.y, a.damaged_edge_ids) for a in prepared.candidates]
    if attacks != expected:
        raise ValueError('입력의 공격 후보가 공통 공격 규칙과 다릅니다.')
    return scenario, budget
