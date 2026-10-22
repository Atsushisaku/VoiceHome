"""定型で拾えなかった指示を `claude -p` に渡す。"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "haiku"
TIMEOUT_SEC = 90

# remo を MCP サーバーとして起動する。いま動いている venv の Python をそのまま使う
MCP_CONFIG = json.dumps({
    "mcpServers": {
        "remo": {"command": sys.executable, "args": ["-m", "voicehome.remo_mcp"]},
    },
})

SYSTEM_PROMPT = """あなたは家庭用の音声アシスタントです。返答はそのまま音声で読み上げられます。

家電は remo のツールで操作する（list_appliances で一覧と状態、set_aircon_power でエアコンの電源）。

規則:
- 家電の操作が必要なときだけツールを使う。状態がわからなければ先に list_appliances で確かめる
- 操作したあとに list_appliances で確かめ直さない（表示される状態は最後に送った操作の記録で、実測ではない）
- ツールの結果が「[dry-run]」で始まるのは試験中で、操作は成功として扱う
- できないことは「できません」と短く伝える
- 返答は日本語の話し言葉で 1 文、30 文字以内。記号・箇条書き・Markdown は使わない
"""


@dataclass
class LlmResult:
    text: str
    duration_ms: int
    cost_usd: float
    is_error: bool


def ask(utterance: str, model: str | None = None) -> LlmResult:
    cmd = [
        "claude", "-p", utterance,
        "--output-format", "json",
        "--model", model or os.environ.get("LLM_MODEL", DEFAULT_MODEL),
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
    proc = subprocess.run(
        cmd, cwd=PROJECT_DIR, capture_output=True, text=True, encoding="utf-8",
        stdin=subprocess.DEVNULL, timeout=TIMEOUT_SEC,
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
