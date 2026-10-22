"""キー押下で録音 → STT → 定型命令 or LLM → TTS で返答。

    uv run voicehome              # 音声で使う
    uv run voicehome --text       # キーボード入力で試す（マイクと STT を使わない）
    uv run voicehome --dry-run    # 家電に送信しない

LLM は LLM_BACKEND=api（既定、Claude API）か cli（claude -p）。
"""

import argparse
import os
import sys
import time

from dotenv import load_dotenv

from . import intents, llm, remo
from .audio import find_input_device, play_wav_bytes, record_until_enter
from .tts import Speaker


REPLIES = {
    "aircon_on": "エアコンをつけました",
    "aircon_off": "エアコンを消しました",
    "light_on": "照明をつけました",
    "light_off": "照明を消しました",
}


def handle(text: str, conversation: llm.Conversation, dry_run: bool) -> tuple[str, str]:
    """発話を処理し、(返答, 経路) を返す。"""
    intent = intents.match(text)
    if intent is None:
        result = conversation.ask(text)
        return result.text, f"llm {result.duration_ms / 1000:.1f}s"
    # 定型で操作したら、それ以前の聞き返しは片付いたものとして忘れる
    conversation.reset()
    try:
        if intent.action == "aircon_on":
            remo.set_aircon(intent.mode, dry_run=dry_run)
        elif intent.action == "aircon_off":
            remo.set_aircon_power(False, dry_run=dry_run)
        else:
            remo.set_light("on" if intent.action == "light_on" else "off", dry_run=dry_run)
    except remo.RemoError as e:
        return f"操作できませんでした。{e}", "rule"
    if intent.action == "aircon_on" and intent.mode:
        return f"{remo.AIRCON_MODE_LABELS[intent.mode]}をつけました", "rule"
    return REPLIES[intent.action], "rule"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voicehome")
    parser.add_argument("--text", action="store_true", help="音声の代わりにキーボード入力を使う")
    parser.add_argument("--dry-run", action="store_true", help="家電に送信しない")
    parser.add_argument("--model", default="small", help="faster-whisper のモデル（small / medium 等）")
    parser.add_argument("--no-tts", action="store_true", help="返答を読み上げない")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    if args.dry_run:
        # claude -p から呼ばれる remo にも効かせる
        os.environ["REMO_DRY_RUN"] = "1"

    if os.environ.get("LLM_BACKEND", "api") == "api" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY が未設定です。.env に書くか、LLM_BACKEND=cli で claude -p を使ってください")
        return 1
    conversation = llm.Conversation()
    speaker = None if args.no_tts else Speaker()
    if speaker and not speaker.is_ready():
        print(f"TTS エンジン（{speaker.url}）に接続できません。VOICEVOX を起動するか --no-tts を付けてください")
        return 1

    if not args.text:
        from .stt import Transcriber

        device = find_input_device()
        print(f"Whisper {args.model} を読み込み中…")
        transcriber = Transcriber(args.model)

    print("Ctrl+C で終了")
    while True:
        try:
            if args.text:
                text = input("\n> ").strip()
            else:
                input("\nEnter で録音開始 ")
                print("録音中… Enter で終了")
                audio = record_until_enter(device)
                t0 = time.perf_counter()
                text = transcriber.transcribe(audio)
                print(f"認識: {text}  ({time.perf_counter() - t0:.1f}s)")
        except (KeyboardInterrupt, EOFError):
            return 0
        if not text:
            continue
        reply, route = handle(text, conversation, args.dry_run)
        print(f"返答: {reply}  [{route}]")
        if speaker and reply:
            play_wav_bytes(speaker.synthesize(reply))
