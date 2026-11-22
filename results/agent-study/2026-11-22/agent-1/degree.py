"""AI research draft, agent 1: endpoint-degree-per-cost baseline.

One deterministic pass; ignore demands and attack coordinates deliberately.
Same selection rule as betweenness.py, so the ranking is the controlled variable.
No scenario-specific lookup or optimal-reference access.
"""
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


def select(n, edges, budget):
    degree = [0] * n
    for eid, u, v, capacity, cost in edges:
        degree[u] += 1
        degree[v] += 1
    order = sorted(edges, key=lambda e: (-Fraction(degree[e[1]] + degree[e[2]], e[4]), e[4], e[0]))
    chosen = []
    for eid, u, v, capacity, cost in order:
        if cost <= budget:
            chosen.append(eid)
            budget -= cost
    return sorted(chosen)


if __name__ == '__main__':
    answer = select(*read_problem(sys.stdin))
    print(len(answer), *answer)
