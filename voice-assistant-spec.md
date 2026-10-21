# 自作音声アシスタント（アレクサ強化版）仕様メモ

## 目的
- ウェイクワードで起動 → 音声をLLMが解釈 → 家電を操作 → 音声で返答
- 単純操作だけでなく、曖昧な指示の解釈・状況判断・提案ができる「強化版」を目指す

## 対象機器
| 機器 | 連携方法 | 難易度 | 備考 |
|---|---|---|---|
| Nature Remo | 公式Web API（アクセストークン） | 易 | エアコン等IR家電はここ経由。最優先 |
| Tapo | 非公式ライブラリ（python-kasa / plugp100 等）またはHA連携 | 中 | ファーム更新で壊れるリスク |
| TCL TV | Google TVならADB / Cast / HA連携。IRならRemo経由 | 中 | |
| eufy | 非公式連携のみ | 難 | 初期スコープ外 |

## アーキテクチャ方針
- 将来的には Home Assistant（HA）を土台にする案が有力（OSS・無料。HA OS / Docker で導入可）
- **試作段階はHAを使わず、Pythonスクリプトで直接組む**（PCのマイクをDockerに渡すのが面倒なため）

### 試作パイプライン
```
キー押下で録音（有線イヤホンマイク）
  → STT（faster-whisper / kotoba-whisper）
  → LLM（claude -p）
  → 家電操作CLI（Remo API など）
  → TTS で返答
```

### 設計原則
- **二段構え**：定型コマンド（「エアコンつけて」等）はLLMを通さず即実行し、曖昧な指示だけLLMに回す（遅延・コスト対策）
- 家電操作は独立したCLI（またはMCPサーバー）として作り、`claude -p` からも将来のAPI経由からも再利用できるようにする
- `claude -p` では `--allowedTools` で家電操作CLIだけを許可する。`--output-format json` を使う

## LLM
- 試作：`claude -p`（サブスク枠を利用）
  - 懸念：起動のたびに数秒〜十数秒かかる、開発作業と利用枠を共有する、HAの会話エージェントとして直接は使えない
  - 規約：自分のマシンからのスクリプト利用は想定範囲内。サブスクのOAuthトークンを他ツールに流用するのは不可。常時運用する前に最新規約を確認する
- 本番：Claude APIキーに移行（二段構えなら月数百円程度の見込み）

## STT（音声認識）
- 第一候補：faster-whisper
- 日本語の精度・速度を重視するなら kotoba-whisper / ReazonSpeech も比較する
- 短い命令文が中心なので軽量モデルで十分な見込み

## TTS（音声合成）
- 第一候補（ローカル・無料）：AivisSpeech / VOICEVOX / Style-BERT-VITS2
  - ラズパイでは遅いため、常設するならミニPCを推奨
- クラウド（低遅延）：Cartesia Sonic / ElevenLabs Flash
- 高品質：ElevenLabs
- 注意：固有名詞（地名・人名）の読み間違いは辞書登録で対処する

## ウェイクワード
- openWakeWord（後から追加）
- 英語のプリセット（例：Hey Jarvis）が基本。日本語の独自ワードは学習可能だが、誤検知が増えやすい

## ハードウェア
- iPad：常時待受けは不可（iOSの制約）。操作パネル（ダッシュボード）用途なら可
- 試作：手持ちPC＋マイク付き有線イヤホン（追加費用0円）
  - 検証できないこと：離れた位置からのウェイクワード認識、テレビ音での誤検知、常時待受けの安定性
- 本番候補：ミニPC（N150級・16GB）＋音声端末（HA Voice系 / ESP32-S3）またはUSBスピーカーフォン
- 投資の優先はマイクの品質。ディスプレイの優先度は低い（手持ちのiPadで足りる）

## 予算感
| 構成 | 目安 |
|---|---|
| 試作（手持ちPC＋イヤホン） | 0円 |
| 最小（手持ちPC＋スピーカーフォン） | 約1万円 |
| 推奨・ディスプレイなし（ミニPC＋専用端末1台） | 5〜6.5万円 |
| ディスプレイあり（壁掛けタブレット追加） | 6.5〜9万円 |
| ランニングコスト | 電気代 月100〜300円 ＋ API代 月数百円 |

※2026年はメモリ高騰で価格が変動しているため、購入前に要確認

## 実装ステップ
1. Remo APIでエアコンをON/OFFするPython CLIを作る
2. `claude -p` から1を呼ばせる（テキスト入力で動作確認）
3. 録音（キー押下）→ Whisper を接続する
4. TTSで返答する
5. openWakeWordで待受けにする（この段階でスピーカーフォンの購入を判断）
6. Tapo / TV を追加する
7. （任意）HAに移行し、API化する

## 強化版の差別化アイデア
- 曖昧な指示の解釈（「寝る準備して」→ 複数の家電を一括操作）
- 状況判断（室温・時刻・在宅状況）にもとづく提案
- カレンダーなど外部情報との連携
- 会話の記憶（「昨日と同じ設定で」）
- HAの `assist_satellite.start_conversation` を使った、アシスタント側からの能動的な提案（HA移行後）

## 参考
- HA公式 start_conversation: https://www.home-assistant.io/actions/assist_satellite.start_conversation/
- HAの遅延に関する議論: https://github.com/orgs/home-assistant/discussions/2623
- Nature Remo API入門: https://dev.classmethod.jp/articles/nature-remo-api/
- Whisper + Ollama + Edge TTS の日本語構成例: https://github.com/codejoetheduke/Japanese-AI-Chat-Bot
- Picovoice: Claudeを音声化するガイド: https://picovoice.ai/blog/add-voice-to-claude/
