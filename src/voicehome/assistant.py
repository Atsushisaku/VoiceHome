"""キー押下で録音 → STT → 定型命令 or claude -p → TTS で返答。

    uv run voicehome              # 音声で使う
    uv run voicehome --text       # キーボード入力で試す（マイクと STT を使わない）
    uv run voicehome --dry-run    # エアコンに送信しない
"""

import argparse
import os
import sys
import time

from dotenv import load_dotenv

from . import intents, llm, remo
from .audio import find_input_device, play_wav_bytes, record_until_enter
from .tts import Speaker


def handle(text: str, dry_run: bool) -> tuple[str, str]:
    """発話を処理し、(返答, 経路) を返す。"""
    intent = intents.match(text)
    if intent is None:
        result = llm.ask(text)
        return result.text, f"llm {result.duration_ms / 1000:.1f}s"
    try:
        remo.set_aircon_power(intent.action == "aircon_on", dry_run=dry_run)
    except remo.RemoError as e:
        return f"操作できませんでした。{e}", "rule"
    return ("エアコンをつけました" if intent.action == "aircon_on" else "エアコンを消しました"), "rule"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voicehome")
    parser.add_argument("--text", action="store_true", help="音声の代わりにキーボード入力を使う")
    parser.add_argument("--dry-run", action="store_true", help="エアコンに送信しない")
    parser.add_argument("--model", default="small", help="faster-whisper のモデル（small / medium 等）")
    parser.add_argument("--no-tts", action="store_true", help="返答を読み上げない")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    if args.dry_run:
        # claude -p から呼ばれる remo にも効かせる
        os.environ["REMO_DRY_RUN"] = "1"

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
        reply, route = handle(text, args.dry_run)
        print(f"返答: {reply}  [{route}]")
        if speaker and reply:
            play_wav_bytes(speaker.synthesize(reply))
