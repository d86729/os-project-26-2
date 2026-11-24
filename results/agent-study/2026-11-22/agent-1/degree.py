"""차수/비용 기준선. AI 보조 초안이며 실제 개인 기여는 별도로 기록한다."""
import sys


def solve():
    n, m, demand_count, attack_count = map(int, sys.stdin.readline().split())
    budget = int(sys.stdin.readline().split()[0])
    for _ in range(n):
        sys.stdin.readline()  # 기지 좌표: 이 전략에서는 사용하지 않음
    edges = []
    for edge_id in range(m):
        start, end, capacity, cost = map(int, sys.stdin.readline().split())
        edges.append((edge_id, start, end, capacity, cost))
    for _ in range(demand_count + attack_count):
        sys.stdin.readline()  # 수요와 공격: 이 전략에서는 사용하지 않음

    degree = [0] * n
    for edge_id, start, end, capacity, cost in edges:
        degree[start] += 1
        degree[end] += 1

    # 중요도/비용이 같으면 비용과 번호가 작은 선을 먼저 본다.
    def priority(edge):
        edge_id, start, end, capacity, cost = edge
        importance = degree[start] + degree[end]
        return (-importance / cost, cost, edge_id)

    selected = []
    for edge_id, start, end, capacity, cost in sorted(edges, key=priority):
        if cost <= budget:
            selected.append(edge_id)
            budget -= cost
    return sorted(selected)


if __name__ == '__main__':
    answer = solve()
    print(len(answer), *answer)
