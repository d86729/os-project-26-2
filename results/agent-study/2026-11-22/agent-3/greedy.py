"""AI research prototype: connectivity-profile greedy plus bounded exchanges.

Reads only the published stdin; does not import the judge or use references.
Maximize the sorted (ascending) connected-pair counts for distinct damage sets.
Use sum of surviving capacities only as a tie breaker, not an LP flow estimate.
Then prefer lower protection cost and lexicographically smaller edge IDs.
Up to three best-improvement rounds examine add and one-out/one-in neighbors.
This is a surrogate heuristic; official secondary delivery score may decrease.
Inspired by deterministic iterative improvement in Vaessens, Aarts & Lenstra
(1998), A local search template, DOI:10.1016/S0305-0548(97)00093-2.
No optimality or approximation-ratio claim. Source written by Codex agent 3.
"""
import sys

IMPROVEMENT_ROUNDS = 0


def solve(text):
    rows = iter(text.splitlines())
    n, m, d, a = map(int, next(rows).split())
    budget = int(next(rows).split()[0])
    for _ in range(n):
        next(rows)  # coordinates; the input already contains attack damage sets
    edges = [tuple(map(int, next(rows).split())) for _ in range(m)]
    for _ in range(d):
        next(rows)  # demand amounts deliberately absent from this surrogate
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
    # Greedy construction considers every affordable addition at each step.
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


if __name__ == '__main__':
    chosen = solve(sys.stdin.read())
    print(len(chosen), *chosen)
