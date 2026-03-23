from dash import Dash, dcc, html, Input, Output
import networkx as nx
import plotly.graph_objects as go
import sqlite3

from build_graph import build_coauthor_graph_from_db, compute_person_stats

DB_PATH = "./db/erdos.db"

# 🔥 GLOBAL STATE (za toggle)
last_clicked = None


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
                ],
                value="level"
            ),

            html.Div(id="legend-box", style={"marginTop": "20px"})

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
                style={"height": "95vh"},
                clear_on_unhover=True
            )
        ], style={
            "width": "70%",
            "display": "inline-block"
        })
    ])

    # ---------------- CALLBACK ----------------
    @app.callback(
        Output("selected-node", "data"),
        Input("graph", "clickData"),
        prevent_initial_call=True
    )
    def store_clicked_node(clickData):
        if not clickData or "points" not in clickData:
            return None

        point = clickData["points"][0]

        if "text" not in point:
            return None

        node = point["text"].split("\n")[0]

        return node
    
    @app.callback(
        Output("graph", "figure"),
        Output("title", "children"),
        Output("legend-box", "children"),
        Input("author-dropdown", "value"),
        Input("color-mode", "value"),
        Input("selected-node", "data"),
        prevent_initial_call=True
    )
    def update_graph(author, color_mode, selected_node):

        if not author:
            return go.Figure(), "Select author", ""

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

        G = nx.Graph()
        for a, coauthors in graph.items():
            for c in coauthors:
                G.add_edge(a, c)

        pos = nx.spring_layout(G, k=1.2, iterations=80, seed=42)

        highlight_nodes = None

        if selected_node and selected_node in G:
            highlight_nodes = set(G.neighbors(selected_node)) | {selected_node}

        fig, legend = make_figure(
            G, pos, levels, author,
            person_info, stats_map,
            color_mode,
            highlight_nodes
        )

        return fig, f"Erdős Graph – {author}", legend
    app.run(debug=True)


# ---------------- FIGURE ----------------

def make_figure(G, pos, levels, root_author, person_info, stats_map, color_mode, highlight_nodes=None):

    edge_x, edge_y = [], []

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

        # EXTERNAL
        if node.startswith("EXT::"):
            real_name = node.split("::")[-1]
            hover_text.append(f"<b>{real_name}</b><br>External collaborator")
            node_color.append("gray")
            node_opacity.append(0.4)
            labels.append("")
            continue

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

        labels.append(f"{node}\n({level})")

        # COLOR MODE
        if color_mode == "gender":
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
        margin=dict(l=20, r=20, t=40, b=20),
        hoverlabel=dict(
            bgcolor="rgba(255,255,255,0.4)",
            bordercolor="rgba(0,0,0,0.3)",
            font_size=12,
            font_color="black"
        )
    )

    # -------- LEGEND --------
    legend = []
    for dept, color in dept_colors.items():
        legend.append(html.Div([
            html.Span(style={
                "display": "inline-block",
                "width": "12px",
                "height": "12px",
                "background": color,
                "marginRight": "8px"
            }),
            dept
        ]))

    return fig, legend