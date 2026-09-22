from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import shlex
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

import requests


@dataclass
class ManagedProcess:
    name: str
    process: subprocess.Popen
    log_file: TextIO
    persistent: bool = False


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log_line(prefix: str, line: str, sink: TextIO, print_to_console: bool = True) -> None:
    clean = line.rstrip("\n")
    msg = f"[{_timestamp()}] [{prefix}] {clean}"
    sink.write(msg + "\n")
    sink.flush()
    if print_to_console:
        print(msg, flush=True)


def _stream_output(prefix: str, stream: TextIO, combined_log: TextIO, proc_log: TextIO) -> None:
    for line in iter(stream.readline, ""):
        _log_line(prefix, line, combined_log)
        proc_log.write(f"[{_timestamp()}] {line.rstrip()}\n")
        proc_log.flush()


def _wait_http_ok(url: str, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code < 500:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def _build_comfyui_command(env: dict[str, str], workspace: Path) -> tuple[list[str], Path]:
    return _build_comfyui_command_with_mode(env, workspace, auto_discover=False)


def _clean_env_value(raw: str) -> str:
    value = (raw or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _resolve_comfyui_workdir(workdir_raw: str, workspace: Path) -> Path:
    workdir = Path(workdir_raw)
    if not workdir.is_absolute():
        workdir = (workspace / workdir).resolve()
    return workdir


def _candidate_comfyui_dirs(workspace: Path, env: dict[str, str]) -> list[Path]:
    custom_raw = env.get("COMFYUI_AUTO_WORKDIRS", "").strip()
    candidates: list[Path] = []
    if custom_raw:
        for raw in custom_raw.split(os.pathsep):
            raw = raw.strip()
            if not raw:
                continue
            p = _resolve_comfyui_workdir(raw, workspace)
            candidates.append(p)

    home = Path.home()
    defaults = [
        workspace / "ComfyUI",
        workspace.parent / "ComfyUI",
        home / "ComfyUI",
        home / "Documents" / "ComfyUI",
    ]
    if os.name == "nt":
        defaults.extend([Path("C:/ComfyUI"), Path("D:/ComfyUI")])
    else:
        defaults.extend([Path("/opt/ComfyUI"), Path("/usr/local/ComfyUI")])

    seen: set[str] = set()
    ordered: list[Path] = []
    for p in candidates + defaults:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(p)
    return ordered


def _discover_comfyui_workdir(workspace: Path, env: dict[str, str]) -> Path | None:
    for candidate in _candidate_comfyui_dirs(workspace, env):
        if (candidate / "main.py").exists():
            return candidate
    return None


def _infer_comfyui_host_port(comfyui_url: str) -> tuple[str, str]:
    parsed = urlparse(comfyui_url or "")
    host = parsed.hostname or "127.0.0.1"
    port = str(parsed.port or 8188)
    return host, port


def _is_configured_comfyui_port_busy(comfyui_url: str) -> bool:
    if not comfyui_url.strip():
        return False
    host, port_raw = _infer_comfyui_host_port(comfyui_url)
    try:
        port = int(port_raw)
    except ValueError:
        return False
    return _is_port_in_use(host, port)


def _build_default_comfyui_command(workdir: Path, comfyui_url: str) -> list[str]:
    main_py = workdir / "main.py"
    if not main_py.exists():
        raise RuntimeError(f"ComfyUI main.py not found in '{workdir}'.")

    host, port = _infer_comfyui_host_port(comfyui_url)
    embedded_python = workdir / "python_embeded" / "python.exe"
    if embedded_python.exists():
        python_cmd = str(embedded_python)
    else:
        python_cmd = "python"

    return [python_cmd, "main.py", "--listen", host, "--port", port]


def _build_comfyui_command_with_mode(
    env: dict[str, str],
    workspace: Path,
    auto_discover: bool,
) -> tuple[list[str], Path]:
    cmd_raw = env.get("COMFYUI_START_COMMAND", "").strip()
    workdir_raw = env.get("COMFYUI_WORKDIR", "").strip()

    if workdir_raw:
        workdir = _resolve_comfyui_workdir(workdir_raw, workspace)
    elif auto_discover:
        discovered = _discover_comfyui_workdir(workspace, env)
        if not discovered:
            tried = [str(p) for p in _candidate_comfyui_dirs(workspace, env)]
            raise RuntimeError(
                "--with-comfyui-auto could not locate ComfyUI. "
                "Set COMFYUI_WORKDIR or COMFYUI_AUTO_WORKDIRS in .env. "
                f"Tried: {', '.join(tried)}"
            )
        workdir = discovered
    else:
        workdir = workspace

    if cmd_raw:
        command = shlex.split(cmd_raw, posix=False)
    elif auto_discover:
        command = _build_default_comfyui_command(workdir, env.get("COMFYUI_URL", ""))
    else:
        raise RuntimeError(
            "--with-comfyui requested but COMFYUI_START_COMMAND is not set. "
            "Set it in .env (example: COMFYUI_START_COMMAND=python main.py --listen 127.0.0.1 --port 8188)."
        )

    return command, workdir


def _compute_comfyui_fingerprint(env: dict[str, str], command: list[str], workdir: Path) -> str:
    model_paths = _extract_comfyui_model_paths(env, command, workdir)
    tracked = {
        "command": [str(part).strip() for part in command],
        "workdir": str(workdir.resolve()),
        "model_paths": model_paths,
    }
    payload = json.dumps(tracked, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_path_candidate(raw: str, workdir: Path) -> str:
    candidate = _clean_env_value(raw)
    if not candidate:
        return ""
    if "://" in candidate:
        return candidate
    path_obj = Path(candidate)
    if not path_obj.is_absolute():
        path_obj = (workdir / path_obj)
    try:
        return str(path_obj.resolve())
    except OSError:
        return str(path_obj)


def _iter_split_paths(raw: str) -> list[str]:
    cleaned = _clean_env_value(raw)
    if not cleaned:
        return []
    parts = [p.strip() for p in cleaned.split(os.pathsep)]
    return [p for p in parts if p]


def _extract_comfyui_model_paths(env: dict[str, str], command: list[str], workdir: Path) -> list[str]:
    resolved: set[str] = set()
    env_keys = (
        "COMFYUI_MODEL_PATHS",
        "COMFYUI_EXTRA_MODEL_PATHS_CONFIG",
        "COMFYUI_EXTRA_MODEL_PATHS",
    )
    for key in env_keys:
        for token in _iter_split_paths(env.get(key, "")):
            normalized = _normalize_path_candidate(token, workdir)
            if normalized:
                resolved.add(normalized)

    command_flags = (
        "--extra-model-paths-config",
        "--extra-model-path",
        "--model-path",
    )
    for index, arg in enumerate(command):
        for flag in command_flags:
            value = ""
            if arg == flag and index + 1 < len(command):
                value = command[index + 1]
            elif arg.startswith(f"{flag}="):
                value = arg.split("=", 1)[1]
            if value:
                normalized = _normalize_path_candidate(value, workdir)
                if normalized:
                    resolved.add(normalized)

    return sorted(resolved)


def _read_comfyui_state(state_file: Path) -> dict | None:
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_comfyui_state(state_file: Path, payload: dict) -> None:
    state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate_pid(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


def _is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _pick_free_port(host: str, preferred_port: int, max_scan: int = 20) -> int:
    if not _is_port_in_use(host, preferred_port):
        return preferred_port
    for offset in range(1, max_scan + 1):
        candidate = preferred_port + offset
        if not _is_port_in_use(host, candidate):
            return candidate
    raise RuntimeError(f"Could not find free port near {preferred_port}")


def _start_process(
    name: str,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    combined_log: TextIO,
    log_dir: Path,
    persistent: bool = False,
) -> ManagedProcess:
    log_path = log_dir / f"{name}.log"
    proc_log = log_path.open("a", encoding="utf-8")

    _log_line("launcher", f"starting {name}: {' '.join(cmd)}", combined_log)

    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert process.stdout is not None
    thread = threading.Thread(
        target=_stream_output,
        args=(name, process.stdout, combined_log, proc_log),
        daemon=True,
    )
    thread.start()

    return ManagedProcess(name=name, process=process, log_file=proc_log, persistent=persistent)


def _stop_process(managed: ManagedProcess, combined_log: TextIO, timeout_seconds: int = 10) -> None:
    if managed.persistent:
        _log_line("launcher", f"leaving persistent process running: {managed.name} (pid={managed.process.pid})", combined_log)
        managed.log_file.close()
        return
    proc = managed.process
    if proc.poll() is not None:
        managed.log_file.close()
        return

    _log_line("launcher", f"stopping {managed.name}", combined_log)
    proc.terminate()
    try:
        proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _log_line("launcher", f"force killing {managed.name}", combined_log)
        proc.kill()
        proc.wait(timeout=timeout_seconds)

    managed.log_file.close()


def _install_requirements(workspace: Path, combined_log: TextIO) -> None:
    cmd = [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
    _log_line("launcher", "installing dependencies from requirements.txt", combined_log)
    result = subprocess.run(cmd, cwd=str(workspace), capture_output=True, text=True)
    if result.stdout:
        for line in result.stdout.splitlines():
            _log_line("pip", line, combined_log)
    if result.stderr:
        for line in result.stderr.splitlines():
            _log_line("pip", line, combined_log)
    if result.returncode != 0:
        raise RuntimeError("Dependency installation failed")


def _load_dotenv(workspace: Path, env: dict[str, str]) -> None:
    env_path = workspace / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        env.setdefault(key.strip(), _clean_env_value(value))


def _env_int(env: dict[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except ValueError:
        return default


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Single-command launcher for FastAPI backend + Streamlit UI with full logs."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--ui-port", type=int, default=8501)
    parser.add_argument("--startup-timeout", type=int, default=120)
    parser.add_argument("--smoke-test", action="store_true", help="Start services, validate endpoints, then stop.")
    parser.add_argument("--install", action="store_true", help="Run pip install -r requirements.txt before startup.")
    parser.add_argument("--api-reload", action="store_true", help="Enable uvicorn auto-reload.")
    parser.add_argument("--with-worker", action="store_true", help="Start RQ worker when Redis is configured.")
    parser.add_argument("--with-comfyui", action="store_true", help="Start ComfyUI automatically when COMFYUI_START_COMMAND is configured.")
    parser.add_argument(
        "--with-comfyui-auto",
        action="store_true",
        help="Auto-discover common ComfyUI paths and start it even if COMFYUI_WORKDIR/COMFYUI_START_COMMAND are missing.",
    )
    args = parser.parse_args()

    workspace = Path(__file__).resolve().parent
    logs_dir = workspace / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    combined_log_path = logs_dir / f"launcher_{run_id}.log"

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    _load_dotenv(workspace, env)
    comfyui_timeout = _env_int(env, "COMFYUI_STARTUP_TIMEOUT", max(180, args.startup_timeout))

    managed: list[ManagedProcess] = []
    stop_event = threading.Event()

    with combined_log_path.open("a", encoding="utf-8") as combined_log:
        _log_line("launcher", f"logs file: {combined_log_path}", combined_log)
        _log_line("launcher", f"workspace: {workspace}", combined_log)

        if args.install:
            _install_requirements(workspace, combined_log)

        api_port = _pick_free_port(args.host, args.api_port)
        ui_port = _pick_free_port(args.host, args.ui_port)
        if api_port != args.api_port:
            _log_line("launcher", f"port {args.api_port} busy, using API port {api_port}", combined_log)
        if ui_port != args.ui_port:
            _log_line("launcher", f"port {args.ui_port} busy, using UI port {ui_port}", combined_log)

        env["API_BASE_URL"] = f"http://{args.host}:{api_port}"

        api_cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            args.host,
            "--port",
            str(api_port),
        ]
        if args.api_reload:
            api_cmd.append("--reload")

        ui_cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "streamlit_app.py",
            "--server.port",
            str(ui_port),
            "--server.address",
            args.host,
        ]

        worker_cmd = [
            sys.executable,
            "-m",
            "rq",
            "worker",
            env.get("QUEUE_NAME", "ai_movie_maker"),
        ]

        def _shutdown_handler(signum: int, frame: object) -> None:
            del frame
            if not stop_event.is_set():
                _log_line("launcher", f"received signal {signum}, shutting down", combined_log)
                stop_event.set()

        signal.signal(signal.SIGINT, _shutdown_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _shutdown_handler)

        try:
            comfyui_url = env.get("COMFYUI_URL", "").strip()
            start_comfyui = args.with_comfyui or args.with_comfyui_auto
            if start_comfyui:
                try:
                    comfy_cmd, comfy_workdir = _build_comfyui_command_with_mode(
                        env,
                        workspace,
                        auto_discover=args.with_comfyui_auto,
                    )
                    comfy_fingerprint = _compute_comfyui_fingerprint(env, comfy_cmd, comfy_workdir)
                    state_file = logs_dir / "comfyui_state.json"
                    existing_state = _read_comfyui_state(state_file)
                    comfy_health_url = f"{comfyui_url.rstrip('/')}/system_stats" if comfyui_url else ""
                    comfy_healthy = bool(comfy_health_url and _wait_http_ok(comfy_health_url, 3))

                    if existing_state:
                        existing_pid = int(existing_state.get("pid", -1))
                        existing_fp = existing_state.get("fingerprint", "")
                        if existing_pid > 0 and _is_process_alive(existing_pid):
                            if existing_fp == comfy_fingerprint:
                                if comfyui_url and _wait_http_ok(f"{comfyui_url.rstrip('/')}/system_stats", 10):
                                    _log_line("launcher", f"Reusing running ComfyUI pid={existing_pid}", combined_log)
                                else:
                                    _log_line(
                                        "launcher",
                                        f"ComfyUI pid={existing_pid} not healthy yet; waiting up to {comfyui_timeout}s",
                                        combined_log,
                                    )
                                    if not (comfyui_url and _wait_http_ok(f"{comfyui_url.rstrip('/')}/system_stats", comfyui_timeout)):
                                        _log_line("launcher", f"Restarting stale ComfyUI pid={existing_pid}", combined_log)
                                        _terminate_pid(existing_pid)
                                        existing_state = None
                                    else:
                                        _log_line("launcher", f"ComfyUI ready: {comfyui_url}", combined_log)
                            else:
                                _log_line("launcher", f"ComfyUI config changed; recycling pid={existing_pid}", combined_log)
                                _terminate_pid(existing_pid)
                                existing_state = None
                                comfy_healthy = False
                        elif existing_pid <= 0 and comfy_healthy:
                            if not existing_fp or existing_fp == comfy_fingerprint:
                                _log_line("launcher", "Reusing external ComfyUI instance detected at configured URL", combined_log)
                            else:
                                _log_line(
                                    "launcher",
                                    "ComfyUI config changed, but the running instance is unmanaged. "
                                    "Continuing with the active ComfyUI process; restart that process to apply new command/model-path settings.",
                                    combined_log,
                                )
                        else:
                            existing_state = None

                    if not existing_state:
                        if comfy_healthy:
                            _log_line(
                                "launcher",
                                "Detected healthy ComfyUI already running; skipping new ComfyUI start",
                                combined_log,
                            )
                            _write_comfyui_state(
                                state_file,
                                {
                                    "pid": 0,
                                    "fingerprint": comfy_fingerprint,
                                    "workdir": str(comfy_workdir),
                                    "command": comfy_cmd,
                                    "external": True,
                                    "updated_at": _timestamp(),
                                },
                            )
                        elif _is_configured_comfyui_port_busy(comfyui_url):
                            _log_line(
                                "launcher",
                                "ComfyUI port is already in use; waiting for health endpoint before deciding to restart",
                                combined_log,
                            )
                            if comfyui_url and _wait_http_ok(f"{comfyui_url.rstrip('/')}/system_stats", comfyui_timeout):
                                _log_line("launcher", f"ComfyUI ready: {comfyui_url}", combined_log)
                                _write_comfyui_state(
                                    state_file,
                                    {
                                        "pid": 0,
                                        "fingerprint": comfy_fingerprint,
                                        "workdir": str(comfy_workdir),
                                        "command": comfy_cmd,
                                        "external": True,
                                        "updated_at": _timestamp(),
                                    },
                                )
                            else:
                                raise RuntimeError(
                                    "ComfyUI port is in use but the health endpoint did not become ready. "
                                    "Close the conflicting process or update COMFYUI_URL/COMFYUI_START_COMMAND."
                                )
                        else:
                            _log_line("launcher", f"ComfyUI workdir: {comfy_workdir}", combined_log)
                            comfy_proc = _start_process(
                                "comfyui",
                                comfy_cmd,
                                comfy_workdir,
                                env,
                                combined_log,
                                logs_dir,
                                persistent=True,
                            )
                            managed.append(comfy_proc)
                            _write_comfyui_state(
                                state_file,
                                {
                                    "pid": comfy_proc.process.pid,
                                    "fingerprint": comfy_fingerprint,
                                    "workdir": str(comfy_workdir),
                                    "command": comfy_cmd,
                                    "updated_at": _timestamp(),
                                },
                            )

                    if comfyui_url:
                        _log_line("launcher", f"waiting for ComfyUI at {comfyui_url}", combined_log)
                        comfy_ready = _wait_http_ok(f"{comfyui_url.rstrip('/')}/system_stats", comfyui_timeout)
                        if not comfy_ready:
                            _log_line(
                                "launcher",
                                f"startup failed: ComfyUI did not become reachable in {comfyui_timeout}s",
                                combined_log,
                            )
                            return 1
                        _log_line("launcher", f"ComfyUI ready: {comfyui_url}", combined_log)
                    else:
                        _log_line(
                            "launcher",
                            "COMFYUI_URL is empty; ComfyUI process started but health check skipped",
                            combined_log,
                        )
                except RuntimeError as exc:
                    if args.with_comfyui_auto:
                        _log_line(
                            "launcher",
                            f"ComfyUI auto-start skipped: {exc}",
                            combined_log,
                        )
                        _log_line(
                            "launcher",
                            "Continuing without ComfyUI. Basic mode remains available; Cinematic mode will stay blocked until ComfyUI is reachable.",
                            combined_log,
                        )
                    else:
                        raise

            managed.append(_start_process("api", api_cmd, workspace, env, combined_log, logs_dir))
            managed.append(_start_process("ui", ui_cmd, workspace, env, combined_log, logs_dir))
            if args.with_worker and env.get("REDIS_URL"):
                managed.append(_start_process("worker", worker_cmd, workspace, env, combined_log, logs_dir))

            api_url = f"http://{args.host}:{api_port}/health"
            ui_url = f"http://{args.host}:{ui_port}"
            _log_line("launcher", f"waiting for API at {api_url}", combined_log)
            api_ready = _wait_http_ok(api_url, args.startup_timeout)
            _log_line("launcher", f"waiting for UI at {ui_url}", combined_log)
            ui_ready = _wait_http_ok(ui_url, args.startup_timeout)

            if not api_ready or not ui_ready:
                _log_line("launcher", "startup failed: API or UI not reachable in time", combined_log)
                return 1

            _log_line("launcher", f"API ready: {api_url}", combined_log)
            _log_line("launcher", f"UI ready: {ui_url}", combined_log)

            if args.smoke_test:
                _log_line("launcher", "smoke-test successful, stopping services", combined_log)
                return 0

            _log_line("launcher", "services running. Press Ctrl+C to stop.", combined_log)
            while not stop_event.is_set():
                for proc in managed:
                    if proc.process.poll() is not None:
                        _log_line("launcher", f"{proc.name} exited with code {proc.process.returncode}", combined_log)
                        stop_event.set()
                        break
                time.sleep(1)

            return 0
        finally:
            for proc in reversed(managed):
                _stop_process(proc, combined_log)
            _log_line("launcher", "shutdown complete", combined_log)


if __name__ == "__main__":
    raise SystemExit(main())

