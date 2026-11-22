"""AI research draft, agent 1: exact unweighted edge-betweenness per cost.

Brandes (2001), Journal of Mathematical Sociology 25(2):163-177,
doi:10.1080/0022250X.2001.9990249 motivates dependency accumulation.
Independently written edge accumulation, with Fraction to make ties exact.
This ranks a protection heuristic; it does not solve robust flow optimization.
Deliberately ignore demands and attacks to isolate structural centrality.
"""
from collections import deque
from fractions import Fraction
import sys


def read_problem(stream):
    n, m, d, a = map(int, stream.readline().split())
    budget = int(stream.readline().split()[0])
    for _ in range(n):
        x, y = map(float, stream.readline().split())
    edges = [tuple(map(int, stream.readline().split())) for _ in range(m)]
    for _ in range(d + a):
        stream.readline()
    return n, edges, budget


def centrality(n, edges):
    adjacent = [[] for _ in range(n)]
    result = {e[0]: Fraction(0) for e in edges}
    for eid, u, v, capacity, cost in edges:
        adjacent[u].append((v, eid))
        adjacent[v].append((u, eid))
    for source in range(n):
        predecessors = [[] for _ in range(n)]
        distance, paths = [-1] * n, [0] * n
        distance[source], paths[source] = 0, 1
        queue, order = deque([source]), []
        while queue:
            u = queue.popleft()
            order.append(u)
            for v, eid in adjacent[u]:
                if distance[v] == -1:
                    distance[v] = distance[u] + 1
                    queue.append(v)
                if distance[v] == distance[u] + 1:
                    paths[v] += paths[u]
                    predecessors[v].append((u, eid))
        dependency = [Fraction(0) for _ in range(n)]
        for v in reversed(order):
            for u, eid in predecessors[v]:
                contribution = Fraction(paths[u], paths[v]) * (1 + dependency[v])
                result[eid] += contribution
                dependency[u] += contribution
    return {eid: value / 2 for eid, value in result.items()}


def select(n, edges, budget):
    values = centrality(n, edges)
    order = sorted(edges, key=lambda e: (-values[e[0]] / e[4], e[4], e[0]))
    chosen = []
    for eid, u, v, capacity, cost in order:
        if cost <= budget:
            chosen.append(eid)
            budget -= cost
    return sorted(chosen)


if __name__ == '__main__':
    answer = select(*read_problem(sys.stdin))
    print(len(answer), *answer)
