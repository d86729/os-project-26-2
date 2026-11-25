"""연결유지 교환: 탐욕적으로 만든 방호안을 최대 세 번 수정한다.
서로 다른 피해 집합별 연결 쌍 수를 작은 순서로 정렬하고, 앞의 값부터 최대화한다.
그 목록이 같을 때만 남은 선들의 용량 합, 더 낮은 보호 비용, 선 번호 순서를 본다.
초기 방호안에서 한 선을 추가하거나 보호하던 한 선을 다른 선으로 교환한다.
예산 안에서 가장 좋은 수정을 선택하며, 개선이 없거나 세 번 수정하면 끝낸다.
용량 합은 실제 전달량이 아니므로 이 판단이 좋아져도 전달률은 나빠질 수 있다.
Vaessens·Aarts·Lenstra (1998)의 반복 개선 개념을 참고했다.
논문 정보: https://doi.org/10.1016/S0305-0548(97)00093-2
원문 PDF: https://homes.di.unimi.it/cordone/courses/2026-ae/Lez13-Materiali/LocalSearchTemplate.pdf
최적해나 근사 비율을 보장하지 않는다. 에이전트 3 작성.
"""
import sys
IMPROVEMENT_ROUNDS = 3
def solve(text):
    rows = iter(text.splitlines())
    n, m, d, a = map(int, next(rows).split())
    budget = int(next(rows).split()[0])
    for _ in range(n):
        next(rows)  # 기지 좌표를 읽는다. 공격으로 끊기는 선의 목록은 입력에 이미 포함되어 있다.
    edges = [tuple(map(int, next(rows).split())) for _ in range(m)]
    for _ in range(d):
        next(rows)  # 이 간단한 판단 기준에서는 수요량을 사용하지 않는다.
    damage = set()
    for _ in range(a):
        tokens = next(rows).split()
        damage.add(sum(1 << int(e) for e in tokens[4:]))
    damage = sorted(damage)
    full = (1 << m) - 1
    costs = [edge[4] for edge in edges]
    graph_cache = {}
    score_cache = {}
    def graph_value(mask):
        if mask in graph_cache:
            return graph_cache[mask]
        parent = list(range(n))
        size = [1] * n
        pairs = capacity = 0
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for eid, u, v, cap, _ in edges:
            if mask & (1 << eid):
                capacity += cap
                u, v = find(u), find(v)
                if u != v:
                    if size[u] < size[v]:
                        u, v = v, u
                    pairs += size[u] * size[v]
                    parent[v] = u
                    size[u] += size[v]
        result = pairs, capacity
        graph_cache[mask] = result
        return result
    def ids(mask):
        return tuple(e for e in range(m) if mask & (1 << e))
    def score(mask):
        if mask not in score_cache:
            values = [graph_value(full & ~(hit & ~mask)) for hit in damage]
            chosen = ids(mask)
            score_cache[mask] = (
                tuple(sorted(pairs for pairs, _ in values)),
                sum(cap for _, cap in values),
                -sum(costs[e] for e in chosen),
            )
        return score_cache[mask]
    def better(left, right):
        return score(left) > score(right) or (score(left) == score(right) and ids(left) < ids(right))
    selected = used = 0
    # 매 단계에서 남은 예산으로 추가할 수 있는 모든 선을 비교한다.
    while True:
        best = selected
        for e in range(m):
            if not selected & (1 << e) and used + costs[e] <= budget:
                candidate = selected | (1 << e)
                if better(candidate, best):
                    best = candidate
        if best == selected:
            break
        selected = best
        used = sum(costs[e] for e in ids(selected))
    for _ in range(IMPROVEMENT_ROUNDS):
        best = selected
        for outgoing in (-1, *ids(selected)):
            reduced = selected if outgoing == -1 else selected & ~(1 << outgoing)
            reduced_cost = used if outgoing == -1 else used - costs[outgoing]
            for incoming in range(m):
                if reduced & (1 << incoming) or reduced_cost + costs[incoming] > budget:
                    continue
                candidate = reduced | (1 << incoming)
                if better(candidate, best):
                    best = candidate
        if best == selected:
            break
        selected = best
        used = sum(costs[e] for e in ids(selected))
    return ids(selected)

def standard_input(text):
    # 간결한 입력에 번호가 없으므로 solve가 사용하는 행 번호를 붙입니다.
    lines = text.splitlines()
    n, m, d, a = map(int, lines[0].split())
    if len(lines[1].split()) == 1:
        first_edge = 2 + n
        for i in range(m):
            lines[first_edge + i] = f'{i} ' + lines[first_edge + i]
        first_attack = first_edge + m + d
        for i in range(a):
            lines[first_attack + i] = f'{i} ' + lines[first_attack + i]
    return '\n'.join(lines)


if __name__ == '__main__':
    chosen = solve(standard_input(sys.stdin.read()))
    print(len(chosen), *chosen)
