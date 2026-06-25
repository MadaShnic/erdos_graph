from collections import deque
from build_graph import build_coauthor_graph_from_db

ROOT = "Stjepan Groš"


def bfs_distances(graph, start):
    visited = {start}
    dist = {start: 0}
    parent = {start: None}

    q = deque([start])

    while q:
        node = q.popleft()

        for nbr in graph[node]:
            if nbr.startswith("EXT::"):
                continue

            if nbr not in visited:
                visited.add(nbr)
                dist[nbr] = dist[node] + 1
                parent[nbr] = node
                q.append(nbr)

    return dist, parent


def reconstruct_path(parent, target):
    path = []
    cur = target

    while cur is not None:
        path.append(cur)
        cur = parent[cur]

    return list(reversed(path))


def compute_diameter(graph):
    nodes = [n for n in graph if not n.startswith("EXT::")]

    max_dist = 0
    best_pair = (None, None)
    best_path = []

    for node in nodes:
        dist, parent = bfs_distances(graph, node)

        far_node = max(dist, key=dist.get)

        if dist[far_node] > max_dist:
            max_dist = dist[far_node]
            best_pair = (node, far_node)
            best_path = reconstruct_path(parent, far_node)

    return max_dist, best_pair, best_path


def main():
    # veliki depth da "pokupi sve"
    graph, levels = build_coauthor_graph_from_db(ROOT, max_depth=100)

    # RADIJUS (maks udaljenost od Groša)
    dist, parent = bfs_distances(graph, ROOT)

    radius = max(dist.values())
    farthest_node = max(dist, key=dist.get)
    path = reconstruct_path(parent, farthest_node)

    print("=== GROŠ METRIKE ===")
    print("Velicina grafa:", len(graph))
    print(f"Radijus mreže (od {ROOT}): {radius}")
    print(f"Najudaljeniji autor: {farthest_node}")
    print("Put:")
    print(" -> ".join(path))

    print("\n=== GLOBALNA DUBINA (DIAMETER) ===")
    diameter, (a, b), dia_path = compute_diameter(graph)

    print(f"Diameter mreže: {diameter}")
    print(f"Između: {a} ↔ {b}")
    print("Put:")
    print(" -> ".join(dia_path))


if __name__ == "__main__":
    main()