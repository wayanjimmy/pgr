"""pgr backend: uses the pgr MCP binary for all tools.

`pgr` is stateless: no local index and no daemon. Each tool call goes through
one long-lived MCP stdio process per repo root, which matches the public
benchmark setup.
"""

import json
import os
import subprocess
import threading
from pathlib import Path

DEFAULT_PGR_BIN = Path(__file__).resolve().parents[3] / "target" / "release" / "pgr"
PGR_BIN = os.environ.get("PGR_BIN", str(DEFAULT_PGR_BIN))

_processes: dict[str, tuple[subprocess.Popen, threading.Lock, list[int]]] = {}
_pool_lock = threading.Lock()


def _send_raw(proc, msg: str):
    proc.stdin.write(msg + "\n")
    proc.stdin.flush()


def _read_line(proc) -> str:
    line = proc.stdout.readline()
    return line.strip() if line else ""


def _get_process(repo_root: str):
    with _pool_lock:
        if repo_root in _processes:
            proc, lock, counter = _processes[repo_root]
            if proc.poll() is None:
                return proc, lock, counter

        bin_path = os.path.abspath(PGR_BIN)
        if not os.path.isfile(bin_path):
            raise FileNotFoundError(f"pgr binary not found at {bin_path}. Run: cargo build --release")

        proc = subprocess.Popen(
            [bin_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=repo_root,
        )
        lock = threading.Lock()
        counter = [10]

        _send_raw(proc, json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pgr-eval", "version": "0.1"},
            },
        }))
        _read_line(proc)
        _send_raw(proc, json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }))

        _processes[repo_root] = (proc, lock, counter)
        return proc, lock, counter


def _call_tool(repo_root: str, tool_name: str, arguments: dict) -> str:
    proc, lock, counter = _get_process(repo_root)

    with lock:
        req_id = counter[0]
        counter[0] += 1
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        })
        _send_raw(proc, request)
        raw = _read_line(proc)

    if not raw:
        return "pgr: no response"

    try:
        resp = json.loads(raw)
    except json.JSONDecodeError:
        return f"pgr: invalid JSON: {raw[:200]}"

    result = resp.get("result", {})
    content = result.get("content", [])
    texts = [block["text"] for block in content if block.get("type") == "text"]
    return "\n".join(texts) if texts else "No results."


def search_code(
    repo_root: str,
    query: str,
    path_glob: str = "",
    file_type: str = "",
    max_files: int = 10,
    max_matches_per_file: int = 3,
    context_before: int = 2,
    context_after: int = 2,
) -> str:
    args = {"query": query}
    if path_glob:
        args["path_glob"] = path_glob
    if file_type:
        args["file_type"] = file_type
    if max_files != 10:
        args["max_files"] = max_files
    if max_matches_per_file != 3:
        args["max_matches_per_file"] = max_matches_per_file
    return _call_tool(repo_root, "search_code", args)


def read_code(
    repo_root: str,
    path: str,
    start_line: int = 1,
    end_line: int = 0,
    max_lines: int = 80,
) -> str:
    args = {"path": path}
    if start_line != 1:
        args["start_line"] = start_line
    if end_line != 0:
        args["end_line"] = end_line
    if max_lines != 80:
        args["max_lines"] = max_lines
    return _call_tool(repo_root, "read_code", args)


def find_files(
    repo_root: str,
    pattern: str = "",
    glob: str = "",
    file_type: str = "",
    max_results: int = 50,
) -> str:
    args = {}
    if pattern:
        args["pattern"] = pattern
    if glob:
        args["glob"] = glob
    if file_type:
        args["file_type"] = file_type
    if max_results != 50:
        args["max_results"] = max_results
    return _call_tool(repo_root, "find_files", args)


def list_dir(
    repo_root: str,
    path: str = ".",
    recursive: bool = False,
    max_results: int = 100,
) -> str:
    args = {"path": path}
    if recursive:
        args["recursive"] = True
    if max_results != 100:
        args["max_results"] = max_results
    return _call_tool(repo_root, "list_dir", args)


def cleanup():
    with _pool_lock:
        for proc, _, _ in _processes.values():
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        _processes.clear()
