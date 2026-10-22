"""LLM に渡す家電操作ツールの定義と実行。API 経路と MCP サーバーの両方から使う。

REMO_DRY_RUN=1 のときは送信しない。トークンはこのプロセスが .env から読み、LLM には渡らない。
"""

import os

import requests

from . import remo

TOOLS = [
    {
        "name": "list_appliances",
        "description": "登録済みの家電と現在の状態を返す。エアコンは電源・モード・温度と選べるモード・温度範囲、照明は電源と使えるボタン。"
        "状態は Remo が最後に送った操作の記録で、実測ではない。",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "set_aircon",
        "description": "エアコンをつけ、運転モードと設定温度を変える（cool=冷房、warm=暖房、dry=除湿）。"
        "省いた項目は今の設定のまま。温度を上げ下げするときは list_appliances で今の温度を見てから値を決める。",
        "input_schema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["cool", "warm", "dry"]},
                "temperature": {"type": "integer", "description": "設定温度（℃）。除湿では無視される"},
                "name": {"type": "string", "description": "複数台あるときのニックネーム。1 台なら省略"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "set_aircon_power",
        "description": "エアコンの電源だけを入れる（on=true）か切る（on=false）。モード・温度は前回のまま。",
        "input_schema": {
            "type": "object",
            "properties": {
                "on": {"type": "boolean"},
                "name": {"type": "string", "description": "複数台あるときのニックネーム。1 台なら省略"},
            },
            "required": ["on"],
            "additionalProperties": False,
        },
    },
    {
        "name": "set_light",
        "description": "照明のボタンを押す。on=つける、off=消す、on-100=全灯、on-favorite=お気に入り、night=常夜灯、"
        "bright-up / bright-down=明るく / 暗く、colortemp-up / colortemp-down=白っぽく / 暖かい色に。",
        "input_schema": {
            "type": "object",
            "properties": {
                "button": {"type": "string", "enum": list(remo.LIGHT_BUTTON_LABELS)},
                "name": {"type": "string", "description": "複数台あるときのニックネーム。1 台なら省略"},
            },
            "required": ["button"],
            "additionalProperties": False,
        },
    },
]


def run(name: str, args: dict) -> tuple[str, bool]:
    """ツールを実行し、(結果の文, エラーか) を返す。"""
    dry_run = os.environ.get("REMO_DRY_RUN") == "1"
    try:
        if name == "list_appliances":
            return "\n".join(remo.describe(a) for a in remo.list_appliances()), False
        if name == "set_aircon":
            return remo.set_aircon(args.get("mode"), args.get("temperature"), args.get("name"), dry_run=dry_run), False
        if name == "set_aircon_power":
            return remo.set_aircon_power(args["on"], args.get("name"), dry_run=dry_run), False
        if name == "set_light":
            return remo.set_light(args["button"], args.get("name"), dry_run=dry_run), False
        return f"不明なツール: {name}", True
    except (remo.RemoError, requests.RequestException, KeyError) as e:
        return f"エラー: {e}", True
