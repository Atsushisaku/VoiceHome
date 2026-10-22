"""定型で拾えなかった指示を LLM に渡す。

LLM_BACKEND=api（既定）: Claude API を直接呼ぶ。ANTHROPIC_API_KEY が必要
LLM_BACKEND=cli        : `claude -p`（サブスク枠）。remo は MCP サーバー経由

聞き返し（「エアコンをつけましょうか？」→「うん」）が通じるよう、直近 FOLLOWUP_SEC 秒の会話を覚えておく。
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import tools

PROJECT_DIR = Path(__file__).resolve().parents[2]
# 最後のやりとりからこの秒数を過ぎたら、会話を忘れて新しく始める
FOLLOWUP_SEC = 60
# 1 回の発話で許すツール呼び出しの往復数（暴走止め）
MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT = """あなたは家庭用の音声アシスタントです。返答はそのまま音声で読み上げられます。
家電はツールで操作する（list_appliances で一覧と状態、set_aircon_power でエアコン、set_light で照明）。

規則:
- 何をどうするかが明確な指示（「照明消して」「エアコンつけて」）なら、そのまま操作する
- 感想や遠回しな希望（「暑い」「ちょっと暗いね」「寝る準備して」）では操作しない。何をするかを 1 つ短く提案して聞き返す（例: エアコンをつけましょうか？）
- 直前の聞き返しに同意されたら（「うん」「お願い」）提案どおり操作し、断られたら何もしない
- 状態がわからなければ先に list_appliances で確かめる。操作したあとに確かめ直さない（状態は送信記録で実測ではない）
- ツールの結果が「[dry-run]」で始まるのは試験中で、操作は成功として扱う
- できないことは「できません」と短く伝える
- 返答は日本語の話し言葉で 1 文、30 文字以内。記号・箇条書き・Markdown は使わない
"""


@dataclass
class LlmResult:
    text: str
    duration_ms: int
    cost_usd: float  # cli のみ。api は 0（トークン数は usage を見る）
    is_error: bool


class Conversation:
    """直近の会話を保ったまま LLM に問い合わせる。"""

    def __init__(self, backend: str | None = None):
        self.backend = backend or os.environ.get("LLM_BACKEND", "api")
        if self.backend == "api":
            import anthropic

            self.client = anthropic.Anthropic()
        self.messages: list[dict] = []  # api 用（tool_use / thinking ブロックも含めて追記のみ）
        self.transcript: list[tuple[str, str]] = []  # cli 用（発話と返答の文字列）
        self.last_at = 0.0

    def reset(self) -> None:
        self.messages.clear()
        self.transcript.clear()

    def ask(self, utterance: str) -> LlmResult:
        if time.monotonic() - self.last_at > FOLLOWUP_SEC:
            self.reset()
        result = self._ask_api(utterance) if self.backend == "api" else self._ask_cli(utterance)
        self.last_at = time.monotonic()
        if result.is_error:
            self.reset()  # 途中で壊れた会話を次に持ち越さない
        return result

    def _ask_api(self, utterance: str) -> LlmResult:
        import anthropic

        model = os.environ.get("LLM_MODEL", "claude-opus-5-5")
        # 音声の短い対話なので思考は浅くてよい。遅延を優先する
        effort = os.environ.get("LLM_EFFORT", "low")
        extra = {}
        if model in ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"):
            # 安全側の判定で断られたとき、サーバー側で別モデルに切り替えて続けてもらう
            extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        t0 = time.perf_counter()
        self.messages.append({"role": "user", "content": utterance})
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                response = self.client.beta.messages.create(
                    model=model,
                    max_tokens=4000,
                    system=SYSTEM_PROMPT,
                    tools=tools.TOOLS,
                    output_config={"effort": effort},
                    messages=self.messages,
                    **extra,
                )
                self.messages.append({"role": "assistant", "content": response.content})
                if response.stop_reason == "refusal":
                    return self._result("その依頼にはお応えできません。", t0, is_error=True)
                tool_uses = [b for b in response.content if b.type == "tool_use"]
                if response.stop_reason != "tool_use" or not tool_uses:
                    text = "".join(b.text for b in response.content if b.type == "text").strip()
                    return self._result(text, t0)
                results = []
                for block in tool_uses:
                    content, is_error = tools.run(block.name, block.input)
                    results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error}
                    )
                self.messages.append({"role": "user", "content": results})
            return self._result("操作が終わりませんでした。", t0, is_error=True)
        except anthropic.AuthenticationError:
            return self._result("API キーが正しくありません。", t0, is_error=True)
        except anthropic.RateLimitError:
            return self._result("混み合っています。少し待ってください。", t0, is_error=True)
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            return self._result(f"LLM の呼び出しに失敗しました。{type(e).__name__}", t0, is_error=True)

    def _result(self, text: str, t0: float, is_error: bool = False) -> LlmResult:
        return LlmResult(text, int((time.perf_counter() - t0) * 1000), 0.0, is_error)

    def _ask_cli(self, utterance: str) -> LlmResult:
        # claude -p は 1 回ごとに独立なので、直前のやりとりを文章で添える
        prompt = utterance
        if self.transcript:
            history = "\n".join(f"利用者: {u}\nあなた: {r}" for u, r in self.transcript)
            prompt = f"直前のやりとり:\n{history}\n\n今の発話: {utterance}"
        result = _run_claude_cli(prompt)
        self.transcript.append((utterance, result.text))
        return result


# remo を MCP サーバーとして起動する。いま動いている venv の Python をそのまま使う
MCP_CONFIG = json.dumps({
    "mcpServers": {
        "remo": {"command": sys.executable, "args": ["-m", "voicehome.remo_mcp"]},
    },
})


def _run_claude_cli(prompt: str) -> LlmResult:
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", os.environ.get("LLM_MODEL", "haiku"),
        "--system-prompt", SYSTEM_PROMPT,
        # 組み込みツール（Bash・Read 等）は一切渡さない。.env を読む手段をなくすため
        "--tools", "",
        "--mcp-config", MCP_CONFIG,
        "--allowedTools", "mcp__remo",
        # 許可リスト外は確認を出さずに拒否する（無人で止まらないように）
        "--permission-mode", "dontAsk",
        "--permission-prompts", "none",
        # ユーザー設定の許可ルールや、remo 以外の MCP を持ち込まない
        "--setting-sources", "project",
        "--strict-mcp-config",
        "--no-session-persistence",
    ]
    # .env の API キーが環境変数に入っていると claude はそちらで課金するので、サブスク枠を使うよう外す
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = subprocess.run(
        cmd, cwd=PROJECT_DIR, capture_output=True, text=True, encoding="utf-8",
        stdin=subprocess.DEVNULL, timeout=90, env=env,
    )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return LlmResult(f"LLM の呼び出しに失敗しました。{proc.stderr.strip()[:200]}", 0, 0.0, True)
    return LlmResult(
        text=data.get("result", ""),
        duration_ms=data.get("duration_ms", 0),
        cost_usd=data.get("total_cost_usd", 0.0),
        is_error=data.get("is_error", False),
    )


def ask(utterance: str) -> LlmResult:
    """会話を持ち越さない 1 回きりの問い合わせ（計測スクリプト用）。"""
    return Conversation().ask(utterance)
