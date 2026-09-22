from app.agents.graph import build_graph


def test_graph_produces_scenes() -> None:
    graph = build_graph()
    state = graph.invoke(
        {
            "script_text": "Scene one starts.\n\nScene two follows.",
            "language": "en",
            "scenes": [],
            "style": "",
        }
    )
    assert len(state["scenes"]) >= 2
    assert state["scenes"][0]["image_prompt"]

