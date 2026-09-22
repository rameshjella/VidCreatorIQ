import os
import platform
from pathlib import Path

import requests
import streamlit as st

def _default_api_base() -> str:
    if os.getenv("API_BASE_URL"):
        return os.getenv("API_BASE_URL", "http://localhost:8000")
    try:
        return st.secrets.get("api_base", "http://localhost:8000")
    except Exception:
        return "http://localhost:8000"


API_BASE = _default_api_base()


def _get_json(url: str, timeout: int = 30):
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _safe_get_json(url: str, timeout: int = 30):
    try:
        return _get_json(url, timeout), None
    except requests.RequestException as exc:
        return None, str(exc)


def _safe_request(method: str, url: str, timeout: int = 30, **kwargs):
    try:
        response = requests.request(method, url, timeout=timeout, **kwargs)
        return response, None
    except requests.RequestException as exc:
        return None, str(exc)


def _ffmpeg_fix_snippet() -> tuple[str, str]:
    system = platform.system().lower()
    if system == "windows":
        return (
            "powershell",
            "winget install -e --id Gyan.FFmpeg\n"
            "$ffmpeg = Get-ChildItem \"$env:LOCALAPPDATA\\Microsoft\\WinGet\\Packages\" -Filter ffmpeg.exe -Recurse | Select-Object -First 1 -ExpandProperty FullName\n"
            "if (-not $ffmpeg) { throw 'ffmpeg.exe not found in WinGet packages' }\n"
            "$ffmpegDir = Split-Path $ffmpeg -Parent\n"
            "[Environment]::SetEnvironmentVariable(\"FFMPEG_BIN\", $ffmpeg, \"User\")\n"
            "$current = [Environment]::GetEnvironmentVariable(\"Path\", \"User\")\n"
            "if ($current -notlike \"*$ffmpegDir*\") { [Environment]::SetEnvironmentVariable(\"Path\", \"$current;$ffmpegDir\", \"User\") }\n"
            "# Also set .env -> FFMPEG_BIN=<full path to ffmpeg.exe>",
        )
    if system == "darwin":
        return (
            "bash",
            "brew install ffmpeg\n"
            "echo 'FFMPEG_BIN=ffmpeg' >> .env",
        )
    return (
        "bash",
        "sudo apt-get update\n"
        "sudo apt-get install -y ffmpeg\n"
        "echo 'FFMPEG_BIN=ffmpeg' >> .env",
    )


def _comfyui_fix_snippet() -> tuple[str, str]:
    system = platform.system().lower()
    if system == "windows":
        return (
            "powershell",
            "# Example ComfyUI start command\n"
            "Set-Location \"C:\\Path\\To\\ComfyUI\"\n"
            "python .\\main.py --listen 127.0.0.1 --port 8188\n"
            "# Or use embedded python:\n"
            ".\\python_embeded\\python.exe .\\main.py --listen 127.0.0.1 --port 8188",
        )
    return (
        "bash",
        "cd /path/to/ComfyUI\n"
        "python3 ./main.py --listen 127.0.0.1 --port 8188",
    )


def _upsert_env_values(env_path: Path, updates: dict[str, str]) -> list[str]:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated_lines: list[str] = []
    seen: set[str] = set()

    for line in lines:
        raw = line.rstrip("\n")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw:
            updated_lines.append(raw)
            continue

        key, _, _ = raw.partition("=")
        env_key = key.strip()
        if env_key in updates:
            updated_lines.append(f"{env_key}={updates[env_key]}")
            seen.add(env_key)
        else:
            updated_lines.append(raw)

    for key, value in updates.items():
        if key not in seen:
            updated_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")
    return sorted(updates.keys())


