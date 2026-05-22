"""
title: ReAct Agent (qwen3-8b)
author: agent-stack
version: 0.1.0
description: ReAct loop sobre OVMS/qwen3-8b con tools search/fetch/calc.
"""

import ast
import operator
import re
from typing import Generator, Iterator, List, Union

import httpx
from pydantic import BaseModel, Field


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_calc(expr: str) -> str:
    def _e(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](_e(n.left), _e(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](_e(n.operand))
        raise ValueError("op not allowed")

    try:
        return str(_e(ast.parse(expr, mode="eval").body))
    except Exception as e:
        return f"error: {e}"


SYSTEM_PROMPT = """/no_think
You are a ReAct agent. You solve the user's question using tools.

TOOLS:
- search(query): SearXNG web search, returns top 5 snippets.
- fetch(url): HTTP GET on http(s) URL, returns up to 4k chars of cleaned text.
- calc(expression): safe arithmetic eval. Examples: (3+4)*2**3, 365.25*40.

OUTPUT FORMAT — every turn you emit EXACTLY ONE of these two shapes. No prose around it. No <think> tags. No commentary.

Shape A (you need a tool):
Thought: <one short sentence>
Action: <tool_name>
Action Input: <single-line input>

Shape B (you have the final answer):
Thought: <one short sentence>
Final Answer: <answer for the user, in their language>

RULES:
- Stop immediately after `Action Input:` (don't write "Observation:" yourself, the system fills it).
- One Action per turn.
- If a tool fails, try a different approach next turn.
- If the question doesn't need tools, go straight to Shape B.

EXAMPLE:

Question: How old would someone born on 1963-02-17 be on 2026-05-22?

Thought: I'll compute the difference in days and divide by 365.25.
Action: calc
Action Input: (2026 - 1963) - (1 if (5, 22) < (2, 17) else 0)

Observation: 63

Thought: 63 years.
Final Answer: 63 años.

END EXAMPLE.
"""

ACTION_RE = re.compile(
    r"Action:\s*(\w+)\s*\n\s*Action Input:\s*(.+?)(?:\n\s*Observation:|\n\s*Thought:|\Z)",
    re.S,
)
FINAL_RE = re.compile(r"Final Answer:\s*(.+)$", re.S)
THINK_RE = re.compile(r"<think>.*?</think>\s*", re.S)


def _strip_thinking(text: str) -> str:
    """Qwen3 may emit <think>...</think> blocks even with /no_think; drop them
    so the ReAct parser sees clean output."""
    return THINK_RE.sub("", text).strip()


class Pipeline:
    class Valves(BaseModel):
        OVMS_URL: str = Field(default="http://ovms:8000/v3")
        MODEL: str = Field(default="qwen3-8b")
        SEARXNG_URL: str = Field(default="http://searxng:8080/search")
        MAX_ITERATIONS: int = Field(default=6)
        TEMPERATURE: float = Field(default=0.0)
        MAX_TOKENS_PER_STEP: int = Field(default=512)
        FETCH_MAX_CHARS: int = Field(default=4000)
        SHOW_TRACE: bool = Field(
            default=True,
            description="Si True, muestra cada Thought/Action/Observation en el chat",
        )

    def __init__(self):
        self.name = "react-agent"
        self.valves = self.Valves()

    async def on_startup(self):
        pass

    async def on_shutdown(self):
        pass

    # --- Tools ---

    def _tool_search(self, query: str) -> str:
        try:
            r = httpx.get(
                self.valves.SEARXNG_URL,
                params={"q": query, "format": "json"},
                timeout=15,
            )
            r.raise_for_status()
            results = r.json().get("results", [])[:5]
            if not results:
                return "no results"
            return "\n".join(
                f"- {x.get('title', '')[:120]}: {x.get('content', '')[:200]} ({x.get('url', '')})"
                for x in results
            )
        except Exception as e:
            return f"error: {e}"

    def _tool_fetch(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            return "error: solo http(s)"
        try:
            r = httpx.get(
                url,
                timeout=15,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 ReActBot/0.1"},
            )
            r.raise_for_status()
            text = re.sub(r"<[^>]+>", " ", r.text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[: self.valves.FETCH_MAX_CHARS]
        except Exception as e:
            return f"error: {e}"

    def _run_tool(self, name: str, arg: str) -> str:
        name = name.strip().lower()
        arg = arg.strip().strip('"').strip("'").strip("`")
        if name == "search":
            return self._tool_search(arg)
        if name == "fetch":
            return self._tool_fetch(arg)
        if name == "calc":
            return _safe_calc(arg)
        return f"error: tool desconocida '{name}'"

    # --- LLM ---

    def _call_llm(self, messages: list) -> str:
        with httpx.Client(timeout=180) as c:
            r = c.post(
                f"{self.valves.OVMS_URL}/chat/completions",
                json={
                    "model": self.valves.MODEL,
                    "messages": messages,
                    "temperature": self.valves.TEMPERATURE,
                    "max_tokens": self.valves.MAX_TOKENS_PER_STEP,
                    "stop": ["Observation:", "\nObservation:"],
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

    # --- ReAct loop ---

    def pipe(
        self,
        user_message: str,
        model_id: str,
        messages: List[dict],
        body: dict,
    ) -> Union[str, Generator, Iterator]:
        scratch = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        if self.valves.SHOW_TRACE:
            yield "**ReAct agent** _(trace visible — desactivable en valves)_\n"

        for step in range(self.valves.MAX_ITERATIONS):
            try:
                raw = self._call_llm(scratch).strip()
            except Exception as e:
                yield f"\n\n_LLM error: {e}_"
                return

            out = _strip_thinking(raw)

            if self.valves.SHOW_TRACE:
                yield f"\n```\n{out}\n```\n"

            final = FINAL_RE.search(out)
            if final:
                answer = final.group(1).strip()
                if self.valves.SHOW_TRACE:
                    yield f"\n---\n\n{answer}"
                else:
                    yield answer
                return

            action = ACTION_RE.search(out)
            if not action:
                if not self.valves.SHOW_TRACE:
                    yield out
                else:
                    yield "\n_(salida no parseable, devolviendo tal cual)_\n"
                return

            tool, arg = action.group(1), action.group(2).strip()
            if self.valves.SHOW_TRACE:
                preview = arg if len(arg) < 80 else arg[:77] + "..."
                yield f"\n_→ `{tool}({preview})`_\n"

            obs = self._run_tool(tool, arg)
            if self.valves.SHOW_TRACE:
                preview = obs if len(obs) < 600 else obs[:597] + "..."
                yield f"\n```\nObservation: {preview}\n```\n"

            scratch.append({"role": "assistant", "content": out})
            scratch.append({"role": "user", "content": f"Observation: {obs}"})

        yield "\n\n_Máx. iteraciones alcanzado sin Final Answer._"
