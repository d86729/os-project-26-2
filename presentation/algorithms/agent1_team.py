# 1번 기준선 A: 양 끝 기지의 연결 수 / 방호 비용
n, m, demand_count, attack_count = map(int, input().split())
budget = int(input().split()[0])  # 예산 뒤에 부가 정보가 있어도 첫 값만 쓴다.

for _ in range(n):
    input()  # 좌표는 이 전략에서 사용하지 않는다.

edges = []
degree = [0] * n
for _ in range(m):
    u, v, capacity, cost = map(int, input().split()[-4:])  # 선 번호가 앞에 있어도 끝의 네 값 사용
    edges.append((u, v, cost))
    degree[u] += 1
    degree[v] += 1

# 가성비가 같으면 비용이 작은 선, 그다음 번호가 작은 선을 먼저 본다.
def priority(i):
    u, v, cost = edges[i]
    return (-(degree[u] + degree[v]) / cost, cost, i)

selected = []
for i in sorted(range(m), key=priority):
    cost = edges[i][2]
    if cost <= budget:
        selected.append(i)
        budget -= cost

selected.sort()
print(len(selected), *selected)
