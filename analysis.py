import sqlite3
import matplotlib.pyplot as plt

DB = "./db/statistics.db"


def load_data():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        SELECT
            author,
            graph_nodes,
            graph_edges,
            avg_degree,
            density,
            avg_clustering,
            centrality,
            clustering
        FROM author_stats
        WHERE graph_nodes > 0
    """)

    rows = cur.fetchall()
    conn.close()

    data = []

    for r in rows:
        author, nodes, edges, avg_deg, density, avg_clust, cent, clust = r

        data.append({
            "author": author,
            "nodes": nodes,
            "edges": edges,
            "avg_degree": avg_deg,
            "density": density,
            "avg_clustering": avg_clust,
            "centrality": cent,
            "clustering": clust
        })

    return data


def split_groups(data):
    small = [d for d in data if d["nodes"] < 30]
    medium = [d for d in data if 30 <= d["nodes"] < 60]
    large = [d for d in data if d["nodes"] >= 60]
    return small, medium, large


def scatter(ax, x_small, y_small, x_medium, y_medium, x_large, y_large, title, xlabel, ylabel):
    ax.scatter(x_small, y_small, label="small (<30)", color="blue")
    ax.scatter(x_medium, y_medium, label="medium (30-60)", color="green")
    ax.scatter(x_large, y_large, label="large (>=60)", color="orange")

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend()


def main():
    data = load_data()
    small, medium, large = split_groups(data)

    fig, axs = plt.subplots(2, 3, figsize=(15, 10))

    # 1. nodes vs density
    scatter(
        axs[0, 0],
        [d["nodes"] for d in small],
        [d["density"] for d in small],
        [d["nodes"] for d in medium],
        [d["density"] for d in medium],
        [d["nodes"] for d in large],
        [d["density"] for d in large],
        "Nodes vs Density",
        "Nodes",
        "Density"
    )

    # 2. nodes vs avg clustering (graf)
    scatter(
        axs[0, 1],
        [d["nodes"] for d in small],
        [d["avg_clustering"] for d in small],
        [d["nodes"] for d in medium],
        [d["avg_clustering"] for d in medium],
        [d["nodes"] for d in large],
        [d["avg_clustering"] for d in large],
        "Nodes vs Avg Clustering (Graph)",
        "Nodes",
        "Avg Clustering"
    )

    # 3. nodes vs centrality (root)
    scatter(
        axs[0, 2],
        [d["nodes"] for d in small],
        [d["centrality"] for d in small],
        [d["nodes"] for d in medium],
        [d["centrality"] for d in medium],
        [d["nodes"] for d in large],
        [d["centrality"] for d in large],
        "Nodes vs Root Centrality",
        "Nodes",
        "Centrality"
    )

    # 4. avg_degree vs avg_clustering
    scatter(
        axs[1, 0],
        [d["avg_degree"] for d in small],
        [d["avg_clustering"] for d in small],
        [d["avg_degree"] for d in medium],
        [d["avg_clustering"] for d in medium],
        [d["avg_degree"] for d in large],
        [d["avg_clustering"] for d in large],
        "Avg Degree vs Avg Clustering",
        "Avg Degree",
        "Avg Clustering"
    )

    # 5. nodes vs root clustering
    scatter(
        axs[1, 1],
        [d["nodes"] for d in small],
        [d["clustering"] for d in small],
        [d["nodes"] for d in medium],
        [d["clustering"] for d in medium],
        [d["nodes"] for d in large],
        [d["clustering"] for d in large],
        "Nodes vs Root Clustering",
        "Nodes",
        "Clustering"
    )

    # 6. root vs graph clustering
    scatter(
        axs[1, 2],
        [d["clustering"] for d in small],
        [d["avg_clustering"] for d in small],
        [d["clustering"] for d in medium],
        [d["avg_clustering"] for d in medium],
        [d["clustering"] for d in large],
        [d["avg_clustering"] for d in large],
        "Root vs Graph Clustering",
        "Root Clustering",
        "Avg Clustering"
    )

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()