from dash import Dash, dcc, html, Input, Output
import networkx as nx
import plotly.graph_objects as go
import sqlite3
import statistics
from collections import Counter

from build_graph import build_coauthor_graph_from_db, compute_person_stats

DB_PATH = "./db/erdos.db"


def load_all_names():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT full_name FROM person")
    names = [r[0] for r in cur.fetchall()]
    conn.close()
    return sorted(names)


def run_dash_app():
    app = Dash(__name__)
    all_names = load_all_names()

    # ---------------- LAYOUT ----------------
    app.layout = html.Div([

        html.Div([
            html.H3("Controls"),
            dcc.Store(id="selected-node", data=None),

            dcc.Dropdown(
                id="author-dropdown",
                options=[{"label": n, "value": n} for n in all_names],
                placeholder="Search author...",
                style={"width": "100%"}
            ),

            html.Hr(),

            html.Label("Color by"),
            dcc.RadioItems(
                id="color-mode",
                options=[
                    {"label": "Level", "value": "level"},
                    {"label": "Gender", "value": "gender"},
                    {"label": "Department", "value": "dept"},
                    {"label": "Title", "value": "title"},
                    {"label": "Collaboration Preference", "value": "collab"},
                ],
                value="level"
            ),

            html.Div(id="legend-box", style={"marginTop": "20px"}),

            html.Hr(),

            html.H3("Statistics"),
            html.Div(id="stats-box")
        ], style={
            "width": "20%",
            "position": "fixed",
            "right": "0",
            "top": "0",
            "height": "100%",
            "padding": "15px",
            "background": "#f4f4f4",
            "overflowY": "auto"
        }),

        html.Div([
            html.H2(id="title"),
            dcc.Graph(
                id="graph",
                style={"height": "95vh"}
            )
        ], style={
            "width": "70%",
            "display": "inline-block"
        })
    ])

    # ---------------- CLICK STORE ----------------
    @app.callback(
        Output("selected-node", "data"),
        Input("graph", "clickData"),
        Input("selected-node", "data"),
        prevent_initial_call=True
    )
    def store_clicked_node(clickData, current):
        if not clickData or "points" not in clickData:
            return None

        point = clickData["points"][0]
        if "hovertext" not in point:
            return None

        raw = point["hovertext"]
        node = raw.split("<br>")[0].replace("<b>", "").replace("</b>", "")

        # toggle reset
        if current == node:
            return None

        return node

    # ---------------- MAIN CALLBACK ----------------
    @app.callback(
        Output("graph", "figure"),
        Output("title", "children"),
        Output("legend-box", "children"),
        Output("stats-box", "children"),
        Input("author-dropdown", "value"),
        Input("color-mode", "value"),
        Input("selected-node", "data"),
        prevent_initial_call=True
    )
    def update_graph(author, color_mode, selected_node):
        if not author:
            return go.Figure(), "Select author", "", ""

        graph, levels = build_coauthor_graph_from_db(author, 3)

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        person_info = {}
        stats_map = {}

        cur.execute("SELECT id, full_name, gender, department, title FROM person")
        for pid, name, gender, dept, title in cur.fetchall():
            person_info[name] = {
                "id": pid,
                "gender": gender,
                "department": dept,
                "title": title
            }

        for name, info in person_info.items():
            stats_map[name] = compute_person_stats(conn, info["id"])

        conn.close()

        # Build graph
        G = nx.Graph()
        for a, coauthors in graph.items():
            for c in coauthors:
                G.add_edge(a, c)

        # ---------------- COLLAB SCORE ----------------
        for node in G.nodes():
            if node.startswith("EXT::"):
                continue

            score = 0
            for n in G.neighbors(node):
                score += -1 if n.startswith("EXT::") else 1

            stats_map.setdefault(node, {})
            stats_map[node]["collab_score"] = score

        pos = nx.spring_layout(G, k=1.2, iterations=80, seed=42)

        highlight_nodes = None
        if selected_node and selected_node in G:
            neighbors = set(G.neighbors(selected_node))
            highlight_nodes = neighbors | {selected_node} if neighbors else {selected_node}

        # ---------------- GRAPH PROPERTIES ----------------
        num_nodes = len(G.nodes())
        num_edges = len(G.edges())
        degrees = dict(G.degree())
        deg_vals = list(degrees.values())
        avg_degree = round(sum(deg_vals) / num_nodes, 2) if num_nodes else 0
        median_degree = statistics.median(deg_vals) if deg_vals else 0
        density = round(nx.density(G), 4) if num_nodes > 1 else 0
        components = nx.number_connected_components(G)

        # ---------------- COMMUNITY INSIGHTS ----------------
        papers = [
            stats_map[n]["total"]
            for n in G.nodes()
            if not n.startswith("EXT::") and n in stats_map and stats_map[n].get("total", 0) > 0
        ]
        avg_papers = round(sum(papers) / len(papers), 2) if papers else 0
        median_papers = statistics.median(papers) if papers else 0
        total_solo = sum(
            stats_map[n].get("solo", 0)
            for n in G.nodes()
            if not n.startswith("EXT::") and n in stats_map
        )
        total_collab = sum(
            stats_map[n].get("collab", 0)
            for n in G.nodes()
            if not n.startswith("EXT::") and n in stats_map
        )
        ratio = round(total_solo / (total_solo + total_collab), 2) if (total_solo + total_collab) else 0
        depts = [
            person_info[n]["department"]
            for n in G.nodes()
            if not n.startswith("EXT::") and n in person_info and person_info[n].get("department")
        ]
        dominant_dept = Counter(depts).most_common(1)
        dominant_dept = dominant_dept[0][0] if dominant_dept else "N/A"
        titles = [
            person_info[n]["title"]
            for n in G.nodes()
            if not n.startswith("EXT::") and n in person_info and person_info[n].get("title")
        ]
        dominant_title = Counter(titles).most_common(1)
        dominant_title = dominant_title[0][0] if dominant_title else "N/A"

        # ---------------- STATS BOX ----------------
        stats_box = html.Div([
            html.H4("Graph Properties"),
            html.P(f"Nodes: {num_nodes}"),
            html.P(f"Edges: {num_edges}"),
            html.P(f"Avg degree: {avg_degree}"),
            html.P(f"Median degree: {median_degree}"),
            html.P(f"Density: {density}"),
            html.P(f"Components: {components}"),
            html.Hr(),
            html.H4("Community Insights"),
            html.P(f"Dominant dept: {dominant_dept}"),
            html.P(f"Dominant title: {dominant_title}"),
            html.P(f"Avg papers: {avg_papers}"),
            html.P(f"Median papers: {median_papers}"),
            html.P(f"Solo ratio: {ratio}")
        ])

        fig, legend = make_figure(
            G, pos, levels, author, person_info, stats_map, color_mode, highlight_nodes
        )

        return fig, f"Erdős Graph – {author}", legend, stats_box

    app.run(debug=True)