def _build_suggested_env_updates(findings: list[dict]) -> dict[str, str]:
    updates: dict[str, str] = {}
    for item in findings:
        dependency = str(item.get("dependency", "")).lower()
        issue = str(item.get("issue", "")).lower()
        missing = item.get("missing", {}) if isinstance(item.get("missing", {}), dict) else {}

        if dependency == "comfyui":
            if "not configured" in issue:
                if not str(missing.get("comfyui_url", "")).strip():
                    updates["COMFYUI_URL"] = "http://127.0.0.1:8188"
            if "connection failed" in issue:
                updates.setdefault("COMFYUI_START_COMMAND", "python main.py --listen 127.0.0.1 --port 8188")
                updates.setdefault("COMFYUI_WORKDIR", "<SET_ME_COMFYUI_FOLDER>")

        if dependency == "piper" and "not configured" in issue:
            updates.setdefault("PIPER_EXECUTABLE", "<SET_ME_PIPER_EXE>")
            updates.setdefault("PIPER_MODEL_PATH", "<SET_ME_PIPER_MODEL_ONNX>")

    return updates


st.set_page_config(page_title="AI Movie Maker", layout="wide")
st.title("AI Movie Maker")
st.caption("Timeline-driven script to narrated movie workflow")

ready_for_generation = False
ready_for_cinematic = False
dependency_hint = "Dependency status unavailable. Check API and /health/dependencies endpoint."
cinematic_dependency_hint = "Cinematic mode requires ComfyUI + FFmpeg readiness."
show_ffmpeg_fix = False
ffmpeg_fix_lang = "bash"
ffmpeg_fix_cmd = ""
show_comfyui_fix = False
comfyui_fix_lang = "bash"
comfyui_fix_cmd = ""

