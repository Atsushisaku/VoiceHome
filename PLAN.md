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
- 済（2026-10-22 在宅）：実機の ON/OFF、マイク録音での計測、`uv run voicehome` での一連の流れ → **フェーズ1の完了条件を満たした**

### 遅延計測（1 回目、入力は VOICEVOX の合成音声「今日ちょっと暑いね」1.57 秒）
| 段 | 秒 | 備考 |
|---|---:|---|
| STT small | 2.54 | 正しく認識。読込 28s（初回 DL 込み） |
| STT medium | 7.51 | 同じ結果。読込 79s（初回 DL 込み） |
| claude -p（haiku） | 4.68 | うち API 2.69s。$0.0013 |
| TTS | 1.67 | 25 文字 |

### 遅延計測（2 回目、有線イヤホンマイクで「暑いからエアコンつけて」4.34 秒）
| 段 | 秒 | 備考 |
|---|---:|---|
| STT small | 2.14 | 正しく認識。読込 2.6s |
| STT medium | 6.22 | 同じ結果。読込 4.2s |
| claude -p（haiku） | 11.03 | API 7.43s。操作後に状態を読み直して 3 往復、返答 106 文字 |
| TTS | 6.16 | 106 文字 |

→ **STT は small を既定にする**（認識結果は同じで約 3 倍速い）。
→ システムプロンプトに「操作後に確かめ直さない」「1 文 30 文字以内」を足し、同じ文で claude -p 8.6 秒・返答 27 文字に縮んだ（dry-run、2 回の中央値）。

### 一連の流れ（実機、2026-10-22）
| 発話（認識結果） | 経路 | 返答 |
|---|---|---|
| エアコンをつけて。 | rule | エアコンをつけました |
| エアコン消して。 | rule | エアコンを消しました |
| ちょっと暑い。 | llm 6.7s | エアコンをつけました。冷房の25度に設定されています。 |
| エアコン消して。 | rule | エアコンを消しました |

STT は毎回 1.7〜1.8 秒。定型の命令は STT + Remo 送信 + TTS で数秒、LLM 経路はそこに 7〜9 秒が乗る。

### 分かったこと
- `claude --bare` はサブスク（OAuth）を読まないので使えない
- `--allowedTools "Bash(uv run remo:*)"` に `--permission-mode dontAsk` を足しても、**読み取り専用コマンド（`cat`・`ls`）は通る**（書き込みは拒否される）
- `permissions.deny` に `Read(./.env)` を足すと `cat`・`grep`・`sed`・`tail` は止まるが、**`cat secret*`（ワイルドカード）と `grep -r` は通る**。拒否ルールでは塞げない
- → remo を MCP サーバー（`voicehome.remo_mcp`、mcp 2.3）にし、`claude -p` は `--tools ""` で組み込みツールなし・`mcp__remo` のみ許可にした。渡るツールは `list_appliances` と `set_aircon_power` の 2 つだけで、`.env` を読ませる指示にも「読めない」と返ることを確認
- MCP 化後の LLM 経路は 3 回の中央値 9.3 秒（API 5〜7 秒、ツール呼び出しで 2 往復）。Bash 版と同程度。MCP サーバーの import に約 2.1 秒かかるが、claude 本体の起動と重なって見えない

# フェーズ2（2026-10-22 開始）

## 決めたこと
- **LLM は Claude API を既定にする**（`LLM_BACKEND=api`、`.env` の `ANTHROPIC_API_KEY`）。`claude -p` は `LLM_BACKEND=cli` で残す
  - 既定モデルは `claude-haiku-5-5`・effort `low`（簡単な処理なので Haiku で十分と判断。`LLM_MODEL` / `LLM_EFFORT` で変更可）。Opus 等に変えたときは拒否時のサーバー側フォールバック（`fallbacks: "default"`）が有効になる
  - API 経路はツールを同じプロセスで実行するので、LLM がファイルやコマンドに触れる手段はない
  - `claude -p` を呼ぶときは `ANTHROPIC_API_KEY` を外して渡す（渡すと claude がサブスクではなく API で課金するため）
- **曖昧な発話は聞き返す**：感想・遠回しな希望では操作せず「〜しましょうか？」と聞く。同意されたら操作、断られたら何もしない
  - 「うん」が通じるよう、直近 60 秒の会話を覚える（`FOLLOWUP_SEC`）。定型命令で操作したら忘れる
- **照明（洋室照明）を追加**：`remo light on|off|night|...`、LLM ツール `set_light`、定型命令「電気つけて」「照明消して」

## 確認済み（dry-run、claude -p 経路）
- 「ちょっと暗いね」→「照明をつけましょうか？」→「うん、お願い」→「照明をつけました。」
- 「今日は暑いね」→「エアコンをつけましょうか？」→「いや、大丈夫」→ 何もしない
- 定型命令の判定 12 例（照明の on/off、否定、エアコンと照明の両方を含む文は LLM へ）

## 確認済み（dry-run、API 経路 Haiku 5.5）
- 最初のプロンプトでは「うん」で照明を操作した直後の「今日は暑いね」で、聞き返さずにエアコンを ON にした（同意の持ち越し）。「暗いね」で状態を見ずに「明るくしましょうか」と提案した
- 「操作してよいのは明確な指示か直前の提案への同意だけ」「同意は 1 回限り」「提案の前に list_appliances」を明記 → 3 場面 × 3 周・24 発話で違反 0。応答 0.8〜4.2 秒（claude -p の 7〜9 秒より速い）
- 既知の食い違い：「寒いね」に「暖房にしましょうか」と提案することがあるが、ツールは電源のみで、同意されても前回のモード（冷房）で ON になる

## 未確認
- 照明の実機操作、API 経路での実機の一連の流れ

## 候補（未着手）
- エアコンのモード・温度を変えるツール（上の「暖房にしましょうか」の食い違いを解消する）
- LLM 経路の短縮：返答を 1 文ずつ読み上げ始める
- スペック記載の残り：ウェイクワード（openWakeWord）、Tapo / TV、会話の記憶（長期）
