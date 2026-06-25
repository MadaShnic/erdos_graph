import sqlite3
import unicodedata
from collections import deque, defaultdict

DB_PATH = "./db/erdos.db"


def normalize_name(name: str) -> str:
    name = name.replace("-", " ")
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()

def get_person_id(conn, full_name):
    cur = conn.cursor()
    cur.execute("SELECT id, full_name FROM person")

    target = normalize_name(full_name)

    for pid, fname in cur.fetchall():
        if normalize_name(fname) == target:
            return pid, fname

    return None


def get_coauthors(conn, person_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT p2.id, p2.full_name
        FROM authorship a1
        JOIN authorship a2 ON a1.paper_id = a2.paper_id
        JOIN person p2 ON a2.person_id = p2.id
        WHERE a1.person_id = ?
          AND a2.person_id != ?
    """, (person_id, person_id))
    return cur.fetchall()


def build_coauthor_graph_from_db(root_author, max_depth):
    conn = sqlite3.connect(DB_PATH)

    root = get_person_id(conn, root_author)
    if root is None:
        raise ValueError(f"Autor '{root_author}' nije u bazi")

    root_id, root_name = root

    graph = defaultdict(set)
    levels = {root_name: 0}

    visited = {root_id}
    queue = deque([(root_id, root_name, 0)])

    while queue:
        person_id, person_name, depth = queue.popleft()

        # ensure that node exists
        graph[person_name]

        coauthors = get_coauthors(conn, person_id)

        # edge node (depth == max_depth)
        if depth == max_depth:
            for co_id, co_name in coauthors:

                if co_name in graph:
                    # already in graph
                    graph[person_name].add(co_name)
                    graph[co_name].add(person_name)
                else:
                    # external node
                    ext_node = f"EXT::{co_name}"
                    graph[person_name].add(ext_node)
                    graph[ext_node].add(person_name)

                    levels[ext_node] = depth + 1

            continue

        # BFS
        for co_id, co_name in coauthors:
            graph[person_name].add(co_name)
            graph[co_name].add(person_name)

            if co_id not in visited:
                visited.add(co_id)
                levels[co_name] = depth + 1
                queue.append((co_id, co_name, depth + 1))

    conn.close()
    return graph, levels


def compute_person_stats(conn, person_id):
    cur = conn.cursor()

    # total papers
    cur.execute("""
        SELECT COUNT(*) FROM authorship
        WHERE person_id = ?
    """, (person_id,))
    total = cur.fetchone()[0]

    # uzmi sve papere osobe + external info
    cur.execute("""
        SELECT p.id, p.external_author_count,
               COUNT(a.person_id) as fer_count
        FROM paper p
        JOIN authorship a ON p.id = a.paper_id
        WHERE p.id IN (
            SELECT paper_id FROM authorship WHERE person_id = ?
        )
        GROUP BY p.id
    """, (person_id,))

    solo = 0
    collab = 0

    for _, external_cnt, fer_cnt in cur.fetchall():
        # SOLO samo ako:
        # - samo 1 FER autor
        # - nema external autora
        if fer_cnt == 1 and external_cnt == 0:
            solo += 1
        else:
            collab += 1

    return {
        "total": total,
        "solo": solo,
        "collab": collab
    }

def degree_centrality(graph):
    # samo pravi čvorovi
    valid_nodes = [n for n in graph if not n.startswith("EXT::")]
    N = len(valid_nodes)

    centrality = {}

    for node in valid_nodes:
        deg = sum(1 for n in graph[node] if not n.startswith("EXT::"))
        centrality[node] = deg / (N - 1) if N > 1 else 0

    return centrality


def clustering_coefficient(graph, node):
    neighbors = [n for n in graph[node] if not n.startswith("EXT::")]
    k = len(neighbors)

    if k < 2:
        return 0

    links = 0

    for i in range(k):
        for j in range(i + 1, k):
            if neighbors[j] in graph[neighbors[i]]:
                links += 1

    return (2 * links) / (k * (k - 1))


def average_clustering(graph):
    valid_nodes = [n for n in graph if not n.startswith("EXT::")]
    return sum(clustering_coefficient(graph, n) for n in valid_nodes) / len(valid_nodes)


def average_centrality(centrality_dict):
    return sum(centrality_dict.values()) / len(centrality_dict)

def compute_graph_metrics(graph, root_name):
    centrality = degree_centrality(graph)

    valid_nodes = [n for n in graph if not n.startswith("EXT::")]

    root_centrality = centrality.get(root_name, 0)
    avg_centrality = sum(centrality[n] for n in valid_nodes) / len(valid_nodes)

    root_clustering = clustering_coefficient(graph, root_name)
    avg_clustering = average_clustering(graph)

    return {
        "root_centrality": root_centrality,
        "avg_centrality": avg_centrality,
        "root_clustering": root_clustering,
        "avg_clustering": avg_clustering
    }
