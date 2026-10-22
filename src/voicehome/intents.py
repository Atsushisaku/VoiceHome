"""定型命令の判定。ここで拾えたものは LLM を通さずに実行する。"""

import re
from dataclasses import dataclass

AIRCON = r"(エアコン|冷房|暖房|除湿|ドライ|クーラー)"
# 「暖房つけて」はモードも指定している。電源だけ入れると前回のモード（冷房など）でついてしまう
AIRCON_MODES = {"cool": r"(冷房|クーラー)", "warm": r"暖房", "dry": r"(除湿|ドライ)"}
LIGHT = r"(照明|電気|でんき|ライト|明かり|あかり)"
ON = r"(つけ|付け|点け|オン|入れ|いれ|起動)"
OFF = r"(消し|けし|消す|けす|切っ|切る|きっ|オフ|止め|とめ|停止)"
# 否定・保留（「つけないで」「そのままで」）は定型にしない
NEGATION = r"(ない|なく|まま|待って)"
# 定型とみなす長さの上限。長い文は条件や文脈を含みやすいので LLM に回す
MAX_LEN = 15


@dataclass
class Intent:
    action: str  # "aircon_on" / "aircon_off" / "light_on" / "light_off"
    mode: str | None = None  # aircon_on のときの運転モード（cool / warm / dry）。None なら前回のまま


def match(text: str) -> Intent | None:
    t = re.sub(r"[\s、。！!？?]", "", text)
    if not t or len(t) > MAX_LEN or re.search(NEGATION, t):
        return None
    aircon, light = bool(re.search(AIRCON, t)), bool(re.search(LIGHT, t))
    if aircon == light:  # どちらでもない／両方（「エアコンと電気消して」等）は LLM に回す
        return None
    on, off = bool(re.search(ON, t)), bool(re.search(OFF, t))
    if on == off:  # どちらもない／両方ある（「つけて消して」等）は曖昧
        return None
    if light:
        return Intent(f"light_{'on' if on else 'off'}")
    if off:
        return Intent("aircon_off")
    modes = [m for m, pattern in AIRCON_MODES.items() if re.search(pattern, t)]
    if len(modes) > 1 or re.search(r"\d|度", t):  # モードが複数・温度指定つきは LLM に任せる
        return None
    return Intent("aircon_on", modes[0] if modes else None)
