"""マイク録音と再生。"""

import io
import os
import threading
import wave

import numpy as np
import sounddevice as sd

STT_SAMPLE_RATE = 16000
# 有線イヤホンマイク。環境変数 MIC_NAME で差し替え可（部分一致）
DEFAULT_MIC_NAME = "ジャックマイク"


def find_input_device(name: str | None = None) -> int | None:
    """名前に一致する入力デバイスの番号を返す。見つからなければ None（既定デバイス）。"""
    name = name or os.environ.get("MIC_NAME", DEFAULT_MIC_NAME)
    for i, d in enumerate(sd.query_devices()):
        # 一覧の先頭側（MME）を優先する。MME はサンプルレート変換を OS がやってくれる
        if d["max_input_channels"] > 0 and name in d["name"]:
            return i
    return None


def _resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return audio
    n = int(len(audio) * dst_rate / src_rate)
    return np.interp(np.linspace(0, len(audio), n, endpoint=False), np.arange(len(audio)), audio).astype(np.float32)


def record_until_enter(device: int | None = None) -> np.ndarray:
    """Enter が押されるまで録音し、16kHz モノラル float32 を返す。"""
    chunks: list[np.ndarray] = []
    stop = threading.Event()
    rate = STT_SAMPLE_RATE
    try:
        sd.check_input_settings(device=device, samplerate=rate, channels=1)
    except sd.PortAudioError:
        rate = int(sd.query_devices(device, "input")["default_samplerate"])

    def callback(indata, frames, time_info, status):
        chunks.append(indata[:, 0].copy())

    with sd.InputStream(device=device, samplerate=rate, channels=1, dtype="float32", callback=callback):
        threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()
        stop.wait()
    audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    return _resample(audio, rate, STT_SAMPLE_RATE)


def save_wav(path: str, audio: np.ndarray, rate: int = STT_SAMPLE_RATE) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


def load_wav(path: str) -> np.ndarray:
    """16kHz モノラルに揃えて読む。"""
    with wave.open(path, "rb") as w:
        rate, ch = w.getframerate(), w.getnchannels()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    audio = pcm.reshape(-1, ch)[:, 0].astype(np.float32) / 32768
    return _resample(audio, rate, STT_SAMPLE_RATE)


def play_wav_bytes(data: bytes) -> None:
    with wave.open(io.BytesIO(data), "rb") as w:
        rate, ch = w.getframerate(), w.getnchannels()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, ch)
    sd.play(pcm, rate)
    sd.wait()
