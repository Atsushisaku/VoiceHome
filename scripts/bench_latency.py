"""録音 / STT / claude -p / TTS の各段の秒数を測る。

    uv run python scripts/bench_latency.py                    # マイクで 1 回録音して測る
    uv run python scripts/bench_latency.py --wav in.wav       # 録音済みの WAV を使う
    uv run python scripts/bench_latency.py --synth "エアコンつけて"  # VOICEVOX で入力音声を作る（マイク不要）

エアコンには送信しない（REMO_DRY_RUN=1）。STT は --models の各モデルで同じ音声を認識し、
1 回目はモデルの読み込み（初回はダウンロード）を含むので「読込」として分けて出す。
"""

import argparse
import os
import statistics
import sys
import tempfile
import time

from voicehome import audio, llm
from voicehome.stt import Transcriber
from voicehome.tts import Speaker


def timed(fn, *args):
    t0 = time.perf_counter()
    result = fn(*args)
    return result, time.perf_counter() - t0


def main() -> int:
    parser = argparse.ArgumentParser()
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--wav", help="入力に使う WAV")
    src.add_argument("--synth", help="この文を VOICEVOX で読ませて入力にする")
    parser.add_argument("--models", nargs="+", default=["small", "medium"])
    parser.add_argument("--runs", type=int, default=3, help="STT と TTS の繰り返し回数（中央値を出す）")
    parser.add_argument("--save", help="録音した音声をこのパスに保存")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["REMO_DRY_RUN"] = "1"
    speaker = Speaker()
    rows: list[tuple[str, str, str]] = []

    if args.wav:
        pcm = audio.load_wav(args.wav)
        rows.append(("入力", f"{len(pcm) / audio.STT_SAMPLE_RATE:.2f}", f"WAV {args.wav}"))
    elif args.synth:
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "input.wav")
            with open(path, "wb") as f:
                f.write(speaker.synthesize(args.synth))
            pcm = audio.load_wav(path)
        rows.append(("入力", f"{len(pcm) / audio.STT_SAMPLE_RATE:.2f}", f"VOICEVOX 合成「{args.synth}」"))
    else:
        input("Enter で録音開始 ")
        print("録音中… Enter で終了")
        pcm, sec = timed(audio.record_until_enter, audio.find_input_device())
        if args.save:
            audio.save_wav(args.save, pcm)
        rows.append(("録音", f"{sec:.2f}", f"発話長 {len(pcm) / audio.STT_SAMPLE_RATE:.2f}s（話している時間そのもの）"))

    transcript = ""
    for size in args.models:
        print(f"STT {size} …", flush=True)
        model, load_sec = timed(Transcriber, size)
        rows.append((f"STT {size} 読込", f"{load_sec:.2f}", "起動時に 1 回だけ"))
        times, text = [], ""
        for _ in range(args.runs):
            text, sec = timed(model.transcribe, pcm)
            times.append(sec)
        rows.append((f"STT {size}", f"{statistics.median(times):.2f}", f"「{text}」 中央値/{args.runs}回"))
        transcript = transcript or text  # LLM には最初のモデルの結果を渡す

    print("claude -p …", flush=True)
    result, llm_sec = timed(llm.ask, transcript)
    rows.append(("claude -p", f"{llm_sec:.2f}", f"API {result.duration_ms / 1000:.2f}s / ${result.cost_usd:.4f} 「{result.text}」"))

    reply = result.text or "テストです"
    times = [timed(speaker.synthesize, reply)[1] for _ in range(args.runs)]
    rows.append(("TTS", f"{statistics.median(times):.2f}", f"VOICEVOX {len(reply)} 文字 中央値/{args.runs}回"))

    print("\n| 段 | 秒 | 備考 |\n|---|---:|---|")
    for stage, sec, note in rows:
        print(f"| {stage} | {sec} | {note} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
