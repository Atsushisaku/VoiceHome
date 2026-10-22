"""remo の操作を MCP ツールとして出すサーバー（stdio）。

claude -p には Bash を渡さずこのツールだけを許可する。トークンはこのプロセスが .env から読み、
LLM のコンテキストには出ない。環境変数 REMO_DRY_RUN=1 なら送信しない。
"""

import os

import requests
from mcp.server.mcpserver import MCPServer

from . import remo

server = MCPServer("remo")


def _dry_run() -> bool:
    return os.environ.get("REMO_DRY_RUN") == "1"


@server.tool()
def list_appliances() -> str:
    """登録済みの家電と、エアコンの現在の設定（電源・モード・温度）を返す。"""
    try:
        return "\n".join(remo.describe(a) for a in remo.list_appliances())
    except (remo.RemoError, requests.RequestException) as e:
        return f"エラー: {e}"


@server.tool()
def set_aircon_power(on: bool, name: str | None = None) -> str:
    """エアコンの電源を入れる（on=true）か切る（on=false）。複数台あるときは name にニックネームを渡す。"""
    try:
        return remo.set_aircon_power(on, name, dry_run=_dry_run())
    except (remo.RemoError, requests.RequestException) as e:
        return f"エラー: {e}"


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
