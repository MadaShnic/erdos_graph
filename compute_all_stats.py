import sqlite3
import networkx as nx
from collections import Counter
import os

from build_graph import (
    build_coauthor_graph_from_db,
    compute_person_stats,
    compute_graph_metrics,
    degree_centrality,
    clustering_coefficient
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DB = os.path.join(BASE_DIR, "db", "statistics.db")

DB_PATH = "./db/erdos.db"


def get_all_authors_with_papers():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT p.full_name
        FROM person p
        JOIN authorship a ON p.id = a.person_id
    """)

    authors = [r[0] for r in cur.fetchall()]
    conn.close()
    return authors


def build_nx_graph(graph_dict):
    G = nx.Graph()
    for a, coauthors in graph_dict.items():
        for c in coauthors:
            G.add_edge(a, c)
    return G

# NOVI KOD
def compute_collab_from_papers(conn, person_id):
    cur = conn.cursor()

    cur.execute("""
        SELECT p.fer_author_count, p.external_author_count
        FROM paper p
        JOIN authorship a ON p.id = a.paper_id
        WHERE a.person_id = ?
    """, (person_id,))

    rows = cur.fetchall()

    if len(rows) == 0:
        return None

    internal = 0
    external = 0

    for fer, ext in rows:
        paper_score = (fer or 0) - (ext or 0)

        if paper_score > 0:
            internal += 1
        elif paper_score < 0:
            external += 1

    if internal > external:
        return "internal"
    elif external > internal:
        return "external"
    elif internal == external:
        return "balanced"

# =========================
# 🔥 GRAPH → SCORE
# =========================
def compute_graph_collab(G_int, person_types):
    total = 0

    for n in G_int.nodes():
        t = person_types.get(n)

        if t == "internal":
            total += 1
        elif t == "external":
            total -= 1
        # balanced = 0

    if total > 0:
        return "internal"
    elif total < 0:
        return "external"
    elif total == 0:
        return "balanced"


def main():
    authors = get_all_authors_with_papers()

    conn_out = sqlite3.connect(OUT_DB)
    cur_out = conn_out.cursor()

    cur_out.execute("DROP TABLE IF EXISTS author_stats")

    # 🔥 NOVA TABLICA
    cur_out.execute("""
        CREATE TABLE author_stats (
            author TEXT PRIMARY KEY,

            total_papers INT,
            solo_papers INT,
            collab_papers INT,

            degree INT,
            centrality REAL,
            clustering REAL,

            graph_nodes INT,
            graph_edges INT,
            avg_degree REAL,
            density REAL,
            components INT,

            avg_centrality REAL,
            avg_clustering REAL,

            gender_ratio REAL,
            dominant_department TEXT,
            dominant_title TEXT,

            avg_papers REAL,
            solo_ratio REAL,

            person_collab_type TEXT,
            graph_collab_type TEXT
        )
    """)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # person info
    cur.execute("SELECT id, full_name, gender, department, title FROM person")
    person_info = {
        name: {
            "id": pid,
            "gender": gender,
            "department": dept,
            "title": title
        }
        for pid, name, gender, dept, title in cur.fetchall()
    }

    # stats cache
    person_stats_cache = {
        name: compute_person_stats(conn, info["id"])
        for name, info in person_info.items()
    }

    # 🔥 PERSON TYPE CACHE
    person_collab_cache = {
        # fix ovdje
        name: compute_collab_from_papers(conn, info["id"])
        for name, info in person_info.items()
    }

    for author in authors:
        try:
            graph_dict, levels = build_coauthor_graph_from_db(author, 3)
            G = build_nx_graph(graph_dict)

            internal_nodes = [n for n in G if not n.startswith("EXT::")]
            G_int = G.subgraph(internal_nodes)

            if author not in person_stats_cache:
                continue

            stats = person_stats_cache[author]
            centrality_map = degree_centrality(graph_dict)

            degree = G_int.degree(author) if author in G_int else 0
            centrality = centrality_map.get(author, 0)
            clustering = clustering_coefficient(graph_dict, author)

            # GRAPH
            num_nodes = len(G_int.nodes())
            num_edges = len(G_int.edges())
            avg_degree = sum(dict(G_int.degree()).values()) / num_nodes if num_nodes else 0
            density = nx.density(G_int) if num_nodes > 1 else 0
            components = nx.number_connected_components(G_int)

            metrics = compute_graph_metrics(graph_dict, author)

            # COMMUNITY
            genders, depts, titles, papers = [], [], [], []

            for n in G_int.nodes():
                if n in person_stats_cache:
                    info = person_info[n]

                    if info["gender"]:
                        genders.append(info["gender"])
                    if info["department"]:
                        depts.append(info["department"])
                    if info["title"]:
                        titles.append(info["title"])

                    papers.append(person_stats_cache[n]["total"])

            gender_ratio = genders.count("F") / len(genders) if genders else 0

            dominant_department = Counter(depts).most_common(1)
            dominant_department = dominant_department[0][0] if dominant_department else None

            dominant_title = Counter(titles).most_common(1)
            dominant_title = dominant_title[0][0] if dominant_title else None

            avg_papers = sum(papers) / len(papers) if papers else 0

            total_solo = sum(person_stats_cache[n]["solo"] for n in G_int.nodes() if n in person_stats_cache)
            total_collab = sum(person_stats_cache[n]["collab"] for n in G_int.nodes() if n in person_stats_cache)

            solo_ratio = total_solo / (total_solo + total_collab) if (total_solo + total_collab) else 0

            # 🔥 FINAL CLASSIFICATION
            person_collab_type = person_collab_cache.get(author, None)
            graph_collab_type = compute_graph_collab(G_int, person_collab_cache)

            values = (
                author,
                stats["total"],
                stats["solo"],
                stats["collab"],

                degree,
                centrality,
                clustering,

                num_nodes,
                num_edges,
                avg_degree,
                density,
                components,

                metrics["avg_centrality"],
                metrics["avg_clustering"],

                gender_ratio,
                dominant_department,
                dominant_title,

                avg_papers,
                solo_ratio,

                person_collab_type,
                graph_collab_type
            )

            assert len(values) == 21

            cur_out.execute("""
                INSERT OR REPLACE INTO author_stats (
                    author,
                    total_papers,
                    solo_papers,
                    collab_papers,
                    degree,
                    centrality,
                    clustering,
                    graph_nodes,
                    graph_edges,
                    avg_degree,
                    density,
                    components,
                    avg_centrality,
                    avg_clustering,
                    gender_ratio,
                    dominant_department,
                    dominant_title,
                    avg_papers,
                    solo_ratio,
                    person_collab_type,
                    graph_collab_type
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, values)

            print("OK:", author)

        except Exception as e:
            print(f"{author}: {e}")

    conn_out.commit()
    conn_out.close()
    conn.close()


if __name__ == "__main__":
    main()