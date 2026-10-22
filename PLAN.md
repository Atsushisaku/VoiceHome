# フェーズ1 計画（2026-10-21 決定）

構想は `voice-assistant-spec.md` を参照。ここにはフェーズ1で決めた範囲と前提だけを書く。

## 範囲
| # | 作るもの | 完了条件 |
|---|---|---|
| 1 | 遅延計測スクリプト | 録音 / STT / `claude -p` / TTS の各段の秒数を表で出す。STT は faster-whisper small と medium を比較 |
| 2 | Remo CLI（`remo list` / `remo aircon on\|off`、`--dry-run` 付き） | 実機のエアコンを CLI から ON/OFF できる |
| 3 | キー押下 → 一連の流れ | イヤホンで「エアコンつけて」→ 実機が動き VOICEVOX で返答。定型命令は LLM を通さず即実行、それ以外は `claude -p`（`--allowedTools` は Remo CLI のみ、`--output-format json`） |

スコープ外：ウェイクワード、Tapo / TV、HA、会話の記憶。

## 技術選定
- Python は uv で管理し 3.12 に固定（`uv python pin 3.12`、`requires-python = ">=3.12,<3.13"`）。システムの 3.10 は使わない
- STT: faster-whisper（CPU。GPU なし）
- TTS: VOICEVOX（後で AivisSpeech に差し替え可。API 互換、ポート 50021 / 10101）
- Remo のトークンは `.env`（`NATURE_REMO_TOKEN`）に置き `.gitignore` で除外。チャットに貼らない
- 最初に `git init`

## 環境（2026-10-21 確認）
- Ryzen 7 5825U / RAM 16GB / NVIDIA GPU なし
- uv 0.11.19（cpython 3.12.13 導入済み）、`claude` CLI あり
- 入力デバイス：「ジャックマイク (Realtek(R) Audio)」＝ 有線イヤホンマイク（認識済み）
- VOICEVOX 未導入。winget に `HiroshibaKazuyuki.VOICEVOX.CPU`（0.25.2）がある
- Nature Remo：トークン発行済み・家電登録済み（`.env` への記入はユーザーが行う）

## 進捗（2026-10-22）
- 済：`git init`・`uv init`（3.12 固定）・VOICEVOX CPU 0.25.2 導入（エンジン単体は `vv-engine/run.exe`）
- 済（コード）：`remo` CLI、`voicehome`（音声 / `--text` / `--dry-run` / `--no-tts`）、`scripts/bench_latency.py`
- 済（2026-10-22 外出中に実施）：トークン疎通（`remo list` でエアコン・洋室照明を取得）、`--dry-run` で定型経路・LLM 経路とも送信内容まで確認。エアコンには一度も送信していない
- 済：LLM 経路を MCP 化（下記）
- 未：実機での ON/OFF、マイク録音での計測

### 遅延計測（1 回目、入力は VOICEVOX の合成音声「今日ちょっと暑いね」1.57 秒）
| 段 | 秒 | 備考 |
|---|---:|---|
| STT small | 2.54 | 正しく認識。読込 28s（初回 DL 込み） |
| STT medium | 7.51 | 同じ結果。読込 79s（初回 DL 込み） |
| claude -p（haiku） | 4.68 | うち API 2.69s。$0.0013 |
| TTS | 1.67 | 25 文字 |

→ 当面は small を既定にする。合成音声はきれいすぎるので、実マイク録音で medium との差を測り直す。

### 分かったこと
- `claude --bare` はサブスク（OAuth）を読まないので使えない
- `--allowedTools "Bash(uv run remo:*)"` に `--permission-mode dontAsk` を足しても、**読み取り専用コマンド（`cat`・`ls`）は通る**（書き込みは拒否される）
- `permissions.deny` に `Read(./.env)` を足すと `cat`・`grep`・`sed`・`tail` は止まるが、**`cat secret*`（ワイルドカード）と `grep -r` は通る**。拒否ルールでは塞げない
- → remo を MCP サーバー（`voicehome.remo_mcp`、mcp 2.3）にし、`claude -p` は `--tools ""` で組み込みツールなし・`mcp__remo` のみ許可にした。渡るツールは `list_appliances` と `set_aircon_power` の 2 つだけで、`.env` を読ませる指示にも「読めない」と返ることを確認
- MCP 化後の LLM 経路は 3 回の中央値 9.3 秒（API 5〜7 秒、ツール呼び出しで 2 往復）。Bash 版と同程度。MCP サーバーの import に約 2.1 秒かかるが、claude 本体の起動と重なって見えない

## 次にやること
1. 在宅時に実機で `uv run remo aircon on` / `off`
2. `uv run python scripts/bench_latency.py --save rec.wav` でマイク録音を計測（small / medium）
3. `uv run voicehome` で一連の流れを通す（VOICEVOX エンジンを先に起動）
