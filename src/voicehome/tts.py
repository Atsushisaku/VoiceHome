"""VOICEVOX エンジンによる音声合成。

AivisSpeech も同じ API なので、TTS_URL=http://127.0.0.1:10101 と TTS_SPEAKER を変えれば差し替えられる。
"""

import os

import requests

DEFAULT_URL = "http://127.0.0.1:50021"
DEFAULT_SPEAKER = 3  # VOICEVOX: ずんだもん（ノーマル）


class Speaker:
    def __init__(self, url: str | None = None, speaker: int | None = None):
        self.url = (url or os.environ.get("TTS_URL", DEFAULT_URL)).rstrip("/")
        self.speaker = speaker if speaker is not None else int(os.environ.get("TTS_SPEAKER", DEFAULT_SPEAKER))

    def is_ready(self) -> bool:
        try:
            return requests.get(f"{self.url}/version", timeout=2).ok
        except requests.RequestException:
            return False

    def synthesize(self, text: str) -> bytes:
        """WAV のバイト列を返す。"""
        params = {"speaker": self.speaker}
        query = requests.post(f"{self.url}/audio_query", params={**params, "text": text}, timeout=30)
        query.raise_for_status()
        wav = requests.post(f"{self.url}/synthesis", params=params, json=query.json(), timeout=60)
        wav.raise_for_status()
        return wav.content
