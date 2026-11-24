"""수요 경로 기반 방호 전략. AI 보조 초안이다."""
import sys

USE_PATH_BUNDLES = True


def read_problem(stream):
    n, m, d, a = map(int, stream.readline().split())
    budget = int(stream.readline())
    for _ in range(n):
        x, y = map(float, stream.readline().split())
    edges = []
    for _ in range(m):
        u, v, capacity, cost = map(int, stream.readline().split())
        edges.append((u, v, capacity, cost))
    demands = []
    for _ in range(d):
        source, target, amount = map(int, stream.readline().split())
        demands.append((source, target, amount))
    attacks = []
    for _ in range(a):
        tokens = stream.readline().split()
        count = int(tokens[2])
        ids = set(map(int, tokens[3:]))
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
    # 공격 수가 같으므로 합계와 평균은 같은 순서가 된다.
    return min(pairs), min(reachable), sum(reachable)


def repair_paths(n, edges, demands, attacks, chosen, remaining):
    """각 공격과 출발 기지에서 추가 방호 비용이 적은 경로를 찾는다."""
    adjacency = [[] for _ in range(n)]
    for eid, (u, v, _, cost) in enumerate(edges):
        adjacency[u].append((v, eid, cost))
        adjacency[v].append((u, eid, cost))
    repairs = []
    sources = sorted({s for s, _, _ in demands})
    targets = {s: sorted({t for u, t, _ in demands if u == s}) for s in sources}
    for damaged in attacks:
        for source in sources:
            best = [(float('inf'), n + 1)] * n
            best[source] = (0, 0)
            previous = [None] * n
            queue = [(0, 0, source)]
            while queue:
                cost, hops, u = min(queue)
                queue.remove((cost, hops, u))
                if (cost, hops) != best[u]:
                    continue
                for v, eid, price in adjacency[u]:
                    candidate = (cost + (price if eid in damaged and eid not in chosen else 0), hops + 1)
                    if candidate < best[v] and candidate[0] <= remaining:
                        best[v] = candidate
                        previous[v] = (u, eid)
                        queue.append((candidate[0], candidate[1], v))
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
                    repairs.append(tuple(sorted(extra)))

    return repairs


def solve(problem):
    n, edges, demands, attacks, budget = problem
    chosen = set()
    remaining = budget
    current = surrogate(n, edges, demands, attacks, chosen)
    while True:
        candidates = {(eid,) for eid, edge in enumerate(edges)
                      if eid not in chosen and edge[3] <= remaining}
        if USE_PATH_BUNDLES:
            candidates.update(repair_paths(n, edges, demands, attacks, chosen, remaining))
        best_key, best_candidate, best_value = None, None, None
        for addition in sorted(candidates):
            cost = sum(edges[eid][3] for eid in addition)
            value = surrogate(n, edges, demands, attacks, chosen | set(addition))
            if value <= current:
                continue
            gain_per_cost = tuple((v - old) / cost for v, old in zip(value, current))
            key = (*gain_per_cost, -cost, tuple(-eid for eid in sorted(addition)))
            if best_key is None or key > best_key:
                best_key, best_candidate, best_value = key, addition, value
        if best_candidate is None:
            break
        chosen.update(best_candidate)
        remaining -= sum(edges[eid][3] for eid in best_candidate)
        current = best_value
    return sorted(chosen)


if __name__ == '__main__':
    answer = solve(read_problem(sys.stdin))
    print(len(answer), *answer)
