"""간선 매개중심성/비용 기준선. AI 보조 초안이다."""
from fractions import Fraction
import sys


def solve():
    n, m, demand_count, attack_count = map(int, sys.stdin.readline().split())
    budget = int(sys.stdin.readline().split()[0])
    for _ in range(n):
        sys.stdin.readline()
    edges = []
    for edge_id in range(m):
        start, end, capacity, cost = map(int, sys.stdin.readline().split())
        edges.append((edge_id, start, end, capacity, cost))
    for _ in range(demand_count + attack_count):
        sys.stdin.readline()

    adjacent = [[] for _ in range(n)]
    importance = [Fraction(0) for _ in edges]
    for edge_id, start, end, capacity, cost in edges:
        adjacent[start].append((end, edge_id))
        adjacent[end].append((start, edge_id))

    # 각 기지에서 최단 경로를 찾고, 경로 기여도를 역순으로 더한다.
    for source in range(n):
        previous = [[] for _ in range(n)]
        distance, paths = [-1] * n, [0] * n
        distance[source], paths[source] = 0, 1
        queue = [source]
        for node in queue:
            for neighbor, edge_id in adjacent[node]:
                if distance[neighbor] == -1:
                    distance[neighbor] = distance[node] + 1
                    queue.append(neighbor)
                if distance[neighbor] == distance[node] + 1:
                    paths[neighbor] += paths[node]
                    previous[neighbor].append((node, edge_id))
        dependency = [Fraction(0) for _ in range(n)]
        for node in reversed(queue):
            for parent, edge_id in previous[node]:
                part = Fraction(paths[parent], paths[node]) * (1 + dependency[node])
                importance[edge_id] += part
                dependency[parent] += part

    def priority(edge):
        edge_id, start, end, capacity, cost = edge
        return (-importance[edge_id] / cost, cost, edge_id)

    selected = []
    for edge_id, start, end, capacity, cost in sorted(edges, key=priority):
        if cost <= budget:
            selected.append(edge_id)
            budget -= cost
    return sorted(selected)


if __name__ == '__main__':
    answer = solve()
    print(len(answer), *answer)
