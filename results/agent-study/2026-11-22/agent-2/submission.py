"""AI research draft, agent 2, 2026-11-22. Demand-path repair bundles.

stdin/stdout contract: protection web judge, nodes have x y only.
No precomputed instance answers or optimal-reference data are used.
The surrogate uses reachability, NOT capacity-constrained delivery.
At each iteration choose repair bundle with largest lexicographic gain/cost:
(worst connected pairs, worst reachable demand, mean reachable demand).
Compare ablation_single.py to isolate the candidate-bundle mechanism.
"""
import heapq
import sys

USE_PATH_BUNDLES = True


def read_problem(stream):
    n, m, d, a = map(int, stream.readline().split())
    budget, percent, problem_seed, algorithm_seed = map(int, stream.readline().split())
    for _ in range(n):
        x, y = map(float, stream.readline().split())
    edges = []
    for _ in range(m):
        eid, u, v, capacity, cost = map(int, stream.readline().split())
        assert eid == len(edges)
        edges.append((u, v, capacity, cost))
    demands = []
    for _ in range(d):
        did, source, target, amount = map(int, stream.readline().split())
        demands.append((source, target, amount))
    attacks = []
    for _ in range(a):
        tokens = stream.readline().split()
        count = int(tokens[3])
        ids = frozenset(map(int, tokens[4:]))
        assert len(ids) == count
        attacks.append(ids)
    return n, edges, demands, attacks, budget


def surrogate(n, edges, demands, attacks, chosen):
    pairs, reachable = [], []
    for damaged in attacks:
        parent = list(range(n))
        size = [1] * n
        def find(x):
            while x != parent[x]:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for eid, (u, v, _, _) in enumerate(edges):
            if eid in damaged and eid not in chosen:
                continue
            ru, rv = find(u), find(v)
            if ru != rv:
                parent[rv] = ru
                size[ru] += size[rv]
        pairs.append(sum(size[i] * (size[i] - 1) // 2 for i in range(n) if find(i) == i))
        reachable.append(sum(amount for s, t, amount in demands if find(s) == find(t)))
    # Sum in the third component is proportional to mean for fixed attacks.
    return min(pairs), min(reachable), sum(reachable)


def repair_paths(n, edges, demands, attacks, chosen, remaining):
    """Cheapest additional protection path for each (attack, demand source)."""
    adjacency = [[] for _ in range(n)]
    for eid, (u, v, _, cost) in enumerate(edges):
        adjacency[u].append((v, eid, cost))
        adjacency[v].append((u, eid, cost))
    sources = sorted({s for s, _, _ in demands})
    targets = {s: sorted({t for u, t, _ in demands if u == s}) for s in sources}
    for damaged in attacks:
        for source in sources:
            best = [(float('inf'), n + 1)] * n
            best[source] = (0, 0)
            previous = [None] * n
            queue = [(0, 0, source)]
            while queue:
                cost, hops, u = heapq.heappop(queue)
                if (cost, hops) != best[u]:
                    continue
                for v, eid, price in adjacency[u]:
                    candidate = (cost + (price if eid in damaged and eid not in chosen else 0), hops + 1)
                    if candidate < best[v] and candidate[0] <= remaining:
                        best[v] = candidate
                        previous[v] = (u, eid)
                        heapq.heappush(queue, (*candidate, v))
            for target in targets[source]:
                if best[target][0] > remaining:
                    continue
                extra = set()
                v = target
                while v != source:
                    u, eid = previous[v]
                    if eid in damaged and eid not in chosen:
                        extra.add(eid)
                    v = u
                if extra:
                    yield frozenset(extra)


def solve(problem):
    n, edges, demands, attacks, budget = problem
    chosen = frozenset()
    remaining = budget
    current = surrogate(n, edges, demands, attacks, chosen)
    while True:
        candidates = {frozenset([eid]) for eid, edge in enumerate(edges)
                      if eid not in chosen and edge[3] <= remaining}
        if USE_PATH_BUNDLES:
            candidates.update(repair_paths(n, edges, demands, attacks, chosen, remaining))
        best_key, best_candidate, best_value = None, None, None
        for addition in sorted(candidates, key=lambda ids: tuple(sorted(ids))):
            cost = sum(edges[eid][3] for eid in addition)
            value = surrogate(n, edges, demands, attacks, chosen | addition)
            if value <= current:
                continue
            gain_per_cost = tuple((v - old) / cost for v, old in zip(value, current))
            key = (*gain_per_cost, -cost, tuple(-eid for eid in sorted(addition)))
            if best_key is None or key > best_key:
                best_key, best_candidate, best_value = key, addition, value
        if best_candidate is None:
            break
        chosen |= best_candidate
        remaining -= sum(edges[eid][3] for eid in best_candidate)
        current = best_value
    return sorted(chosen)


if __name__ == '__main__':
    answer = solve(read_problem(sys.stdin))
    print(len(answer), *answer)
