import heapq
def solve(N, edges, demands, attacks, budget, bundle_mode=True):
    # edges: [(u, v, cost), ...], demands: [(s, d, vol), ...], attacks: [set(끊긴선), ...]
    adj = [[] for _ in range(N)]
    for i, (u, v, _) in enumerate(edges):
        adj[u].append((v, i)); adj[v].append((u, i))
    # 1. 평가: (최악 연결쌍, 최악 생존수요, 총 생존수요)
    def eval_state(prot):
        res = []
        for brk in attacks:
            vis, pairs = [-1]*N, 0
            for i in range(N):
                if vis[i] == -1:
                    q = [i]; vis[i] = i; cnt = 1
                    while q:
                        u = q.pop()
                        for v, e in adj[u]:
                            if vis[v] == -1 and (e not in brk or e in prot):
                                vis[v] = i; q.append(v); cnt += 1
                    pairs += cnt*(cnt-1)//2
            dem = sum(vol for s, d, vol in demands if vis[s] == vis[d])
            res.append((pairs, dem))
        return (min(p for p, _ in res), min(d for _, d in res), sum(d for _, d in res))
    prot, cur = set(), eval_state(set())
    while True:
        # 2. 후보 생성 (단일선 + 다익스트라 경로묶음)
        cands = {frozenset([i]) for i in range(len(edges)) if i not in prot and edges[i][2] <= budget}
        if bundle_mode:
            for brk in attacks:
                for s, d, _ in demands:
                    dist, par, pq = [1e9]*N, [None]*N, [(0, s)]; dist[s] = 0
                    while pq:
                        c, u = heapq.heappop(pq)
                        if c > dist[u] or u == d: continue
                        for v, e in adj[u]:
                            w = edges[e][2] if (e in brk and e not in prot) else 0
                            if c + w < dist[v]: dist[v] = c + w; par[v] = (u, e); heapq.heappush(pq, (dist[v], v))
                    if 0 < dist[d] <= budget:
                        b, u = set(), d
                        while u != s:
                            u, e = par[u]
                            if e in brk and e not in prot: b.add(e)
                        cands.add(frozenset(b))
        # 3. 3단계 가성비 최고 후보 선택
        best, best_g = None, (0, 0, 0)
        for c in cands:
            cost = sum(edges[i][2] for i in c)
            if 0 < cost <= budget:
                nxt = eval_state(prot | c)
                g = tuple((nxt[k] - cur[k]) / cost for k in range(3))
                if g > best_g: best, best_g = c, g
        if not best: break
        prot |= best; budget -= sum(edges[i][2] for i in best); cur = eval_state(prot)
    return sorted(prot)

# 공통 텍스트 입력을 동윤이의 solve 함수가 받는 형태로 변환합니다.
def read_problem():
    import sys
    stream = sys.stdin
    n, m, demand_count, attack_count = map(int, stream.readline().split())
    budget_fields = stream.readline().split()
    budget = int(budget_fields[0])
    legacy = len(budget_fields) > 1  # 일부 입력에는 예산 뒤에 부가 값이 있습니다.
    for _ in range(n):
        stream.readline()  # 이 전략은 좌표를 직접 사용하지 않습니다.
    edges = []
    for _ in range(m):
        u, v, capacity, cost = map(int, stream.readline().split()[-4:])
        edges.append((u, v, cost))
    demands = [tuple(map(int, stream.readline().split()[-3:])) for _ in range(demand_count)]
    attacks = []
    for _ in range(attack_count):
        fields = stream.readline().split()
        if legacy:
            fields = fields[1:]  # 입력에 포함된 공격 번호를 제외합니다.
        attacks.append(set(map(int, fields[3:])))
    return n, edges, demands, attacks, budget


if __name__ == '__main__':
    answer = solve(*read_problem())
    print(len(answer), *answer)