with st.sidebar:
    st.subheader("Connection")
    api_base = st.text_input("API base URL", value=API_BASE)
    auto_refresh = st.toggle("Auto refresh job", value=True)
    refresh_secs = st.slider("Refresh interval (sec)", min_value=2, max_value=15, value=4)

    health, health_err = _safe_get_json(f"{api_base}/health", timeout=5)
    if health and health.get("status") == "ok":
        st.success("API reachable")
    else:
        st.error("API unreachable")
        if health_err:
            st.caption(health_err)

    st.subheader("Dependencies")
    deps_payload, deps_err = _safe_get_json(f"{api_base}/health/dependencies", timeout=5)
    if deps_payload and "dependencies" in deps_payload:
        deps = deps_payload["dependencies"]
        ready_for_generation = bool(deps_payload.get("ready_for_generation", False))
        ready_for_cinematic = bool(deps_payload.get("ready_for_cinematic", False))
        ffmpeg_dep = deps.get("ffmpeg", {})
        comfyui_dep = deps.get("comfyui", {})
        for dep_name in ["ffmpeg", "comfyui", "piper"]:
            dep = deps.get(dep_name, {})
            ready = bool(dep.get("ready", False))
            icon = "OK" if ready else "MISSING"
            st.write(f"- {icon} `{dep_name}`: {dep.get('detail', '')}")
        if not deps_payload.get("ready_for_generation", False):
            st.warning("Generation is blocked until required dependencies are ready.")
            configured = ffmpeg_dep.get("configured", "")
            resolved = ffmpeg_dep.get("resolved_path", "")
            if not resolved:
                show_ffmpeg_fix = True
                ffmpeg_fix_lang, ffmpeg_fix_cmd = _ffmpeg_fix_snippet()
                if configured:
                    dependency_hint = (
                        f"FFmpeg is not available. `FFMPEG_BIN` is set to `{configured}` but was not found. "
                        "Set `FFMPEG_BIN` to a valid executable path or add ffmpeg to PATH."
                    )
                else:
                    dependency_hint = (
                        "FFmpeg is not configured. Set `FFMPEG_BIN` in `.env` to `ffmpeg` or full path "
                        "(example: `C:\\ffmpeg\\bin\\ffmpeg.exe`)."
                    )
            else:
                dependency_hint = "Dependencies are not ready. Check sidebar details and fix missing items."
        else:
            dependency_hint = "FFmpeg dependency is ready."

        if not ready_for_cinematic:
            show_comfyui_fix = True
            comfyui_fix_lang, comfyui_fix_cmd = _comfyui_fix_snippet()
            comfy_detail = comfyui_dep.get("detail", "ComfyUI is not ready.")
            cinematic_dependency_hint = (
                "Cinematic mode requires ComfyUI + FFmpeg readiness. "
                f"ComfyUI detail: {comfy_detail}"
            )
        else:
            cinematic_dependency_hint = "Cinematic dependencies are ready."
    else:
        st.caption(f"Dependency status unavailable: {deps_err}")

    with st.expander("Detailed Fixes", expanded=False):
        doctor_payload, doctor_err = _safe_get_json(f"{api_base}/health/dependency-doctor", timeout=5)
        if doctor_payload and "findings" in doctor_payload:
            findings = doctor_payload.get("findings", [])
            summary = doctor_payload.get("summary", {})
            checkpoint_health = doctor_payload.get("comfyui_checkpoints", {})
            st.caption(
                f"Issues: {summary.get('issue_count', 0)} | Blocking: {summary.get('blocking_issues', False)}"
            )
            if isinstance(checkpoint_health, dict):
                st.markdown("**ComfyUI checkpoints**")
                st.caption(
                    f"Count: {checkpoint_health.get('checkpoint_count', 0)} | "
                    f"Reachable: {checkpoint_health.get('reachable', False)}"
                )
                sample_names = checkpoint_health.get("sample_checkpoint_names", [])
                if sample_names:
                    st.code("\n".join(sample_names), language="text")
                else:
                    st.warning(checkpoint_health.get("detail", "No checkpoint names returned."))
            if not findings:
                st.success("No dependency issues found.")
            for item in findings:
                st.markdown(f"**{item.get('dependency', 'dependency')}** - {item.get('severity', 'info')} - {item.get('issue', '')}")
                missing = item.get("missing", {})
                if missing:
                    st.code(str(missing), language="text")
                fixes = item.get("suggested_fixes", [])
                for fix in fixes:
                    st.write(f"- {fix}")

            suggested_updates = _build_suggested_env_updates(findings)
            if suggested_updates:
                if st.button("Apply suggested env fixes", key="apply_env_fixes_request"):
                    st.session_state["pending_env_fix_updates"] = suggested_updates
                    st.session_state["show_env_fix_confirm"] = True

                if st.session_state.get("show_env_fix_confirm"):
                    pending = st.session_state.get("pending_env_fix_updates", {})
                    st.warning("Confirm writing these values to `.env`.")
                    preview = "\n".join([f"{k}={v}" for k, v in pending.items()])
                    st.code(preview or "(nothing to update)", language="bash")

                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Confirm write .env", key="confirm_env_fix_write"):
                            env_path = Path(__file__).resolve().parent / ".env"
                            applied = _upsert_env_values(env_path, pending)
                            st.success(f"Updated `.env`: {', '.join(applied)}")
                            st.session_state["show_env_fix_confirm"] = False
                            st.session_state["pending_env_fix_updates"] = {}
                    with c2:
                        if st.button("Cancel", key="cancel_env_fix_write"):
                            st.session_state["show_env_fix_confirm"] = False
                            st.session_state["pending_env_fix_updates"] = {}
        else:
            st.caption(f"Dependency doctor unavailable: {doctor_err}")

    if show_ffmpeg_fix:
        if st.button("Copy fix command", key="copy_ffmpeg_fix"):
            st.session_state["ffmpeg_fix_cmd"] = ffmpeg_fix_cmd
            st.session_state["ffmpeg_fix_lang"] = ffmpeg_fix_lang
            st.info("Use the copy icon in the code block to copy the command.")
        if st.session_state.get("ffmpeg_fix_cmd"):
            st.code(st.session_state["ffmpeg_fix_cmd"], language=st.session_state.get("ffmpeg_fix_lang", "bash"))

    if show_comfyui_fix:
        if st.button("Copy ComfyUI start command", key="copy_comfyui_fix"):
            st.session_state["comfyui_fix_cmd"] = comfyui_fix_cmd
            st.session_state["comfyui_fix_lang"] = comfyui_fix_lang
            st.info("Use the copy icon in the code block to copy the command.")
        if st.session_state.get("comfyui_fix_cmd"):
            st.code(st.session_state["comfyui_fix_cmd"], language=st.session_state.get("comfyui_fix_lang", "bash"))

