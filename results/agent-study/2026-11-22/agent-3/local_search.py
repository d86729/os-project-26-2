"""공격 후 연결을 비교하는 탐욕·교환 전략. AI 보조 초안이다."""
import sys

IMPROVEMENT_ROUNDS = 3


def solve():
    n, m, demand_count, attack_count = map(int, sys.stdin.readline().split())
    budget = int(sys.stdin.readline().split()[0])
    for _ in range(n):
        sys.stdin.readline()
    edges = []
    for edge_id in range(m):
        start, end, capacity, cost = map(int, sys.stdin.readline().split())
        edges.append((edge_id, start, end, capacity, cost))
    for _ in range(demand_count):
        sys.stdin.readline()
    attacks = []
    for _ in range(attack_count):
        line = sys.stdin.readline().split()
        damaged = tuple(sorted(map(int, line[3:])))
        if damaged not in attacks:
            attacks.append(damaged)

    graph_cache = {}
    score_cache = {}

    def graph_value(remaining):
        if remaining in graph_cache:
            return graph_cache[remaining]
        adjacent = [[] for _ in range(n)]
        capacity = 0
        for edge_id in remaining:
            _, start, end, edge_capacity, _ = edges[edge_id]
            adjacent[start].append(end)
            adjacent[end].append(start)
            capacity += edge_capacity
        visited = [False] * n
        pairs = 0
        for start in range(n):
            if visited[start]:
                continue
            visited[start] = True
            stack = [start]
            size = 0
            while stack:
                node = stack.pop()
                size += 1
                for neighbor in adjacent[node]:
                    if not visited[neighbor]:
                        visited[neighbor] = True
                        stack.append(neighbor)
            pairs += size * (size - 1) // 2
        graph_cache[remaining] = (pairs, capacity)
        return pairs, capacity

    def score(selected):
        key = tuple(selected)
        if key not in score_cache:
            results = []
            for damaged in attacks:
                remaining = tuple(i for i in range(m) if i not in damaged or i in selected)
                results.append(graph_value(remaining))
            profile = tuple(sorted(pairs for pairs, capacity in results))
            capacity_sum = sum(capacity for pairs, capacity in results)
            cost = sum(edges[i][4] for i in selected)
            score_cache[key] = (profile, capacity_sum, -cost)
        return score_cache[key]

    def better(candidate, current):
        a, b = score(candidate), score(current)
        return a > b or (a == b and tuple(candidate) < tuple(current))

    selected = []
    while True:
        best = selected
        for edge_id in range(m):
            if edge_id in selected:
                continue
            candidate = sorted(selected + [edge_id])
            if sum(edges[i][4] for i in candidate) <= budget and better(candidate, best):
                best = candidate
        if best == selected:
            break
        selected = best

    for _ in range(IMPROVEMENT_ROUNDS):
        best = selected
        for outgoing in [None] + selected:
            reduced = [i for i in selected if i != outgoing]
            for incoming in range(m):
                if incoming in reduced:
                    continue
                candidate = sorted(reduced + [incoming])
                if sum(edges[i][4] for i in candidate) <= budget and better(candidate, best):
                    best = candidate
        if best == selected:
            break
        selected = best
    return selected


if __name__ == '__main__':
    answer = solve()
    print(len(answer), *answer)
