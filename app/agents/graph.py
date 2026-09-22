from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.services.ollama_service import OllamaService


class PipelineState(TypedDict):
    script_text: str
    language: str
    scenes: list[dict]
    style: str


def _naive_scene_split(script_text: str) -> list[str]:
    chunks = [c.strip() for c in script_text.split("\n\n") if c.strip()]
    if chunks:
        return chunks
    sentences = [s.strip() for s in script_text.split(".") if s.strip()]
    merged: list[str] = []
    current = []
    for sentence in sentences:
        current.append(sentence + ".")
        if len(" ".join(current)) > 280:
            merged.append(" ".join(current))
            current = []
    if current:
        merged.append(" ".join(current))
    return merged[:40]


class DirectorAgent:
    def __init__(self):
        self.ollama = OllamaService()

    def __call__(self, state: PipelineState) -> PipelineState:
        chunks = _naive_scene_split(state["script_text"])
        scenes: list[dict] = []

        if self.ollama.is_available():
            prompt = (
                "You are a film director. Convert the script into JSON with this schema: "
                "{\"style\": string, \"scenes\": [{\"title\": string, \"description\": string, "
                "\"image_prompt\": string, \"duration_seconds\": number, \"script_chunk\": string}]}. "
                f"Script:\n{state['script_text']}"
            )
            try:
                data = self.ollama.generate_json(prompt)
                llm_scenes = data.get("scenes", [])
                for i, sc in enumerate(llm_scenes, start=1):
                    scenes.append(
                        {
                            "scene_index": i,
                            "title": sc.get("title", f"Scene {i}"),
                            "description": sc.get("description", ""),
                            "image_prompt": sc.get("image_prompt", "cinematic still"),
                            "duration_seconds": float(sc.get("duration_seconds", 6.0)),
                            "script_chunk": sc.get("script_chunk", chunks[min(i - 1, len(chunks) - 1)]),
                        }
                    )
                state["style"] = data.get("style", "cinematic")
            except Exception:
                scenes = []

        if not scenes:
            state["style"] = "cinematic dramatic"
            for i, chunk in enumerate(chunks, start=1):
                scenes.append(
                    {
                        "scene_index": i,
                        "title": f"Scene {i}",
                        "description": chunk,
                        "image_prompt": f"cinematic frame, {chunk[:180]}",
                        "duration_seconds": 6.0,
                        "script_chunk": chunk,
                    }
                )

        state["scenes"] = scenes
        return state


class StoryboardAgent:
    def __call__(self, state: PipelineState) -> PipelineState:
        # This node exists so prompt refinement can evolve independently from director decisions.
        for scene in state["scenes"]:
            scene["image_prompt"] = f"{scene['image_prompt']}, style: {state.get('style', 'cinematic')}"
        return state


class NarratorAgent:
    def __call__(self, state: PipelineState) -> PipelineState:
        return state


class VideographerAgent:
    def __call__(self, state: PipelineState) -> PipelineState:
        return state


class EditorAgent:
    def __call__(self, state: PipelineState) -> PipelineState:
        return state


def build_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("director", DirectorAgent())
    graph.add_node("storyboard", StoryboardAgent())
    graph.add_node("videographer", VideographerAgent())
    graph.add_node("narrator", NarratorAgent())
    graph.add_node("editor", EditorAgent())

    graph.set_entry_point("director")
    graph.add_edge("director", "storyboard")
    graph.add_edge("storyboard", "videographer")
    graph.add_edge("videographer", "narrator")
    graph.add_edge("narrator", "editor")
    graph.add_edge("editor", END)

    return graph.compile()

