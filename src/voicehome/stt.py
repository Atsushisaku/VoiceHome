"""faster-whisper による音声認識（CPU）。"""

import numpy as np
from faster_whisper import WhisperModel

# 家電操作の語彙を寄せておくと、短い命令の誤認識が減る
INITIAL_PROMPT = "エアコンつけて。エアコン消して。冷房、暖房。"


class Transcriber:
    def __init__(self, model_size: str = "small"):
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio: np.ndarray, beam_size: int = 1) -> str:
        segments, _ = self.model.transcribe(
            audio,
            language="ja",
            beam_size=beam_size,
            vad_filter=True,
            initial_prompt=INITIAL_PROMPT,
        )
        return "".join(s.text for s in segments).strip()
