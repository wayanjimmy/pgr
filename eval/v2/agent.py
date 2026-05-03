"""Custom agent runtime for the v2 eval.

Uses the Anthropic API directly with native structured tools.
All public conditions use identical tool schemas; only the backend differs.
"""

import json
import time
import sys
from dataclasses import dataclass, field, asdict
from typing import Any

import anthropic

from tools import TOOL_DEFINITIONS, SYSTEM_PROMPT
from backends import baseline as baseline_backend
from backends import pgr_backend
from backends import fff_backend


@dataclass
class ToolCall:
    """Record of a single tool call."""
    tool_name: str
    tool_input: dict
    output: str
    output_tokens: int
    duration_ms: float
    turn_number: int


@dataclass
class TaskResult:
    """Full result for a single task run."""
    task_id: str
    repo: str
    task_type: str
    condition: str
    prompt: str
    answer: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    total_tool_calls: int = 0
    total_turns: int = 0
    wall_clock_ms: float = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_output_tokens: int = 0
    total_cost_usd: float = 0
    first_call_tool: str = ""
    first_call_produced_file: bool = False
    retry_count: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tool_calls"] = [asdict(tc) for tc in self.tool_calls]
        return d


def dispatch_tool(tool_name: str, tool_input: dict, repo_root: str, condition: str) -> str:
    """Dispatch a tool call to the appropriate backend."""
    if condition == "pgr":
        backend = pgr_backend
    elif condition == "fff":
        backend = fff_backend
    else:
        backend = baseline_backend

    if tool_name == "search_code":
        return backend.search_code(
            repo_root=repo_root,
            query=tool_input["query"],
            path_glob=tool_input.get("path_glob", ""),
            file_type=tool_input.get("file_type", ""),
            max_files=tool_input.get("max_files", 10),
            max_matches_per_file=tool_input.get("max_matches_per_file", 3),
            context_before=tool_input.get("context_before", 2),
            context_after=tool_input.get("context_after", 2),
        )
    if tool_name == "read_code":
        return backend.read_code(
            repo_root=repo_root,
            path=tool_input["path"],
            start_line=tool_input.get("start_line", 1),
            end_line=tool_input.get("end_line", 0),
            max_lines=tool_input.get("max_lines", 80),
        )
    if tool_name == "find_files":
        return backend.find_files(
            repo_root=repo_root,
            pattern=tool_input.get("pattern", ""),
            glob=tool_input.get("glob", ""),
            file_type=tool_input.get("file_type", ""),
            max_results=tool_input.get("max_results", 50),
        )
    if tool_name == "list_dir":
        return backend.list_dir(
            repo_root=repo_root,
            path=tool_input.get("path", "."),
            recursive=tool_input.get("recursive", False),
            max_results=tool_input.get("max_results", 100),
        )
    return f"Unknown tool: {tool_name}"


def run_task(
    task_id: str,
    repo: str,
    task_type: str,
    prompt: str,
    repo_root: str,
    condition: str,
    model: str = "claude-sonnet-4-6",
    max_turns: int = 20,
) -> TaskResult:
    """Run a single task through the agent loop."""
    client = anthropic.Anthropic()
    result = TaskResult(
        task_id=task_id,
        repo=repo,
        task_type=task_type,
        condition=condition,
        prompt=prompt,
    )

    messages = [{"role": "user", "content": prompt}]
    turn = 0
    start_time = time.time()
    last_tool_calls = {}

    try:
        while turn < max_turns:
            turn += 1
            response = None
            for attempt in range(5):
                try:
                    response = client.messages.create(
                        model=model,
                        max_tokens=4096,
                        system=SYSTEM_PROMPT,
                        tools=TOOL_DEFINITIONS,
                        messages=messages,
                    )
                    break
                except anthropic.AuthenticationError as e:
                    result.error = f"Auth error: set ANTHROPIC_API_KEY env var. {e}"
                    break
                except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                    status = getattr(e, "status_code", 0)
                    if status in (429, 529, 500, 502, 503) and attempt < 4:
                        wait = (2 ** attempt) * 2
                        print(f"    [{task_id}] API {status}, retrying in {wait}s (attempt {attempt+1}/5)", flush=True)
                        time.sleep(wait)
                        continue
                    result.error = str(e)
                    break

            if response is None:
                if not result.error:
                    result.error = "No response after retries"
                break

            result.input_tokens += response.usage.input_tokens
            result.output_tokens += response.usage.output_tokens

            assistant_content = response.content
            tool_use_blocks = [b for b in assistant_content if b.type == "tool_use"]
            text_blocks = [b for b in assistant_content if b.type == "text"]

            if not tool_use_blocks:
                result.answer = "\n".join(b.text for b in text_blocks)
                break

            messages.append({"role": "assistant", "content": assistant_content})
            tool_results = []
            for tool_block in tool_use_blocks:
                tool_name = tool_block.name
                tool_input = tool_block.input

                input_key = json.dumps(tool_input, sort_keys=True)
                if tool_name in last_tool_calls and last_tool_calls[tool_name] == input_key:
                    result.retry_count += 1
                last_tool_calls[tool_name] = input_key

                tool_start = time.time()
                output = dispatch_tool(tool_name, tool_input, repo_root, condition)
                tool_duration = (time.time() - tool_start) * 1000

                tc = ToolCall(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    output=output[:500],
                    output_tokens=len(output),
                    duration_ms=tool_duration,
                    turn_number=turn,
                )
                result.tool_calls.append(tc)
                result.total_tool_calls += 1
                result.tool_output_tokens += len(output)

                if not result.first_call_tool:
                    result.first_call_tool = tool_name
                    if tool_name in ("search_code", "find_files") and any(
                        ext in output for ext in [".go", ".py", ".ts", ".js", ".rs", ".java"]
                    ):
                        result.first_call_produced_file = True

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": output,
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        result.total_turns = turn
        result.wall_clock_ms = (time.time() - start_time) * 1000
        result.total_cost_usd = (
            result.input_tokens * 3.0 / 1_000_000
            + result.output_tokens * 15.0 / 1_000_000
        )

    except Exception as e:
        result.error = str(e)
        result.wall_clock_ms = (time.time() - start_time) * 1000

    return result


def main():
    if len(sys.argv) != 6:
        print("Usage: python agent.py TASK_ID REPO TASK_TYPE PROMPT_FILE CONDITION")
        sys.exit(1)

    task_id = sys.argv[1]
    repo = sys.argv[2]
    task_type = sys.argv[3]
    prompt_file = sys.argv[4]
    condition = sys.argv[5]

    with open(prompt_file) as f:
        payload = json.load(f)

    result = run_task(
        task_id=task_id,
        repo=repo,
        task_type=task_type,
        prompt=payload["prompt"],
        repo_root=payload["repo_root"],
        condition=condition,
        model=payload.get("model", "claude-sonnet-4-6"),
        max_turns=payload.get("max_turns", 20),
    )

    print(json.dumps(result.to_dict()))


if __name__ == "__main__":
    main()
