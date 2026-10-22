"""remo の操作を MCP ツールとして出すサーバー（stdio）。claude -p 経路（LLM_BACKEND=cli）で使う。

claude -p には Bash を渡さずこのツールだけを許可する。ツールの中身は tools.py と共通。
"""

from mcp.server.mcpserver import MCPServer

from . import tools

server = MCPServer("remo")


@server.tool()
def list_appliances() -> str:
    """登録済みの家電と現在の状態を返す。状態は Remo が最後に送った操作の記録で、実測ではない。"""
    return tools.run("list_appliances", {})[0]


@server.tool()
def set_aircon_power(on: bool, name: str | None = None) -> str:
    """エアコンの電源を入れる（on=true）か切る（on=false）。複数台あるときは name にニックネームを渡す。"""
    return tools.run("set_aircon_power", {"on": on, "name": name})[0]


@server.tool()
def set_light(button: str, name: str | None = None) -> str:
    """照明のボタンを押す。on / off / on-100（全灯）/ on-favorite / night（常夜灯）/ bright-up / bright-down /
    colortemp-up（白っぽく）/ colortemp-down（暖かい色に）。"""
    return tools.run("set_light", {"button": button, "name": name})[0]


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