top_left, top_right = st.columns([1.1, 1.4])

with top_left:
    st.subheader("1) Script & Project")
    uploaded = st.file_uploader("Upload .txt script", type=["txt"])
    pasted = st.text_area("Or paste script", height=260)
    title = st.text_input("Project title", value="My AI Movie")
    visual_mode = st.radio("Visual Mode", options=["Basic", "Cinematic"], horizontal=True)

    if st.button("Create Project", type="primary"):
        script_text = uploaded.read().decode("utf-8") if uploaded else pasted.strip()
        if len(script_text) < 20:
            st.error("Please provide at least 20 characters.")
        else:
            payload = {"title": title, "script_text": script_text, "language": "en"}
            response, err = _safe_request("POST", f"{api_base}/projects", json=payload, timeout=30)
            if response is not None and response.ok:
                project = response.json()
                st.session_state["project_id"] = project["id"]
                st.success(f"Project #{project['id']} ready")
            else:
                st.error(err or response.text)

    c1, c2 = st.columns(2)
    with c1:
        selected_mode = visual_mode.strip().lower()
        can_generate = ready_for_generation and (selected_mode == "basic" or ready_for_cinematic)
        mode_hint = (
            dependency_hint
            if selected_mode == "basic"
            else cinematic_dependency_hint
        )

        if st.button("Generate Movie", disabled=not can_generate, help=mode_hint):
            project_id = st.session_state.get("project_id")
            if not project_id:
                st.error("Create/select a project first")
            else:
                run_resp, err = _safe_request(
                    "POST",
                    f"{api_base}/projects/{project_id}/run",
                    json={"visual_mode": selected_mode},
                    timeout=30,
                )
                if run_resp is not None and run_resp.ok:
                    payload = run_resp.json()
                    st.session_state["job_id"] = payload["job_id"]
                    st.success(f"Job #{payload['job_id']} queued")
                else:
                    st.error(err or run_resp.text)
        if not can_generate:
            st.warning(mode_hint)
    with c2:
        failed_scene_index = st.number_input("Resume from scene index", min_value=1, value=1, step=1)
        if st.button("Resume Job"):
            job_id = st.session_state.get("job_id")
            if not job_id:
                st.error("No job selected")
            else:
                resume_resp, err = _safe_request(
                    "POST",
                    f"{api_base}/jobs/{job_id}/resume",
                    json={"failed_scene_index": int(failed_scene_index)},
                    timeout=30,
                )
                if resume_resp is not None and resume_resp.ok:
                    st.success("Resume requested")
                else:
                    st.error(err or resume_resp.text)

with top_right:
    st.subheader("2) Job Timeline")
    project_id = st.session_state.get("project_id")
    job_id = st.session_state.get("job_id")

    if job_id:
        try:
            job, job_err = _safe_get_json(f"{api_base}/jobs/{job_id}")
            if not job:
                st.error(f"Failed to fetch job: {job_err}")
                st.stop()
            progress = float(job.get("progress", 0.0))
            st.progress(max(0.0, min(1.0, progress)), text=f"{int(progress * 100)}%")
            st.caption(
                f"Status: {job['status']} | Stage: {job['stage']} | Scenes: {job.get('processed_scenes', 0)}/{job.get('total_scenes', 0)} | Attempts: {job.get('attempts', 0)}"
            )
            st.info(job.get("message", ""))

            events, events_err = _safe_get_json(f"{api_base}/jobs/{job_id}/events")
            if events is None:
                st.warning(f"Failed to load events: {events_err}")
                events = []
            if events:
                st.markdown("**Live Logs**")
                for ev in events[-20:]:
                    ts = ev.get("created_at", "")
                    st.text(f"[{ts}] [{ev['stage']}] {ev['message']}")
            else:
                st.caption("No events yet")
        except Exception as exc:
            st.error(f"Failed to fetch job data: {exc}")
    else:
        st.write("No job selected.")

