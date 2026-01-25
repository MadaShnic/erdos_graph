import sqlite3
import unicodedata
from collections import deque, defaultdict
import visual

DB_PATH = "./db/erdos.db"


def normalize_name(name: str) -> str:
    name = name.replace("-", " ")
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()

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
        raise ValueError(f"Autor '{root_author}' nije pronađen u bazi")

    root_id, root_name = root

    graph = defaultdict(set)
    levels = {root_name: 0}

    visited = {root_id}
    queue = deque([(root_id, root_name, 0)])

    while queue:
        person_id, person_name, depth = queue.popleft()

        if depth >= max_depth:
            continue

        coauthors = get_coauthors(conn, person_id)

        for co_id, co_name in coauthors:
            graph[person_name].add(co_name)

            if co_id not in visited:
                visited.add(co_id)
                levels[co_name] = depth + 1
                queue.append((co_id, co_name, depth + 1))

    conn.close()
    return graph, levels


def main():
    root_author = "Mario Osvin Pavčević"   # ili "Anamari Nakić"
    max_depth = 3

    graph, levels = build_coauthor_graph_from_db(
        root_author=root_author,
        max_depth=max_depth
    )

    visual.run_dash_app(graph, levels, root_author)


if __name__ == "__main__":
    main()
