"""Nature Remo の家電を操作する CLI。

    remo list
    remo aircon on|off [--name ニックネーム] [--dry-run]

トークンは環境変数または .env の NATURE_REMO_TOKEN から読む。
環境変数 REMO_DRY_RUN=1 のときは --dry-run と同じ扱い（claude -p 経由の試験用）。
"""

import argparse
import os
import sys
from dataclasses import dataclass

import requests
from dotenv import load_dotenv

API_BASE = "https://api.nature.global/1"
TIMEOUT_SEC = 10


class RemoError(Exception):
    pass


@dataclass
class Appliance:
    id: str
    type: str
    nickname: str
    raw: dict


def _token() -> str:
    load_dotenv()
    token = os.environ.get("NATURE_REMO_TOKEN", "").strip()
    if not token:
        raise RemoError("NATURE_REMO_TOKEN が未設定です（.env に書いてください）")
    return token


def _request(method: str, path: str, data: dict | None = None) -> dict | list:
    resp = requests.request(
        method,
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {_token()}"},
        data=data,
        timeout=TIMEOUT_SEC,
    )
    if resp.status_code != 200:
        raise RemoError(f"Remo API {method} {path} が {resp.status_code} を返しました: {resp.text[:200]}")
    return resp.json()


def list_appliances() -> list[Appliance]:
    return [
        Appliance(id=a["id"], type=a["type"], nickname=a.get("nickname", ""), raw=a)
        for a in _request("GET", "/appliances")
    ]


def find_aircon(name: str | None = None) -> Appliance:
    aircons = [a for a in list_appliances() if a.type == "AC"]
    if name:
        aircons = [a for a in aircons if name in a.nickname]
    if not aircons:
        raise RemoError("該当するエアコンが見つかりません" + (f"（--name {name}）" if name else ""))
    if len(aircons) > 1:
        names = "、".join(a.nickname for a in aircons)
        raise RemoError(f"エアコンが複数あります。--name で指定してください: {names}")
    return aircons[0]


def set_aircon_power(on: bool, name: str | None = None, dry_run: bool = False) -> str:
    """エアコンの電源を切り替え、結果の一文を返す。"""
    ac = find_aircon(name)
    # Remo API の仕様: button が空文字なら電源 ON、"power-off" なら OFF
    data = {"button": "" if on else "power-off"}
    action = "つけ" if on else "消し"
    if dry_run:
        return f"[dry-run] {ac.nickname} を{action}ます（POST /appliances/{ac.id}/aircon_settings {data}）"
    _request("POST", f"/appliances/{ac.id}/aircon_settings", data=data)
    return f"{ac.nickname} を{action}ました"


def describe(a: Appliance) -> str:
    line = f"{a.type:<6} {a.nickname}  ({a.id})"
    if a.type == "AC" and a.raw.get("settings"):
        s = a.raw["settings"]
        power = "OFF" if s.get("button") == "power-off" else "ON"
        line += f"  電源={power} モード={s.get('mode')} 温度={s.get('temp')}"
    return line


def main(argv: list[str] | None = None) -> int:
    # Windows のコンソールやパイプ越しでも日本語を化けさせない（--help より前に設定する）
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="remo", description="Nature Remo の家電操作")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="登録済みの家電を一覧表示")
    ac = sub.add_parser("aircon", help="エアコンの電源操作")
    ac.add_argument("power", choices=["on", "off"])
    ac.add_argument("--name", help="エアコンのニックネーム（部分一致）。複数台あるときに指定")
    ac.add_argument("--dry-run", action="store_true", help="送信せずに内容だけ表示")
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            for a in list_appliances():
                print(describe(a))
        else:
            dry_run = args.dry_run or os.environ.get("REMO_DRY_RUN") == "1"
            print(set_aircon_power(args.power == "on", args.name, dry_run))
    except (RemoError, requests.RequestException) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