st.divider()
st.subheader("3) Scene Timeline Editor")

if project_id:
    project_resp, err = _safe_request("GET", f"{api_base}/projects/{project_id}", timeout=30)
    if project_resp is not None and project_resp.ok:
        project = project_resp.json()
        scenes = project.get("scenes", [])
        if scenes:
            st.markdown("**Edit order/duration then click Save Timeline**")
            editor_rows = [
                {
                    "scene_id": scene["id"],
                    "scene_index": scene["scene_index"],
                    "duration_seconds": float(scene.get("duration_seconds", 6.0)),
                    "title": scene["title"],
                }
                for scene in scenes
            ]
            edited = st.data_editor(
                editor_rows,
                key="timeline_editor",
                use_container_width=True,
                hide_index=True,
                disabled=["scene_id", "title"],
                column_config={
                    "scene_index": st.column_config.NumberColumn("Order", min_value=1, step=1),
                    "duration_seconds": st.column_config.NumberColumn("Duration (s)", min_value=0.1, step=0.5),
                },
            )
            if st.button("Save Timeline"):
                edited_rows = edited.to_dict("records") if hasattr(edited, "to_dict") else list(edited)
                payload = {
                    "scenes": [
                        {
                            "scene_id": int(row["scene_id"]),
                            "scene_index": int(row["scene_index"]),
                            "duration_seconds": float(row["duration_seconds"]),
                        }
                        for row in edited_rows
                    ]
                }
                save_resp, save_err = _safe_request("PATCH", f"{api_base}/projects/{project_id}/scenes", json=payload, timeout=30)
                if save_resp is not None and save_resp.ok:
                    st.success("Timeline updated")
                    st.rerun()
                else:
                    st.error(save_err or save_resp.text)

            cols = st.columns(len(scenes) if len(scenes) <= 6 else 6)
            for i, scene in enumerate(scenes):
                with cols[i % len(cols)]:
                    label = f"S{scene['scene_index']}"
                    complete = "video_path" in scene and bool(scene.get("video_path"))
                    st.metric(label=label, value=scene["title"][:18], delta="done" if complete else "pending")

            for scene in scenes:
                with st.expander(f"Scene {scene['scene_index']}: {scene['title']}"):
                    st.write(scene["script_chunk"])
                    st.caption(scene["image_prompt"])
                    if scene.get("image_path") and Path(scene["image_path"]).exists():
                        st.image(scene["image_path"], use_column_width=True)
                    if st.button(f"Regenerate Scene {scene['scene_index']}", key=f"regen-{scene['id']}"):
                        rg, rg_err = _safe_request(
                            "POST",
                            f"{api_base}/projects/{project_id}/scenes/regenerate",
                            json={"scene_id": scene["id"]},
                            timeout=120,
                        )
                        if rg is not None and rg.ok:
                            st.success("Scene regenerated")
                        else:
                            st.error(rg_err or rg.text)
                    if scene.get("video_path") and Path(scene["video_path"]).exists():
                        st.video(scene["video_path"])
        else:
            st.caption("Scenes will appear after first generation run")

        dl, dl_err = _safe_request("GET", f"{api_base}/projects/{project_id}/download", timeout=30)
        if dl is not None and dl.ok:
            st.download_button("Download Final MP4", data=dl.content, file_name="ai_movie.mp4", mime="video/mp4")
        elif dl_err:
            st.caption(f"Download unavailable: {dl_err}")
    else:
        st.error(err or project_resp.text)
else:
    st.caption("Create a project to open timeline editor")

if auto_refresh and st.session_state.get("job_id"):
    import time

    time.sleep(refresh_secs)
    st.rerun()

