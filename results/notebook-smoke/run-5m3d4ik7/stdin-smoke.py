node_count, edge_count, _, _ = map(int, input().split())
input()
nodes = []
for _ in range(node_count):
    x, y = map(float, input().split())
    nodes.append((x, y))
for _ in range(edge_count):
    _, u, v, _, _ = map(int, input().split())
    assert 0 <= u < len(nodes) and 0 <= v < len(nodes)
print(0)