# ---------------- FIGURE ----------------
def make_figure(G, pos, levels, root_author, person_info, stats_map, color_mode, highlight_nodes=None):

    is_highlight_mode = highlight_nodes is not None and len(highlight_nodes) > 0

    edge_x_normal, edge_y_normal = [], []
    edge_x_highlight, edge_y_highlight = [], []

    # ---------------- EDGES ----------------
    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]

        if is_highlight_mode and u in highlight_nodes and v in highlight_nodes:
            edge_x_highlight += [x0, x1, None]
            edge_y_highlight += [y0, y1, None]
        else:
            edge_x_normal += [x0, x1, None]
            edge_y_normal += [y0, y1, None]

    edge_trace_normal = go.Scatter(
        x=edge_x_normal,
        y=edge_y_normal,
        mode="lines",
        line=dict(width=1, color="#888"),
        hoverinfo="none",
        opacity=0.4
    )

    edge_trace_highlight = go.Scatter(
        x=edge_x_highlight,
        y=edge_y_highlight,
        mode="lines",
        line=dict(width=2.5, color="#222"),
        hoverinfo="none",
        opacity=0.9
    )

    # ---------------- NODES ----------------
    node_x, node_y = [], []
    node_color, node_opacity = [], []
    hover_text, labels = [], []

    dept_colors = {}
    color_palette = [
        "red", "blue", "green", "orange", "purple",
        "brown", "pink", "cyan", "yellow"
    ]
    color_index = 0

    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)

        is_highlighted = (not is_highlight_mode) or (node in highlight_nodes)

        # ---------------- EXTERNAL ----------------
        if node.startswith("EXT::"):
            real_name = node.split("::")[-1]

            hover_text.append(f"<b>{real_name}</b><br>External collaborator")

            node_color.append("#C0C0C0")
            node_opacity.append(1.0 if is_highlighted else 0.1)

            labels.append(real_name if is_highlighted or not is_highlight_mode else "")
            continue

        level = levels.get(node, "?")
        info = person_info.get(node, {})
        stats = stats_map.get(node, {})
        degree = G.degree(node)

        score = stats.get("collab_score", 0)
        collab_type = "Internal" if score > 0 else "External" if score < 0 else "Balanced"

        hover_text.append(
            f"<b>{node}</b><br>"
            f"Erdős number: {level}<br>"
            f"Degree: {degree}<br>"
            f"Department: {info.get('department', 'N/A')}<br>"
            f"Gender: {info.get('gender', 'N/A')}<br>"
            f"Title: {info.get('title', 'N/A')}<br>"
            f"Papers: {stats.get('total', 0)}<br>"
            f"Solo: {stats.get('solo', 0)}<br>"
            f"Collaborations: {stats.get('collab', 0)}<br>"
            f"Collab type: {collab_type}<br>"
        )

        if is_highlight_mode and highlight_nodes:
            labels.append(f"{node}\n({level})" if node in highlight_nodes else "")
        else:
            labels.append(f"{node}\n({level})")

        # ---------------- COLOR ----------------
        if color_mode == "collab":
            node_color.append("#7bd389" if score > 0 else "#f4a261" if score < 0 else "#b084cc")

        elif color_mode == "gender":
            node_color.append("blue" if info.get("gender") == "M" else "pink")

        elif color_mode == "dept":
            dept = info.get("department", "Unknown")
            if dept not in dept_colors:
                dept_colors[dept] = color_palette[color_index % len(color_palette)]
                color_index += 1
            node_color.append(dept_colors[dept])

        elif color_mode == "title":
            title = info.get("title", "Unknown")
            if title not in dept_colors:
                dept_colors[title] = color_palette[color_index % len(color_palette)]
                color_index += 1
            node_color.append(dept_colors[title])

        else:
            if node == root_author:
                node_color.append("red")
            elif level == 1:
                node_color.append("#FFF3B0")  # light yellow
            elif level == 2:
                node_color.append("#87CEFA")  # light blue
            elif level == 3:
                node_color.append("#90EE90")  # light green
            else:
                node_color.append("#C0C0C0")  # fallback (external or >3)
            

        node_opacity.append(1.0 if is_highlighted else 0.1)

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=labels,
        textposition="top center",
        hoverinfo="text",
        hovertext=hover_text,
        marker=dict(
            size=18,
            color=node_color,
            opacity=node_opacity,
            line=dict(width=2, color="black")
        )
    )

    fig = go.Figure(data=[edge_trace_normal, edge_trace_highlight, node_trace])

    fig.update_layout(
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False, visible=False),
        showlegend=False,
        hovermode="closest",
        margin=dict(l=20, r=20, t=40, b=20)
    )

    # ---------------- LEGEND LOGIC ----------------
    legend = []

    def legend_item(color, text):
        return html.Div([
            html.Span(style={
                "display": "inline-block",
                "width": "12px",
                "height": "12px",
                "background": color,
                "marginRight": "8px"
            }),
            text
        ])

    if color_mode == "gender":
        legend = [
            legend_item("blue", "Male"),
            legend_item("pink", "Female")
        ]

    elif color_mode == "collab":
        legend = [
            legend_item("#7bd389", "Internal collaboration"),
            legend_item("#f4a261", "External collaboration"),
            legend_item("#b084cc", "Balanced")
        ]

    elif color_mode == "level":
        legend = [
            legend_item("red", "Erdős (0)"),
            legend_item("#FFF3B0", "Level 1"),
            legend_item("#87CEFA", "Level 2"),
            legend_item("#90EE90", "Level 3"),
            legend_item("#C0C0C0", "External")
        ]

    elif color_mode in ["dept", "title"]:
        for key, color in dept_colors.items():
            legend.append(legend_item(color, key))

    return fig, legend