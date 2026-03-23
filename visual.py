from dash import Dash, dcc, html, Input, Output
import networkx as nx
import plotly.graph_objects as go
import sqlite3

DB_PATH = "./db/erdos.db"


def run_dash_app(graph, levels, root_author):
    app = Dash(__name__)

    # ---------------- DB LOAD ----------------
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    person_info = {}
    stats_map = {}

    # load basic info
    cur.execute("SELECT id, full_name, gender, department, title FROM person")
    for pid, name, gender, dept, title in cur.fetchall():
        person_info[name] = {
            "id": pid,
            "gender": gender,
            "department": dept,
            "title": title
        }

    # compute stats
    for name, info in person_info.items():
        stats_map[name] = compute_person_stats(conn, info["id"])

    conn.close()

    # ---------------- GRAPH ----------------
    G = nx.Graph()
    for a, coauthors in graph.items():
        for c in coauthors:
            G.add_edge(a, c)

    pos = nx.spring_layout(G, k=1.2, iterations=100, seed=42)

    # ---------------- LAYOUT ----------------
    app.layout = html.Div([
        html.H2(f"Erdős Coauthor Graph – {root_author}"),
        dcc.Graph(
            id="graph",
            figure=make_figure(G, pos, levels, root_author, person_info, stats_map),
            clear_on_unhover=True,
            style={"height": "90vh"}
        )
    ])

    # ---------------- CALLBACK ----------------
    @app.callback(
        Output("graph", "figure"),
        Input("graph", "hoverData")
    )
    def highlight_subgraph(hoverData):
        if hoverData is None:
            return make_figure(G, pos, levels, root_author, person_info, stats_map)

        point_data = hoverData["points"][0]

        if "customdata" not in point_data:
            return make_figure(G, pos, levels, root_author, person_info, stats_map)

        if point_data["curveNumber"] != 1:
            return make_figure(G, pos, levels, root_author, person_info, stats_map)

        node = point_data["customdata"]
        neighbors = set(G.neighbors(node)) | {node}

        return make_figure(
            G, pos, levels, root_author,
            person_info, stats_map,
            highlight_nodes=neighbors
        )

    app.run(debug=True)


# ---------------- STATS ----------------

def compute_person_stats(conn, person_id):
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) FROM authorship
        WHERE person_id = ?
    """, (person_id,))
    total = cur.fetchone()[0]

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
        if fer_cnt == 1 and external_cnt == 0:
            solo += 1
        else:
            collab += 1

    return {
        "total": total,
        "solo": solo,
        "collab": collab
    }


# ---------------- FIGURE ----------------

def make_figure(G, pos, levels, root_author, person_info, stats_map, highlight_nodes=None):
    edge_x = []
    edge_y = []

    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        line=dict(width=1, color="#888"),
        hoverinfo="none",
        opacity=0.5
    )

    node_x = []
    node_y = []
    node_color = []
    node_opacity = []
    hover_text = []
    labels = []

    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)

        # ---------------- EXTERNAL NODE ----------------
        if node.startswith("EXT::"):
            real_name = node.split("::")[-1]

            hover_text.append(
                f"<b>{real_name}</b><br>External collaborator"
            )

            node_color.append("gray")
            node_opacity.append(0.4)
            labels.append("")  # nema labelu
            continue

        # ---------------- NORMAL NODE ----------------
        level = levels.get(node, "?")

        info = person_info.get(node, {})
        stats = stats_map.get(node, {})

        hover_text.append(
            f"<b>{node}</b><br>"
            f"Erdős number: {level}<br>"
            f"Department: {info.get('department', 'N/A')}<br>"
            f"Gender: {info.get('gender', 'N/A')}<br>"
            f"Title: {info.get('title', 'N/A')}<br>"
            f"Papers: {stats.get('total', 0)}<br>"
            f"Solo: {stats.get('solo', 0)}<br>"
            f"Collaborations: {stats.get('collab', 0)}"
        )

        labels.append(node)

        # boje
        if node == root_author:
            node_color.append("red")
        elif level == 1:
            node_color.append("skyblue")
        else:
            node_color.append("lightgreen")

        if highlight_nodes:
            node_opacity.append(1.0 if node in highlight_nodes else 0.1)
        else:
            node_opacity.append(1.0)

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=labels,
        customdata=list(G.nodes()),
        textposition="top center",
        hoverinfo="text",
        hovertext=hover_text,
        marker=dict(
            size=18,
            color=node_color,
            opacity=node_opacity,
            line=dict(width=2)
        )
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        showlegend=False,
        hovermode="closest",
        margin=dict(l=20, r=20, t=40, b=20)
    )

    return fig