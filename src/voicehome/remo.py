"""Nature Remo の家電を操作する CLI。

    remo list
    remo aircon on|off [--mode cool|warm|dry] [--temp 温度] [--name ニックネーム] [--dry-run]
    remo light on|off|night|... [--name ニックネーム] [--dry-run]

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


def find_one(type_: str, label: str, name: str | None = None) -> Appliance:
    """種類（AC / LIGHT）とニックネームで 1 台に絞る。"""
    found = [a for a in list_appliances() if a.type == type_]
    if name:
        found = [a for a in found if name in a.nickname]
    if not found:
        raise RemoError(f"該当する{label}が見つかりません" + (f"（--name {name}）" if name else ""))
    if len(found) > 1:
        names = "、".join(a.nickname for a in found)
        raise RemoError(f"{label}が複数あります。--name で指定してください: {names}")
    return found[0]


def find_aircon(name: str | None = None) -> Appliance:
    return find_one("AC", "エアコン", name)


AIRCON_MODE_LABELS = {"cool": "冷房", "warm": "暖房", "dry": "除湿", "blow": "送風", "auto": "自動"}


def _aircon_modes(ac: Appliance) -> dict[str, list[str]]:
    """モード → 指定できる温度の一覧（Remo の登録内容）。除湿など温度を持たないモードは ["0"] 等になる。"""
    modes = ac.raw.get("aircon", {}).get("range", {}).get("modes", {})
    return {m: v.get("temp", []) for m, v in modes.items()}


def set_aircon_power(on: bool, name: str | None = None, dry_run: bool = False) -> str:
    """エアコンの電源だけを切り替える（モード・温度は前回のまま）。結果の一文を返す。"""
    if on:
        return set_aircon(name=name, dry_run=dry_run)
    ac = find_aircon(name)
    data = {"button": "power-off"}
    if dry_run:
        return f"[dry-run] {ac.nickname} を消します（POST /appliances/{ac.id}/aircon_settings {data}）"
    _request("POST", f"/appliances/{ac.id}/aircon_settings", data=data)
    return f"{ac.nickname} を消しました"


def set_aircon(
    mode: str | None = None, temp: int | None = None, name: str | None = None, dry_run: bool = False
) -> str:
    """エアコンをつける。mode / temp を省くと今の設定のまま。結果の一文を返す。"""
    ac = find_aircon(name)
    modes = _aircon_modes(ac)
    current = ac.raw.get("settings") or {}
    target = mode or current.get("mode")
    if target not in modes:
        labels = "、".join(AIRCON_MODE_LABELS.get(m, m) for m in modes)
        raise RemoError(f"{ac.nickname} は {AIRCON_MODE_LABELS.get(target, target)} にできません。選べるモード: {labels}")
    temps = modes[target]
    # Remo API の仕様: button が空文字なら電源 ON。モードと温度は IR 信号にまとめて送る
    data = {"button": "", "operation_mode": target}
    if len(temps) <= 1:
        # 除湿など温度の段階がないモード。温度指定は無視する
        data["temperature"] = temps[0] if temps else ""
        detail = AIRCON_MODE_LABELS.get(target, target)
    else:
        if temp is not None:
            value = str(temp)
        elif current.get("temp") in temps:
            value = current["temp"]  # 指定がなければ今の温度を引き継ぐ
        else:
            value = temps[len(temps) // 2]
        if value not in temps:
            raise RemoError(f"{AIRCON_MODE_LABELS.get(target, target)}の温度は {temps[0]}〜{temps[-1]} 度です（指定: {value}）")
        data["temperature"] = value
        detail = f"{AIRCON_MODE_LABELS.get(target, target)} {value}度"
    if dry_run:
        return f"[dry-run] {ac.nickname} を{detail}でつけます（POST /appliances/{ac.id}/aircon_settings {data}）"
    _request("POST", f"/appliances/{ac.id}/aircon_settings", data=data)
    return f"{ac.nickname} を{detail}でつけました"


# 照明のボタン名と、返答に使う言い方。実際に使えるボタンは機器ごとに Remo の登録内容で決まる
LIGHT_BUTTON_LABELS = {
    "on": "つけ",
    "off": "消し",
    "on-100": "全灯にし",
    "on-favorite": "お気に入りの明るさにし",
    "night": "常夜灯にし",
    "bright-up": "明るくし",
    "bright-down": "暗くし",
    "colortemp-up": "白っぽくし",
    "colortemp-down": "暖かい色にし",
}


def set_light(button: str, name: str | None = None, dry_run: bool = False) -> str:
    """照明のボタンを押し、結果の一文を返す。"""
    light = find_one("LIGHT", "照明", name)
    available = [b["name"] for b in light.raw.get("light", {}).get("buttons", [])]
    if button not in available:
        raise RemoError(f"{light.nickname} にボタン {button} はありません。使えるもの: {', '.join(available)}")
    action = LIGHT_BUTTON_LABELS.get(button, f"{button} にし")
    if dry_run:
        return f"[dry-run] {light.nickname} を{action}ます（POST /appliances/{light.id}/light button={button}）"
    _request("POST", f"/appliances/{light.id}/light", data={"button": button})
    return f"{light.nickname} を{action}ました"


def describe(a: Appliance) -> str:
    line = f"{a.type:<6} {a.nickname}  ({a.id})"
    if a.type == "AC" and a.raw.get("settings"):
        s = a.raw["settings"]
        power = "OFF" if s.get("button") == "power-off" else "ON"
        line += f"  電源={power} モード={s.get('mode')} 温度={s.get('temp')}"
        ranges = []
        for m, temps in _aircon_modes(a).items():
            ranges.append(f"{m}({temps[0]}-{temps[-1]})" if len(temps) > 1 else m)
        line += f"  選べるモード={','.join(ranges)}"
    if a.type == "LIGHT" and a.raw.get("light"):
        light = a.raw["light"]
        state = light.get("state", {})
        buttons = ",".join(b["name"] for b in light.get("buttons", []))
        line += f"  電源={state.get('power', '?').upper()} ボタン={buttons}"
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
    ac.add_argument("--mode", choices=list(AIRCON_MODE_LABELS), help="運転モード（on のときだけ）")
    ac.add_argument("--temp", type=int, help="設定温度（on のときだけ）")
    ac.add_argument("--name", help="エアコンのニックネーム（部分一致）。複数台あるときに指定")
    ac.add_argument("--dry-run", action="store_true", help="送信せずに内容だけ表示")
    lt = sub.add_parser("light", help="照明のボタン操作")
    lt.add_argument("button", choices=list(LIGHT_BUTTON_LABELS))
    lt.add_argument("--name", help="照明のニックネーム（部分一致）。複数台あるときに指定")
    lt.add_argument("--dry-run", action="store_true", help="送信せずに内容だけ表示")
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            for a in list_appliances():
                print(describe(a))
        else:
            dry_run = args.dry_run or os.environ.get("REMO_DRY_RUN") == "1"
            if args.command == "aircon" and args.power == "on":
                print(set_aircon(args.mode, args.temp, args.name, dry_run))
            elif args.command == "aircon":
                print(set_aircon_power(False, args.name, dry_run))
            else:
                print(set_light(args.button, args.name, dry_run))
    except (RemoError, requests.RequestException) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
