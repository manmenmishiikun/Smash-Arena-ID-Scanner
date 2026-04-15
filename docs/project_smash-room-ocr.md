# smash-room-ocr プロジェクト仕様・設計

OBS WebSocket 機能を利用し、スマブラSPの配信・録画画面から「部屋ID」を WinRT OCR で読み取り、クリップボードへ自動コピーおよび通知を行う **Windows 専用**のデスクトップ支援ツール。

# 技術スタック

- **言語**: Python 3.10+
- **GUI**: `customtkinter`, `tkinter`
- **画像処理**: `opencv-python`, `numpy`（二値化、ROI、テンプレートマッチング）
- **OCR**: `winsdk`（Windows 10/11 WinRT OCR）
- **OBS**: `obsws-python`（WebSocket v5・ソースのスクリーンショット取得）
- **その他**: `pystray` / `Pillow`（トレイアイコン描画。`requirements.txt` に明示）、`pyperclip`（クリップボード）、`winsound`（通知音）、`pyinstaller`（exe ビルド用）、`aiohttp`（拡張連携用ローカル SSE サーバー）

# 主要機能（実装済み）

- OBS 接続・ソース選択・フレーム取得からの **部屋ID自動検出**（連続フレームで同一IDが確定したときのみコピー・通知）。
- **同一IDの再コピー・再通知の抑制**（テンプレ一致が一瞬外れても `last_copied_id` を維持。詳細は `room_id_detector.py`）。
- **Win+V クリップボード履歴**から、**直前の部屋ID文字列に一致する1件を削除**（新ID確定時・別IDに変わったときのみ。`clipboard_history_win.py`。履歴オフや権限により失敗しうる **ベストエフォート**）。
- **検知ランプ**（ROOM: テンプレ一致、ID: 5桁パターンで読み取れたか）。ランプ用キャンバスと「ROOM」「ID」ラベルに同一の `ToolTip` を付与。ラベルは `LAMP_LABEL_HIT_WIDTH` で最小幅を揃え、ホバー当たり幅を ROOM / ID で一致させる。
- **履歴ドロップダウン**（直近IDの選択コピー。トリガー幅と揃えたメニュー）。
- 通知音オン/オフ、常に最前面、起動時自動接続、`config.json` 永続化、タスクトレイ連携（最小化はトレイ格納、`×` とトレイ「終了」は完全終了）。
- **単一起動制御（Windows）**: `main.py` で **名前付き Mutex** により多重起動を禁止。二重起動時は新規インスタンスを終了し、可能な場合は既存インスタンスへ名前付き Event で「前面化要求」を送って既存ウィンドウを `deiconify()` + `lift()` で前面に戻す（失敗時はタイトル検索で復元を試みるベストエフォート）。
- **監視ボタン横のステータスランプ**（`canvas_indicator`）: 停止時は灰、監視中は赤、**ID コピー成功の一瞬のフラッシュは白**（`#ffffff`。巨大 ID 帯の緑ハイライトとは別）。
- **OBS 接続設定**と**対象ソース**は**独立した角丸 `CTkFrame` カード**（ヘッダ＋中身）。ヘッダ行は固定高さ（`CONNECTION_HEADER_ROW_HEIGHT`）。タイトルは **place** でカード幅中央（`relx=0.5, anchor="center"`）、キャレットは左（`HEADER_CARET_PAD_X`）に **place** し、重ね順は `tk.Misc.tkraise(canvas)`（`tkinter.Canvas` は `lift`/`tkraise` が `tag_raise` に束縛されるため）。**カード内側**に `frame_*_inner` を置き `CONNECTION_CARD_INSET` で四辺に余白を取る。カードまわりの余白は **`CONNECTION_CARD_UNIFORM_PAD`** で統一。**状態A**では 2 カードを隣接させ、`CONNECTION_CARD_PEER_GAP`（5px）は OBS 直下のすき間のみ。伸縮スペーサーは **対象ソースの下**（カード同士の間には置かない）。**状態B**では 2 カードの間に `CONNECTION_CARD_PEER_GAP` を `grid` の `pady` で確保。**状態A（setup）**と**状態B（run）**をヘッダクリックで瞬時にスワップ（アニメなし）。ウィンドウ幅は `WINDOW_WIDTH`（400）固定。縦幅は起動時に **`_compute_fixed_window_height()`** で setup / run それぞれの `winfo_reqheight()` を測り **`max` を `_fixed_window_height` に保存**し、以降の **`_fit_window_height_to_content`** は常にその固定値を適用する（状態切替でリサイズしない）。状態Aの伸縮スペーサーは **空の `CTkFrame` を使わない**（要請高さが約200pxになり無意味な縦余白になるため **`tk.Frame`（高さ1）** を使用）。`frame_dynamic` 内の weight=1 行はウィンドウ外寸内で余白を吸収する。状態Bでは **監視ボタン＋`label_status`** を `frame_run_cluster` にまとめ、`frame_run_middle` は **`CTkFrame` ではなく `tk.Frame`**（背景 `_get_bg_color()`）とし、子を **`grid`（上スペーサー／クラスタ／下スペーサーの 3 行）** で配置し、行の伸縮は **`RUN_SPACER_WEIGHT_TOP` / `RUN_SPACER_WEIGHT_BOTTOM`（既定 8:3）** で上側に多めに割り当てる（区切り線をより下にあるとみなして帯の縦バランスに合わせる）。`frame_run_middle` を `CTkFrame` のまま親 `grid`＋スペーサー行だけだと、縦方向の stretch が効かず余白が下に溜まりやすい。
- **レイアウト**: `frame_dynamic` にカード・`frame_run_middle`（監視＋ステータス）のみを置き `expand=True` で伸縮。**下端**は `frame_toggles` を先に `pack(side="bottom")` し、その上に区切り線（`frame_bottom_separator`）、その上に **`frame_arena_scan_row`**（Arena Scan ロゴ＋「と連携」スイッチ＋歯車）、その上に `frame_dynamic` を `pack(side="top", expand=True)`。連携ポート入力は **歯車の `CTkToplevel` モーダル**内にあり、`ExtensionBridgeMixin` の `entry_extension_bridge_port` / `label_bridge_port` はそのモーダルで生成する。状態切替では **トグル帯・区切り線・Arena Scan 行は pack し直さない**（見切れ防止）。**Z 順**: 巨大ID帯は `frame_dynamic` より **先に** `pack` されるが、後から `pack` したウィジェットが手前に描画されるため、構築後に `_frame_id_outer.lift()` で ID 帯を前面へ（ヒント「クリックで再コピー」が角丸カードに隠れないようにする）。
- **動的中間は `grid`**: 状態A/B の切替で OBS/ソースの**カード枠**は `grid_forget` せず行の付け替えのみ（点滅軽減）。可変行（スペーサー・`frame_run_middle`）だけ `grid_forget`。
- **ウィンドウ高さ**: 起動完了時に **`_compute_fixed_window_height`** で `_fixed_window_height` を確定。状態切替のたびに **`_fit_window_height_to_content`** を **同一イベント内で即時**呼び、その後 **`update()`** で描画を確定する（遅延 `after` は使わず、段階的リサイズに見える挙動を防ぐ）。角丸が親で切れないよう、固定値は setup/run 両方の実寸に基づく。**起動時**: UI 構築・縦幅スナップまで **`withdraw()`** し、完了後 **`deiconify()`** で初めて表示する（暫定寸法の一瞬表示を防ぐ）。
- **区切り線**: 高さ `BOTTOM_SEPARATOR_HEIGHT`（2px。DPI により 1px が消えるのを防ぐ）。色は `_get_bottom_separator_color()`（ダークでは履歴枠と同じ `HISTORY_BORDER` / `#555555`、ライトでは `#666666`）。`BOTTOM_SEPARATOR_PADY_TOP`（5px）で上側余白（監視クラスタ〜区切りの見た目バランス用に調整）。区切りとトグルを `lift()`。
- **状態A**: OBS 展開、対象ソースは畳み。スペーサーは **対象ソースカードの下** に置き余白を吸収（カード同士の間には伸びない）。監視ボタン＋`label_status` は非表示。セットアップ時にステータス行が見えないため、接続エラー時は（状態Aなら）`messagebox` で補足。
- **状態B**: OBS 畳み、対象ソース展開、監視行＋`label_status` を `frame_run_cluster`（親は `tk.Frame` の `frame_run_middle`）に載せ、`frame_run_middle` 内は **`grid` の行ウェイト**（上スペーサー＞下スペーサー）でソース直下〜区切り線付近の帯に縦配置。`frame_run_middle` の `grid` 余白は `RUN_MIDDLE_GRID_PADY`（既定 `(4, 1)`）。ボタン行（`frame_ctrl`）と `label_status` の間は `RUN_CLUSTER_BTN_STATUS_GAP`（既定 6px）。接続完了（`_safe_update_sources`）で自動的に状態Bへ。
- **切断時の扱い**: OBS 側切断時は **状態Aへ戻し**、`label_status` に加えて setup 側で常に見える OBS カード内ラベル（`label_setup_status`）にも「再接続してください」を表示する。切断通知の `messagebox` は表示しない。
- **初期表示（近似）**: `auto_start` かつ `target_source` が空でないときは起動時から状態B。
- **自動接続フラグ**: OBS 接続成否や切断イベントでは `auto_start` を変更しない。`⚡ 自動接続` チェックボックスの操作時のみ `config.json` に保存される。

## Chrome 拡張連携 UI（ミニマル化・2026-04）

- **ポップアップ（`options.html`）**: ヘッダに `icons/brand-arena-scan-128.png` と短文。**保存ボタンなし** — `bridgeEnabled` / `autoClickMatchingPostBtn` は変更時に即 `chrome.storage.sync.set`、**連携ポート**は入力の **300ms デバウンス**後に検証成功時のみ保存。ポート入力は **`<dialog>`** の詳細からのみ（メインに IP や `/events` は出さない）。状態ブロックは `background.js` の `SMASH_ARENA_GET_BRIDGE_STATUS` をポーリングして表示。**使い方**は `guide.html` を新規タブで開く。
- **ツールバー**: `background.js` の `syncToolbarTitle()` で `chrome.action.setTitle` に **平易な日本語一行**（ホバーで理由が分かる）。

## GUI 詳細: 接続設定カード（2026-04 改）

- **切替**: `_apply_connection_layout("setup" | "run")` が **`frame_dynamic` 内**だけを `grid` で組み替える（可変行の `grid_forget`／再配置）。
- **下端区切り線**: `BOTTOM_SEPARATOR_PADX` で左右に余白を取った細い `CTkFrame`（高さ `BOTTOM_SEPARATOR_HEIGHT`、色 `_get_bottom_separator_color()`＝ダーク時 `HISTORY_BORDER` / ライト時 `#666666`）。
- **旧アコーディオン**（共有ビューポート＋高さアニメーション）は廃止。

# 配布ビルド

- **`scripts/build_exe.bat`**: PyInstaller で単一 `SmashArenaIDScanner.exe` を生成（`--hidden-import` に `winsdk` 関連および `winsdk.windows.applicationmodel.datatransfer` 等を指定）。

## ビルド検証（2026-04）

- **仕組み**: venv 必須 → `pip install -r requirements.txt` → `PyInstaller --onefile --windowed` で `main.py` を起点に依存を収集。`--add-data` の区切りは Windows 向けに `;` で正しい。`winsdk` / `pystray._win32` の hidden-import は WinRT OCR とトレイのために妥当。
- **実測サイズの目安**: 同一オプションで生成した `dist\SmashArenaIDScanner.exe` は **約 74MB**（環境・バージョンで前後）。`build\...\SmashArenaIDScanner.pkg` も同程度で、**肥大の主因は `opencv-python`（venv 内 `cv2` フォルダだけで約 109MB 相当）と `numpy`（約 29MB 相当）**、ランタイム・その他依存が続く。`pystray` 本体は 0.2MB 未満で、`--collect-all pystray` はサイズ面では誤差レベル。
- **`--collect-all customtkinter`**: テーマ・アセット同梱のため一般的。無効化すると UI が欠けるリスクが高い。
- **無駄・注意点**:
  - ビルドのたびに **全パッケージを `pip install` し直す**ため時間がかかる（exe 自体の無駄ではない）。必要なら「初回のみ」や `pip install -r requirements.txt` を手動に分離できる。
  - **CLI で `PyInstaller ... main.py` を実行すると `packaging/SmashArenaIDScanner.spec` とは別に spec が再生成される**。カスタム `excludes` / `optimize` / UPX 等を spec で管理するなら、**編集済み spec を `pyinstaller packaging/SmashArenaIDScanner.spec` でビルドする運用**の方が安全。
  - **既存の exe が実行中**だと上書きに失敗する（`PermissionError`）。配布前にプロセスを終了する。
  - 生成 spec の `upx=True` は **UPX が PATH に無いと実質スキップ**されがち（サイズ削減は環境依存）。
- **さらに小さくする方向（要検証）**:
  - アプリは `cv2.imshow` / GUI を使っていないため、**`opencv-python` → `opencv-python-headless`** に差し替えれば OpenCV バイナリがやや小さくなる可能性がある（数 MB 級の差はバージョン依存。導入後はテンプレ一致・デコードを必ず再確認）。
  - `numpy` / `cv2` を避ける実装はコストが大きい。`--exclude-module` での刈り込みは壊れやすい。

# ファイル構成（主要）

| ファイル | 役割 |
|---------|------|
| `main.py` | エントリ。ルートロガー＋`image_processor` 用ログ初期化、単一起動（Mutex）、既存インスタンス前面化イベントの受信。`SmashArenaIDScannerApp` は `gui.main_window` から直接 import する。 |
| `gui/` | GUI 実装パッケージ。`main_window.py`（`SmashArenaIDScannerApp`）、`constants.py`（レイアウト定数）、`tooltip.py`、`tray.py`、`mixins/connection.py`（OBS/ソースカード・setup/run 切替）、`mixins/history.py`（履歴ドロップダウン）、`mixins/extension_bridge.py`（Chrome 拡張向け SSE の Listen 同期・`notify` 経路）。 |
| `ocr_worker.py` | `OCRWorker`（`threading` + `asyncio`）：OBS 取得→ROI→OCR→確定。監視ループの待機は `stop_worker` 後に速やかに抜けられるよう短い区切りで `asyncio.sleep`（`_sleep_while_running`）。 |
| `pipeline_profile.py` | 監視ループのフェーズ時間計測（環境変数で有効化）。 |
| `room_id_detector.py` | 部屋ID確定のステートマシン（`reset_pending_only`・コピー成功後の `acknowledge_copy` 等）。 |
| `clipboard_history_win.py` | Windows クリップボード履歴のテキスト一致削除（非Windowsでは no-op）。 |
| `image_processor.py` | テンプレ・ROI・前処理・ID正規表現抽出。 |
| `ocr_engine.py` | WinRT OCR（`WinRTOcrEngine` のみ。差し替え時は同契約のクラスで可）。 |
| `obs_capture.py` | OBS WebSocket スクショ取得。 |
| `config_manager.py` | 設定 JSON の読み書き（原子的保存・バックアップ・数値サニタイズ）。 |
| `extension_bridge_server.py` | 拡張連携用: `127.0.0.1` 上の SSE（`GET /events`）。OCR ワーカーとは別スレッド・別イベントループ。 |
| `chrome-extension/` | Chrome 拡張（SSE クライアント・`smashmate.net` rate ページの入力補助）。詳細は `chrome-extension/README.md`。 |
| `run_app.bat` | venv 有効化して起動。 |
| `tests/` | `pytest` による回帰テスト（検出ロジック・テキスト抽出・デコード・設定）。 |
| `pytest.ini` | pytest の `testpaths=tests`。 |
| `tools/test_pipeline.py` | ローカル画像 / OBS 連携の統合検証スクリプト。 |
| `tools/test_boot.py` | 短時間の起動スモーク。 |
| `scripts/_treq.py` | 開発用: 接続カード setup/run の要請高さをコンソールに出すワンオフ（本番起動経路では未使用）。 |
| `assets/templates/` | テンプレート画像（`arenahere*.png` など）。 |
| `assets/samples/` | OCR 回帰確認に使うサンプル画像群。 |
| `icons/` | アイコン素材（`arena scan@128.png`＝デスクトップ、`mate flow-*@128.png`＝拡張用）。 |
| `tools/generate_extension_icons.py` | 拡張配布用 PNG（16/32/48/128px）を 128px 素材から生成し `chrome-extension/icons/` へ出力。 |

## アイコン（2026-04）

- **デスクトップ**: `icons/arena scan@128.png` をタイトルバー（64px）およびシステムトレイ（64px）に利用。巨大な原本（`arena scan.png` 等）は exe に同梱せず、128px のみ `packaging/SmashArenaIDScanner.spec` の `datas` に追加。
- **Chrome 拡張**: `icons/mate flow-*@128.png` をソースに `tools/generate_extension_icons.py` でリサイズし `chrome-extension/icons/` に配置。`manifest.json` の `icons`（ストア・拡張管理画面の一覧）は緑。ツールバーは `background.js` の `chrome.action.setIcon` で **接続状態が `connected`（SSE 確立）のときだけ緑**、それ以外は赤。素材を差し替えたら同スクリプトを再実行する。

# Chrome 拡張連携（ローカル SSE）

**Chrome 拡張**（`chrome-extension/`）が `smashmate.net` の rate ページで部屋ID入力を補助する。Python 側が **Server-Sent Events（SSE）** で部屋IDを配信する。**拡張の manifest・バックグラウンド・コンテンツスクリプト・オプション・説明は `chrome-extension/` に含める**（仕様の正は引き続き [`extension_bridge_server.py`](../extension_bridge_server.py) を優先）。

| パス | 内容 |
|------|------|
| `chrome-extension/manifest.json` | MV3・権限・コンテンツスクリプト（`matches`: `https://smashmate.net/rate/*` のみ） |
| `chrome-extension/constants.js` | `SMASH_ARENA_BRIDGE`（`SSE_PATH`・既定ポート・`MAX_SSE_BUFFER_BYTES`）。`extension_bridge_server` と値を揃える。`background.js` は `importScripts("constants.js", …)`、`options.html` も先に読み込む。 |
| `chrome-extension/background.js` | `importScripts("constants.js", "shared-path.js")` 後、**`isRateProfilePath` に合致するタブが 1 つ以上あるときだけ** `127.0.0.1:<port>` + `SSE_PATH` へ `fetch`（それ以外は接続しない）。`tabs.onUpdated` / `onRemoved` でデバウンスし再評価。SSE パース（バッファ上限あり）・該当タブへの並列配信。**同一ポートで既に接続中なら再接続せず、不要な abort/reconnect を抑える。**さらに、**rateタブ集合はキャッシュで管理**し、配信ごとの `tabs.query` を避ける。接続状態（connecting/retrying/error 等）は runtime message で options へ公開し、`detail` は表示崩れ防止のため短く正規化して返す。**SSE 読み取りタイムアウトや中断時は `ReadableStream` を `cancel` してソケットを早めに解放**し、ツールバーアイコンは緑/赤が変わるときだけ `setIcon` する。 |
| `chrome-extension/shared-path.js` | `isRateProfilePath` のみ（background / content で重複定義しない） |
| `chrome-extension/content.js` | pathname ゲート・`button.matching_post_btn` 存在時のみ入力反映。受信部屋IDは Python の `ROOM_ID_PATTERN` と同じ正規表現で検証。`autoClickMatchingPostBtn` が true のとき入力後に同ボタンを `click()`（オプションは `storage` キャッシュ + `onChanged` で同期）。**負荷抑制のため、auto-click は 15 秒クールダウン + 同一IDの短時間再クリック抑制（2分 TTL）を適用**し、**ボタンが有効（disabled ではない）場合のみクリック**。また、**手入力時は部屋ID欄で Enter または Space を押すと `matching_post_btn` クリック扱い**にし、**確認ダイアログ表示中は Enter または Space=OK / Escape または Backspace=キャンセルでキーボード操作**できるようにする（いずれも **`keyboardShortcutEnter` 等で個別に無効化可**、既定はすべて ON。ダイアログの自動押下はしない）。**チャット欄など部屋ID欄以外の編集入力では Enter/Space/Escape/Backspace のショートカット処理を走らせず、入力操作を妨げない（`contenteditable` は子要素フォーカス時も含めて判定）。部屋ID欄にフォーカスがある間は SweetAlert ショートカットが Enter/Space を奪わない。さらに、同一IDの再受信でも入力欄の現在値がズレている場合は再反映できるようにする。** **部屋ID欄が空のときは、SSE 由来の入力反映のうち先頭 1 回だけをスキップ**し（別ページから戻った直後などに届く古い値の即時反映を抑止）、**2 回目以降**から貼り付け。空欄に戻したら再び先頭 1 回スキップを武装。手入力で空でなくなったらスキップ武装を解除。**空欄かつ「前回の部屋IDを呼び出す」系の `span.cursor` が見えるときは、部屋ID欄の Enter または Space で `matching_post_btn` より当該要素を優先クリック。** SPA 相当の pathname 変化は **`popstate` + 適応間隔の `setTimeout` 連鎖**で検知（対戦ルームプロフィール URL 上は約 700ms、それ以外の `rate` 配下は約 2.5s）。**タブ非表示時はタイマーを停止**し、再表示時に再開。 |
| `chrome-extension/options.*` | 連携 ON/OFF（`bridgeEnabled`）・自動クリック（`autoClickMatchingPostBtn`）・**キーボード（`keyboardShortcutEnter` / `keyboardShortcutSpace` / `keyboardShortcutEscape` / `keyboardShortcutBackspace`、既定 true）**・ポート（`bridgePort`、`<dialog>` の詳細から編集、メイン画面には URL プレビューを出さない）。変更は **即 `chrome.storage.sync.set`**（保存ボタンなし）。ポートは入力 **300ms デバウンス**で検証成功時のみ保存。`bridgeEnabled` OFF 時はポート欄を無効化。**接続状態**は `SMASH_ARENA_GET_BRIDGE_STATUS` を **約4秒ポーリング**（ポップアップが可視のときのみ）し、色分け＋ヒント。**接続済みでも部屋 ID 通知が 60 秒以上無い**ときは待機秒数を表示。`storage.onChanged` で他タブ変更を反映し、**ポート入力にフォーカスがある間はポート値の上書きを避け**チェック類のみ部分同期。`guide.html` を新規タブで開く導線あり。 |
| `chrome-extension/README.md` | 利用者向け（自動化範囲・規約・再接続・配布） |

- **スマメイトの利用規約・各種ポリシーへの適合**は利用者自身とし、著しいサーバー負荷や手動操作を超える頻度は避ける設計方針とする。本実装は**一般目的のローカル連携の例**として提供する。

## `AppConfig` のフィールド（OBS と混同しない）

| フィールド | 意味 |
|-----------|------|
| `host` / `port` / `password` | **OBS WebSocket** 接続用（変更しない）。 |
| `extension_bridge_enabled` | 拡張連携を有効にする（既定 `false`）。**単独では Listen しない**。 |
| `extension_bridge_port` | **127.0.0.1** で SSE が待ち受けるポートのみ（既定 `2206`）。**OBS の `port` とは無関係**。`ConfigManager._sanitize_config` で **OBS 用 `port` とは別ブロック**として 1〜65535 にクランプする。 |
| `detection_confirm_needed` | 同一 ID が何連続で検出されたら確定するか（既定 `2`、1〜20 にクランプ）。 |
| `detection_poll_fast_sec` | 探索中のフレーム間スリープ秒（既定 `1.0`、**0.2〜60**）。 |
| `detection_poll_slow_sec` | 同一 ID 維持中のスリープ秒（既定 `3.0`、0.1〜120、`poll_fast` 未満にはならない）。 |

## Listen の開始・停止（固定）

- **Listen 開始**: `extension_bridge_enabled` が True **かつ** `OCRWorker.is_monitoring` が True のときだけ、`127.0.0.1:extension_bridge_port` で待受を開始する。
- **Listen 停止**: 監視停止（`is_monitoring` が False）、連携トグル OFF、**OBS 切断**（`_safe_on_disconnected` 等で監視が止まる）、**アプリ終了**のいずれかでソケットを閉じる。
- **冪等性**: GUI の `_sync_extension_bridge_listen()`（`ExtensionBridgeMixin`）は、**既に同じポートで待受中なら再作成しない**（`_extension_bridge_sync_lock` で start/stop を直列化）。
- **設定保存**: `_save_config` は UI から `_apply_extension_bridge_fields_from_ui` で反映したうえで保存し、**有効/無効・ポートが変わったときだけ** `_finalize_extension_bridge_after_save` 経由で `_sync_extension_bridge_listen` を呼ぶ（通知音など他項目の保存で不要な `stop()/join` を避ける）。
- **ポート変更**: Listen 中に `extension_bridge_port` が変わった場合は**いったん停止**し、条件が両方 True なら**新ポートで再開**。再開失敗時はログを残し、`label_status` に短いエラー（例: ポート使用中）。**待受に成功したとき**は `ExtensionBridgeServer` の任意コールバック `on_listen_ok` で GUI のステータスを監視中の文言へ戻し、一時的なポートエラー表示を解消する。

## SSE の仕様

- **URL**: `http://127.0.0.1:<extension_bridge_port>/events`（パス定数は `extension_bridge_server.SSE_PATH`＝`"/events"`）。
- **形式**: `Content-Type: text/event-stream`。本文は `data: <部屋ID>\n\n`（プレーンテキスト 1 行）。
- **ペイロード整形**: `notify_room_id` は `_normalize_room_id_for_sse` で改行（`\r`/`\n`）を除去し前後空白を落とす。空になった場合は保持もブロードキャストもしない（`data:` 行の改行インジェクション防止）。
- **ブロードキャスト**: 接続中の全クライアントへ同一 ID を送る。各クライアントの `asyncio.Queue`（`maxsize=64`）が満杯のときは**最古 1 件を破棄してから**新しい ID を載せる（遅い購読者でも常に最新寄りのストリームに寄せる）。
- **リプレイ**: サーバー内に**直近に確定した部屋IDが 1 件**だけ保持し、新規接続時に直ちに 1 件送る（未確定なら送らない）。**待受に成功していない（Listen スレッド起動直後など）**間は `notify` の**ライブ配信（ブロードキャスト）は行わない**が、直近 ID は更新する（Listen 完了後の接続でリプレイ可能）。**bind に失敗した場合**（ポート競合など）はリプレイ用バッファも破棄する。**Listen が正常終了したあと**（監視停止・連携 OFF・アプリ終了など）もリプレイ用バッファを破棄し、次の Listen では新たな OCR 確定までリプレイしない。`is_monitoring` でも SSE 側に流さない条件は従来どおり。
- **終了待ち**: `ExtensionBridgeServer.stop()` の `Thread.join` 上限は `STOP_JOIN_TIMEOUT_SEC`（既定 4 秒）。通常はループ停止で短時間で終わる。

## OCR スレッドとブリッジの境界

- 部屋ID確定は `ocr_worker.py` の `result.confirmed_id` 分岐で `pyperclip.copy` を試す。**コピー成功時のみ** `RoomIdDetector.acknowledge_copy` と `on_id_found`（「コピーしました」表示・通知音・履歴更新）を実行し、クリップボードと GUI の齟齬を防ぐ。失敗時は WARNING ログに留め、`last_copied_id` は更新しないため **同一 ID の再確定で再コピーを試みられる**。`on_confirmed_id_bridge`（SSE）は **確定のたび**呼び、コピー成否に依存しない。
- OCR スレッドからは**ブロッキングしない**。ブリッジは別スレッドの `asyncio` ループ上で `aiohttp` を動かし、`notify_room_id` は `call_soon_threadsafe` でキューへ載せるのみ。
- **`notify_room_id` と `stop()` の競合**: ロック解放後にループが閉じられると `call_soon_threadsafe` が `RuntimeError` になりうるため、**捕捉して DEBUG のみ**（OCR スレッドへ例外は伝播させない）。
- **`_client_queues`**: `add` / `discard` / `clear` / 再代入と `_broadcast` 内のスナップショットを **`_queues_lock`** で直列化（マルチスレッド・停止時の整合用。`_broadcast` 自体はブリッジのイベントループ上で実行される）。

## Chrome 拡張（再接続・配信）

- **SSE の張りどころ**: オプションで接続 ON でも、`/rate/<数>/` 形式のタブが **どれも無い**あいだは **localhost の SSE に接続しない**（不要な常時接続を避ける）。rate タブをバックグラウンドにしたまま別サイトを前面にしていても、当該タブは残っているため接続は維持される。
- **指数バックオフ**の待ち時間に **85%〜100% のジッター**を乗せ、固定間隔でのリトライが重なりにくいようにする。
- **複数タブ**へは `chrome.tabs.sendMessage` を `Promise.all` で並列化（順次 `await` より短時間）。
- **タブキャッシュの再構築**: `rebuildRateProfileTabCache` は**同時に1本だけ**実行する（進行中の `Promise` を共有）。`onInstalled` と `hasAnyRateProfileTab` / `broadcastRoomId` が重なっても `tabs.query` の結果が取り違えられないようにする。
- **sendMessage の扱い**: 「Receiving end does not exist」「Could not establish connection」など**コンテンツ未注入直後の一時失敗**では rate タブをキャッシュから外さない（次のイベントで再送可能にする）。それ以外の失敗では古いタブ ID をキャッシュから除去する。

## 配布（PyInstaller）

- `aiohttp` は `requirements.txt` に含め、**単体 exe** に同梱し、エンドユーザーに追加ランタイムを要求しない想定。ビルドは `scripts/build_exe.bat` または `packaging/SmashArenaIDScanner.spec` で確認する。

# ログ・デバッグ

- `main.py` が **ルートロガー** に stderr ハンドラを付与し、`INFO`/`DEBUG` を設定（`obs_capture` / `ocr_worker` 等のログも表示可能）。
- `image_processor` ロガーは従来どおり専用フォーマット（`%(message)s` のみ）を付与し、`propagate=False` なので二重出力はしない。
- 詳細診断: 環境変数 `SMASH_ROOM_OCR_LOG=1`（または `debug` / `true`）で **DEBUG**（OCR 非マッチなど）。
- **パフォーマンス内訳**: `SMASH_ROOM_OCR_PROFILE=1`（または `true` / `on`）で、`ocr_worker` の監視ループが **capture / roi / ocr / total** の平均 ms を DEBUG で約30フレームごとに出力（`pipeline_profile.py`）。
- **本番パスでは**レイアウト計測用の JSON ファイル追記などは行わない（開発時の一時計測コードは除去済み）。

# OCR 前処理方針（2026-04 再調整）

- 前処理は **複雑化を避けた固定閾値二値化**を維持し、`BINARIZE_THRESHOLD=160` を基準値とする。
- **ブラーは非採用**（文字欠損を招くケースがあったため）。代わりに ROI を拡大した後、上部/左側のノイズ帯を比率トリミングして OCR 対象を ID 文字列寄りに限定する（`OCR_TOP_CROP_RATIO=0.20`, `OCR_LEFT_CROP_RATIO=0.20`）。
- 文字抽出では、曖昧文字展開（`0/Q`, `6/G`, `O` 分岐）より前に、**OCR 生文字列から直接マッチした候補を優先**する。これにより、生OCRが正しく読めている `G` / `Q` を不要に `6` / `0` へ倒さない。
- 複数の有効ID候補が同時に成立する場合、**辞書順やハードコード特例では決めない**。補正後テキスト上で **左から最初に現れる** 5桁（`ROOM_ID_PATTERN` の `finditer` 順）を採用する。テキスト上に候補が現れない場合は曖昧扱いのまま `legacy` 等のフォールバックへ進む。
- 回帰確認用に `tools/test_sample_suite.py` を追加し、`test_screen_<正解>_<誤読>.png` 規約の固定サンプルで一括検証できるようにした（8 枚で 8/8 正解。`test_screen_4Q1PG_4QIPG.png` は正解 4Q1PG、生 OCR が `I` を含みやすい場合のメモ）。

# 軽量化・構成の方針（2026-04 整理）

- **実行時の無駄を減らす**: 不要なファイル I/O・デバッグ用フックを本番コードから外す。
- **依存の明示**: GUI が `Pillow` でトレイ画像を生成するため `requirements.txt` に記載（従来は間接依存のみの可能性あり）。
- **OCR モジュール**: 単一実装のため抽象基底クラスは置かず、`WinRTOcrEngine` の `recognize` 契約で差し替え可能とする。
- **設定の単一ソース**（実行時コストは増やさない）:
  - `AppConfig.to_obs_connection_config()` で `ObsConnectionConfig` を生成し、ホスト／ポート／パスワードの重複指定を避ける。
  - `AppConfig` に **スクショ取得パラメータ**を追加: `screenshot_width` / `screenshot_height` / `screenshot_quality` / `screenshot_format`（`config.json` で上書き可能。`ConfigManager.load` で範囲サニタイズ）。
  - `config.json` の保存は **一時ファイル→`os.replace`** で原子的に行い、上書き前に `config.json.bak` へ退避。読み込み失敗時はバックアップを試す。
  - `RoomIdDetector` のポーリング間隔（`poll_fast` / `poll_slow`）は `DetectionConfig` に含め、確定ロジックと同じ dataclass で調整可能にする。`RoomIdDetector.poll_fast` 等は `_cfg` を参照するプロパティ（読み取り専用）。**実行時**は `AppConfig` の `detection_confirm_needed` / `detection_poll_fast_sec` / `detection_poll_slow_sec` を `ConfigManager._sanitize_config` でクランプしたうえで `AppConfig.to_detection_config()` → `RoomIdDetector(...)` に渡す（GUI 未露出・`config.json` のみで上書き可能）。
- **UI の軽量最適化**:
  - 履歴トリガー幅計算で使用する `tkfont.Font` は毎回再生成せずキャッシュする。
  - 履歴トリガー幅が前回と同じ場合は `configure(width=...)` をスキップし、不要な再レイアウトを減らす。
  - 履歴 ID 一覧（`tuple(_recent_ids)`）が変わらないあいだは、計算済みのトリガー幅を再利用しフォント計測を省略する。
- **監視ワーカー（低スペック向け）**:
  - `find_and_extract_roi` と `extract_room_id_from_text` は `asyncio.to_thread` で既定スレッドプールに退避し、ワーカー上の asyncio ループが OpenCV／正規表現分岐で長く占有されないようにする（WinRT OCR は従来どおり `await`）。
- **1920×1080 へのリサイズ**:
  - 縮小時は `INTER_AREA`、拡大時は `INTER_LINEAR`（従来の `INTER_LANCZOS4` より軽量）。ROI 内の拡大は `INTER_LINEAR`（`INTER_CUBIC` より軽量）。
- **OBS 取得処理の堅牢化**:
  - 未接続時は `get_source_list` / `get_source_screenshot` を早期 return し、呼び出し側の再接続制御へ速く戻す。
  - `data:image/...;base64,...` 形式の payload 切り出しは `partition` で1回だけ実施する。
  - `obsws-python` の同期呼び出しは `asyncio.to_thread` でワーカースレッドに逃がし、イベントループのブロックを避ける。
  - `decode_screenshot_payload()` で base64 を検証し、`imdecode` 失敗時は **接続を切らず** `None` を返す（接続エラー時のみ切断）。
  - ソース一覧取得失敗時はログを残し **接続は維持**（接続切りはスクリーンショット取得の致命的エラー時）。
- **テンプレ照合の軽量化**:
  - 1080p テンプレは **半解像度の粗い照合**で「明らかに不一致」のときだけフル解像度の `matchTemplate` を省略する（`COARSE_EARLY_EXIT_THRESHOLD`）。入力幅が 1280 以下のときは 720p テンプレへ任せるため、粗い段で 1080 フル照合をスキップしうる。
- **OCR 前処理の安全化**:
  - ROI が極端に小さい場合、比率トリミングで空配列になっても元画像を使って継続し、`cv2.threshold` の例外を回避する。

# コーディング方針・制約

- UI は `pack` / `place` を組み合わせ、履歴メニュー等は **固定高さの過剰加算を避け**上下余白が偏らないよう調整。アコーディオン内のパネルは `customtkinter` の制約に合わせて `configure(height=...)` で高さ変更する。
- GUI スレッドと監視処理の分離（`OCRWorker`）。
- WinRT / Windows 依存は OCR・クリップボード履歴に集中。将来 Mac 向けは別実装差し替えを想定。
- 使われない依存・一時デバッグ用のファイル出力はリポジトリに残さない（`debug-*.log` は `.gitignore`）。
- **キャプチャ間隔・スクショ解像度・モード別ポーリング**は、計測や環境で変わりうるため **設定可能な値として設計**する（下記「将来計画」のフレームレート要件と整合させる）。

# 将来計画：統合便利ツール（検討・未実装）

配布しやすい **単一アプリ** に、過去に個別で作っていた機能を統合する構想。実装状況は本リポジトリの現行コード（部屋IDスキャナ）がベースであり、以下は **仕様・設計のメモ**（実装は段階的に行う）。

## モード方針

| モード | 目的（想定） | キャプチャ頻度の目安 |
|--------|----------------|----------------------|
| **メイト** | 専用部屋IDの画面読取→クリップボード、スマメイトの現在レート取得→txt 自動更新（**運営許諾後**に方式・間隔を確定） | **現行ツールに近い低頻度**（秒オーダー）でよい |
| **VIP（オンライン野良）** | 現在戦闘力などの **表示が一瞬しか出ない** UI を OCR | **高頻度**が必要な場面あり（下記「フレームレート」参照） |

- UI は **トグル等でメイト / VIP を切り替え**。VIP 時のみ高負荷ループに切り替え、メイト時は従来どおり軽いままにする。
- **ユーザビリティ**: 別ウィンドウを増やしたり日々の操作を増やすことは避けたい。**取得は引き続き OBS WebSocket（`GetSourceScreenshot`）を第一候補**とし、配信ワークフローと共有する。

## スマメイトレート取得

- **運営への連絡・許諾を得た上で**、API / ページ取得の可否・利用条件・推奨間隔を確定する（未許諾の自動取得は仕様に含めない）。

## パフォーマンス・取得解像度（検討結果）

- ボトルネックは WebSocket そのものより、**毎回のエンコード・転送・デコード・画素数**。関心領域だけ必要でも、**フルフレーム取得後にだけ切り抜く**だけでは負荷削減が限定的になりやすい。将来、さらに軽くする場合は **OBS 側でクロップ済みの小さいソースだけをスクショ対象にする**、または **OS 側の矩形キャプチャ** 等も候補（別ウィンドウ強制にならない範囲で比較）。
- **スクショ解像度**: 負荷と認識率の兼ね合いで **480p 前後が下限候補**（環境により 720p が必要になる可能性あり）。実装時は **設定で変更可能**にする。

## フレームレート・ポーリング間隔の設計要件（必須）

- VIP 向けに必要な **取得間隔 / 実効 FPS は、手作業計測に基づく暫定値**であり、**今後の再検証・端末差・ゲーム側仕様変更で変わりうる**。
- そのため **コード内のマジックナンバーだけに固定しない**。実装段階では次を満たすこと:
  - **設定ファイル（例: `config.json`）またはモード別設定**で、キャプチャ間隔（秒）または目標 FPS を **ユーザーまたは開発者が変更できる**。
  - 既定値は仕様書に「現在の推奨」と明記し、変更履歴は `docs/development_log.md` 等で追えるようにする。
- **現時点の暫定（手作業計測）**: VIP 系の画面チェックは **約 6〜7 fps（秒あたり 6〜7 回取得）が下限に近い**という検証あり。これは **確定仕様ではなく再調整前提**。

## 増築しやすい実装の方向（実装時）

- **キャプチャ**（OBS 等）と **モード別パイプライン**（画像処理・OCR・出力）を分離し、GUI は薄く保つ。
- 既存の `OBSCapture` / `ImageProcessor` / `WinRTOcrEngine` / `RoomIdDetector` 等を **部品として再利用**し、メイト・VIP 用ロジックは別モジュールに追加しやすい形にする。

# 既知の問題・メモ

- 部屋IDは **許容文字のランダム5桁**（大文字・I/O/Z 禁止）であり、**辞書順など恣意的な順序で候補を決めない**。複数候補時は補正後テキスト上の **出現順（左から最初の一致）** のみで選ぶ。
- OCR により **Q と 0 の誤認**はフォント依存で起こりうる。有効文字セット上は Q も正当（`CHAR_CORRECTION_MAP` では Q を 0 に寄せていない）。
- `CTkComboBox` は背景 `transparent` 不可のため、テーマに合わせた色を直接指定している。
- ツールチップ `Toplevel` は親が最前面のとき隠れるため、ツールチップ側に `-topmost` を設定している。
- クリップボード履歴削除は **環境によっては効かない**（仕様）。

# ドキュメントについて

- **現在の仕様の正**: 本ファイル（`docs/project_smash-room-ocr.md`）。
- **`docs/development_log.md`**: 経緯・検討メモ。過去の「次ステップ」と現状が食い違う場合は **本仕様を優先**。

# 最終更新日

2026-04-16（ルート整理: `gui_app.py` の後方互換シムを撤去し、`main.py`・`tools/test_boot.py`・`scripts/_treq.py` の import を `gui.main_window` へ統一。ルート直下ファイルを 1 つ削減し、実装の参照先を `gui/` パッケージへ一本化。）

2026-04-16（Chrome 拡張: `content.js` / `options.html` で **Enter / Space / Escape / Backspace** を `chrome.storage.sync`（`keyboardShortcutEnter`・`keyboardShortcutSpace`・`keyboardShortcutEscape`・`keyboardShortcutBackspace`）で **個別 ON/OFF**（既定すべて ON）。他拡張とのキー競合を避けられる。manifest `1.1.7`。）

2026-04-16（Chrome 拡張 `content.js`: **Space** を **Enter** と同じ「確定」キーとして扱う（`isManualPrimaryActionKey`）。部屋ID欄での **「設定/変更」** 送信・**前回の部屋IDを呼び出す**の優先クリック・SweetAlert の **OK** が Space でも可能。manifest `1.1.6`。）

2026-04-16（Chrome 拡張 `content.js`: 部屋ID欄が**空**のときは **SSE 由来の入力反映を先頭 1 回だけスキップ**し、2 回目以降から反映（空欄に戻したら再武装。手入力で非空になったら武装解除）。`pageshow`・`popstate`・600ms ポーリングで pathname 変化を検知し rate プロフィール切替時は `lastAppliedRoomId` をリセット。空欄時に表示される **「前回の部屋IDを呼び出す」** 相当の `span.cursor`（文言に「前回」「呼び出」を含む）がある場合は、部屋ID欄で **Enter** したとき **`matching_post_btn` より当該要素を優先クリック**。`SELECTORS.md` に前回ID呼び出しの注意書きを追加。manifest `1.1.5`。）

2026-04-16（Chrome 拡張の全体ブラッシュアップ: `background.js` の `setConnectionState` で状態・詳細が変わらないときはツールバー `setIcon`/`setTitle` をスキップし、ホットパス負荷を抑える。`broadcastRoomId` は rate タブキャッシュが空なら早期 return。`options.js` は `persistBridgeEnabled` / `persistAutoClickOnly` の重複を `persistSyncSettings` に集約。利用者向け `chrome-extension/README.md` の文言を「PC アプリと連携する」「と連携」に統一。本設計書の `options.*` 行を現 UI（自動保存・詳細ダイアログのポート・接続テストボタンなし）に合わせて更新。）

2026-04-16（Chrome 拡張の堅牢化: `rebuildRateProfileTabCache` を単一フライト化し `tabs.query` の並行レースを防止。`broadcastRoomId` は一時的な `sendMessage` 失敗でタブをキャッシュから落とさない。バッジ更新は `chrome.action` 例外を握りつぶし。`options.js` は主要 DOM の null ガード。`content.js` は `storage.sync` 読み込み失敗時は自動クリックをオフ扱い。）

2026-04-16（Chrome 拡張: `content.js` の SweetAlert キャンセル操作に **Backspace** を追加。Escape と同様にキャンセルボタン相当のクリックを発火するが、部屋ID欄・チャット等の編集入力にフォーカスがあるときは従来どおりショートカットを奪わない。）

2026-04-15（Chrome 拡張デザイン改善: `options.html/js` の接続状態表示を色分け（成功/警告/エラー）＋ヒント文言付きに更新。接続テスト実行中はボタン文言を切り替えて待機状態を明確化し、ポート欄にライブバリデーション（エラー表示・保存ボタン無効化）を追加して設定ミスを事前に防止。）

2026-04-15（Chrome 拡張ブラッシュアップ: `options.js` の接続状態取得を同時1本に集約し、ポップアップ可視時のみ 4 秒ポーリングするよう最適化。接続中に無通信が 60 秒を超えた場合は「受信待ち N秒」を表示して切り分けしやすくした。`background.js` は runtime status の `detail` を短く正規化して UI 崩れを防止。）

2026-04-15（P0/P1実装: GUI の `ExtensionBridgeMixin` を非同期同期方式に変更し、`_sync_extension_bridge_listen()` の `stop()/join` 待機が UI スレッドを塞がないよう改善。Chrome 拡張 `background.js` は SSE read timeout（45秒）を導入し、Python 側 `extension_bridge_server.py` の heartbeat（15秒）と組み合わせて無通信ハングを検知して再接続できるようにした。）

2026-04-15（P0/P1実装: `background.js` に rate プロフィールタブキャッシュを追加し、配信ごとの `tabs.query` を削減。`options.js/html` には接続状態表示・接続テスト・ポート入力バリデーション・保存失敗メッセージを追加し、初回導入チェックリストで導線を明確化。併せて `README` を更新し初回3ステップを明記。）

2026-04-15（テスト補強: `tests/test_extension_bridge_server.py` に SSE 実接続でのリプレイ/heartbeat確認と stop/notify 競合回帰を追加。加えて `docs/extension-bridge-test-plan.md` を新設し、拡張側（background/content/options）を含む回帰確認手順を整理。）

2026-04-15（Chrome 拡張最適化: `background.js` の `refreshConnection` を調整し、同一ポートで接続中なら既存 SSE を維持して再接続しないようにした。これにより、`tabs.onUpdated` の連続発火時でも不要な abort/reconnect を抑え、接続のチラつきとローカル負荷を低減。併せて `content.js` は SSE 受信時の入力反映で `disabled/readOnly` な部屋ID欄を更新しないガードを追加し、サイト状態に反した強制上書きを防止。）

2026-04-15（Chrome 拡張ブラッシュアップ: `content.js` の重複スキップ条件を調整し、`lastAppliedRoomId` が同一でも入力欄の現在値が異なる場合は再反映するよう修正。これにより、手動編集やサイト側更新で値がズレた後に同じ部屋IDを再受信しても復元できる。併せて SweetAlert ショートカットの「他編集欄ガード」を `closest("input, textarea, select, [contenteditable]")` ベースに強化し、`contenteditable` の子要素にフォーカスがあるケースでも Enter/Escape を奪わないようにした。フォーカス復帰タイマーも 1 本化して不要な多重 `setTimeout` を抑制。）

2026-04-15（不具合修正: `content.js` で SweetAlert 用キーボードショートカットに追加ガードを入れ、`input.room_matching_id` にフォーカス中は Enter/Escape の SWAL 処理を走らせないようにした。これにより、キャンセル後に部屋ID欄へフォーカスが戻った状態でも Enter で再度「設定/変更」ボタン押下が機能し続ける。）

2026-04-15（Chrome 拡張ブラッシュアップ: `content.js` の auto-click 判定を「予約時」ではなく**実クリック直前**に再判定・記録する方式へ修正し、ボタン無効化などでクリック不成立だった場合にクールダウンだけ進んでしまう不整合を解消。併せて Enter ショートカットで `readonly/disabled` な部屋ID欄を無視、SweetAlert ショートカットの編集要素判定に `select` を含めて他入力との干渉をさらに抑制。`background.js` は `refreshConnection` に世代ガードを追加し、タブ更新連打時の非同期レースで古い再接続処理が後勝ちする可能性を抑止。）

2026-04-15（Chrome 拡張: 確認ダイアログの「キャンセル」**ボタンをクリック**した場合も `input.room_matching_id` へフォーカスを戻すよう `content.js` を補強。Escape キャンセル時だけでなくマウス操作でも、直後に部屋ID欄へ再入力しやすくした。）

2026-04-15（Chrome 拡張: `content.js` の Enter/Escape ショートカットに「編集フィールド非干渉」ガードを追加。`input.room_matching_id` 以外（チャット欄・他 input/textarea/contenteditable）での入力中はショートカット処理をスキップし、対戦ルーム内チャットの Enter 操作と競合しないようにした。）

2026-04-15（Chrome 拡張: `content.js` で SweetAlert を Escape キャンセルした直後、`input.room_matching_id` へフォーカスを戻すよう修正。これにより、キャンセル後に Enter をもう一度押すだけで再び「変更」フローへ入りやすくなり、キーボード操作の詰まりを解消。）

2026-04-15（Chrome 拡張: `content.js` のキーボードイベント登録を **同一ページで1回だけ**に制限し、拡張の再注入時に Enter/Escape ハンドラが多重発火して重複クリックする事故を防止。SweetAlert のショートカット判定も Enter/Escape のときだけ DOM を探索するようにしてキー入力時のオーバーヘッドを低減。）

2026-04-15（Chrome 拡張: `content.js` で確認ダイアログ（SweetAlert）のキーボード操作を追加。表示中は **Enter=OK / Escape=キャンセル**で押下可能にし、マウスなしでも確定/取り消しできるようにした。）

2026-04-15（Chrome 拡張: `content.js` の送信ボタン判定を強化。`display/visibility` に加え `getClientRects()` で可視性を確認し、`disabled` の `matching_post_btn` には auto-click / Enter 送信ともに `click()` しないようにして誤送信・空振りを防止。）

2026-04-15（Chrome 拡張: `content.js` に手入力向けの Enter キー送信を追加。`input.room_matching_id` で Enter 押下時に `matching_post_btn` をクリック扱いにし、デスクトップアプリ未導入でも拡張単体で送信しやすくした。）

2026-04-15（安全性調整: `content.js` の auto-click に **15秒クールダウン** と **同一ID 2分TTL 再クリック抑制**を追加。`ConfigManager` の `detection_poll_fast_sec` 下限を **0.2秒** に引き上げ、OBS 併用時の過負荷リスクを低減。`manifest` の `host_permissions` は `https://smashmate.net/rate/*` へ縮小。）

2026-04-15（Chrome 拡張: rate プロフィールタブが無いときは SSE を張らない（`background.js` の `hasAnyRateProfileTab` + `tabs.onUpdated` / `onRemoved`）。コンテンツスクリプト注入を `manifest` の `matches` を `https://smashmate.net/rate/*` に限定。manifest `1.1.3`。）

2026-04-15（拡張連携のコードレビュー反映: GUI の拡張 SSE まわりを `gui/mixins/extension_bridge.py` に集約。Chrome 拡張に `constants.js`（パス・既定ポート・SSE バッファ上限の単一化）、`background.js` のストリームバッファ上限、`content.js` の部屋ID形式検証（`ROOM_ID_PATTERN` 相当）、`tests/test_extension_bridge_server.py` に `_format_listen_error` の回帰テスト。manifest `1.1.2`。）

2026-04-15（`assets/samples/test_screen.png` を `test_screen_4Q1PG_4QIPG.png` にリネームし正解 4Q1PG をファイル名で固定。`test_sample_suite.py` の期待付きサンプルを 8/8 に。`test_pipeline.py` のローカル画像パスを追随。）

2026-04-15（配布・低スペック向けレビュー反映: `ImageProcessor` の 1080p 正規化リサイズを縮小／拡大で補間分岐、ROI 拡大を `INTER_LINEAR` 化。`OCRWorker` は `find_and_extract_roi` / `extract_room_id_from_text` を `asyncio.to_thread` で実行。履歴トリガー幅は `_recent_ids` 不変時に計測結果を再利用。`_build_ui` 末尾の二重 `update()` を整理。）

2026-04-15（拡張連携レビュー反映: `ExtensionBridgeServer` に SSE キュー満杯時の古いイベント捨て + 最新優先 `_enqueue_sse_queue`、待受成功時の `on_listen_ok`（GUI ステータスを監視中へ復帰）。Chrome 拡張は `shared-path.js` で pathname 判定を共通化、`background.js` に `SSE_PATH`・再接続ジッター・タブへの並列 `sendMessage`。`content.js` は `autoClickMatchingPostBtn` を storage キャッシュ化。）

2026-04-15（コードレビュー: `OCRWorker` に `_sleep_while_running` を追加し、`stop_worker` 後も長い `asyncio.sleep` でワーカースレッド終了が遅れないよう監視ループの待機を分割。起動時自動接続の初期待機・リトライ間隔・最大試行を `gui/constants.py` の `AUTO_START_*` に集約。）

2026-04-15（拡張・連携の UI: `options.html` をカード型レイアウト・ライト/ダーク対応・接続 URL ライブプレビュー・SSE OFF 時のポート無効化・Enter 保存・`storage` 同期反映に刷新。manifest `1.1.1`。デスクトップ GUI は拡張行を「🔗 拡張連携」「拡張用ポート」表記とツールチップ文言で OBS ポートと区別しやすく整理。`content.js` の入力反映ハイライトをダークモード向け色＋`outlineOffset` で視認性改善。）

2026-04-15（リファクタ: 肥大化していた `gui_app.py` を `gui/` パッケージへ分割。定数・ツールチップ・トレイ画像生成・接続カード／履歴 UI をモジュール化し、メインクラスは `gui/main_window.py` に集約。ルートの `gui_app.py` は互換シム。）

2026-04-15（レビュー反映: `AppConfig` に部屋ID確定用 `detection_*` 3 項目を追加し `to_detection_config()` で `RoomIdDetector` に接続。`ConfigManager._sanitize_config` でクランプ（`poll_slow` は `poll_fast` 未満にならないよう補正）。`OCRWorker` は監視オフのループで `reset_pending_only()` し再開時の誤確定を抑制。`obs_capture` の未使用 `TYPE_CHECKING` を削除。`tests/test_config_manager.py` に検出設定の回帰テストを追加。）

2026-04-15（拡張: オプション `autoClickMatchingPostBtn`（既定 false）で、部屋ID反映後に `matching_post_btn` を `click()`。`content.js` は `chrome.storage.sync` を参照し、メッセージハンドラを非同期化。`options.html` / `options.js` / `SELECTORS.md` / `chrome-extension/README.md` / manifest `1.1.0` を更新。）

2026-04-15（レビュー反映: `extension_bridge_server` の `notify_room_id` で SSE 用に改行除去・空は無視。bind 失敗時は `_last_confirmed_id` も破棄。`ConfigManager._app_config_from_json_dict` で `load` の重複を削減。`gui_app._save_config` の OBS ポート既定を `obs_capture.DEFAULT_PORT` に合わせる。`OCRWorker` にスレッド／コールバック前提の短い docstring。）

2026-04-15（拡張連携の実装レビュー: Listen 終了時に `_last_confirmed_id` を破棄して古い部屋のリプレイを防ぐ。`STOP_JOIN_TIMEOUT_SEC` で join 上限を 4 秒に整理。`gui_app` は拡張の有効/ポートが変わった保存時だけ `_sync_extension_bridge_listen`、`_extension_bridge_sync_lock` で `stop` を直列化、`_safe_on_confirmed_id_bridge` で `notify` を例外防御。`_save_config` のポートは `ConfigManager.save` にクランプを一元化。）

2026-04-15（`chrome-extension/content.js`: 送信ボタンを `button.matching_post_btn` のみでゲート（初回「設定」／以降「変更」など文言に非依存）。`SELECTORS.md` / `README.md` / 設計書ファイル表を追記。）

2026-04-15（`chrome-extension/manifest.json`: ツールバーアイコンに `default_popup`（`options.html`）を設定し、クリックで設定ポップアップを表示。`README.md` のインストール手順を追記。）

2026-04-15（`chrome-extension/content.js`: 部屋ID入力を `input.room_matching_id[name="room_matching_id"]` 優先（実ページの `type="url"` に対応）。フォールバック探索に `input[type="url"]` を含める。`SELECTORS.md` に入力前後・変更ボタンの HTML 例を追記。）

2026-04-15（`chrome-extension/` に Chrome 拡張（MV3）を追加: ローカル SSE を `fetch` で購読、`/rate/<数>/` の pathname のみ入力補助、オプションでポート・接続 ON/OFF、`README.md` / `SELECTORS.md`。本節の「拡張はリポジトリに含めない」記述を実態に合わせて更新。）

2026-04-15（メンテナンス: `ConfigManager.load` の既知キー列挙を `dataclasses.fields(AppConfig)` に変更（`__dataclass_fields__` 非推奨回避）。`OCRWorker.run` の `finally` で `is_running=False` を保証。`RoomIdDetector` の docstring を `acknowledge_copy` との役割分担に合わせて修正。`gui_app` 先頭 docstring の箇条書き体裁を整理。**同日追記**: 拡張連携既定ポートを `DEFAULT_EXTENSION_BRIDGE_PORT` に集約。`OCRWorker._apply_confirmed_id` で確定時のクリップボード／コールバックを集約。`gui_app._dispatch_ui` で別スレッド→UI の `after(0, …)` と終了ガードを共通化。）

2026-04-15（拡張連携: `AppConfig.extension_bridge_*`・ローカル SSE サーバー `extension_bridge_server.py`・GUI トグル＋ポート、`GET /events`・監視中のみ Listen・設計書に本節を追記。Chrome 拡張本体は未実装。**同日追記**: `_full_destroy` で `extension_bridge.stop()` を try/except 化。`notify_room_id` は Listen 完了前でも直近 ID を保持し、待受後の新規接続でリプレイ可能に。**同日追記**: `notify_room_id` の `call_soon_threadsafe` を `RuntimeError` で握りつぶし、`_client_queues` を `_queues_lock` で保護。）

2026-04-15（`pyperclip.copy` 失敗時は `on_id_found` と `acknowledge_copy` をスキップし GUI の「コピーしました」とクリップボードの齟齬を防ぐ。`last_copied_id` はコピー成功後のみ更新。SSE は確定のたびに通知。）

2026-04-14（公開向けの構成整理: 設計/開発ログを `docs/`、ビルド補助を `scripts/`、手動検証スクリプトを `tools/`、テンプレート/サンプル画像を `assets/` 配下へ移動。`gui_app.py` とビルドスクリプトの参照パスを新構成に追従。）

2026-04-07（`main.py` の単一起動制御を調整。二重起動時メッセージ表示を廃止し、既存インスタンスの前面化要求のみ行って新規インスタンスは終了する方式に変更。）

2026-04-07（`extract_room_id_from_text`: 複数候補時の `_pick_best_room_id`（辞書順・`401P6`/`4Q1PG` 特例）を廃止し、補正後テキスト上の左から最初の一致 `_pick_room_id_by_text_order` のみで決定。）

2026-04-07（OCR前処理を再調整: ブラー廃止、ROIノイズ帯トリミング、固定閾値 `160` 採用。`extract_room_id_from_text` で直接候補優先に変更し、誤って `Q→0` / `G→6` に倒れるケースを低減。`test_sample_suite.py` 追加、提供サンプル 7/7 正解を確認。）

2026-04-07（`DetectionConfig` にポーリング間隔を集約・`AppConfig.to_obs_connection_config` 追加・設計書に設定方針を追記。併せて過去の「開発用デバッグログ削除・`ocr_engine` 簡素化・Pillow 明示・`obs_capture` 未使用 import 削除」。同日: コピー成功時の監視ボタン横ランプのフラッシュ色を緑から白へ変更）

2026-04-07（追記）: `gui_app.py` に残っていたレイアウト計測用 JSON ファイル追記（エージェント用デバッグ）を削除し、設計書の「本番ではファイル追記しない」と整合。`image_processor.py` モジュール先頭のテンプレ照合順の説明を `find_and_extract_roi` の実装に合わせて修正。

2026-04-07（ブラッシュアップ）: `gui_app.py` の履歴トリガー幅計算を軽量化（フォント計測器をキャッシュ、幅不変時は再レイアウトしない）。`obs_capture.py` で未接続時の早期 return と base64 payload 切り出しの簡素化を追加。`image_processor.py` で極小 ROI 時の空配列トリミングを安全に回避するガードを追加。

2026-04-07（終了処理の統一）: `gui_app.py` で `WM_DELETE_WINDOW` をトレイ最小化から終了要求へ変更。`_request_shutdown()` / `_full_destroy()` を追加し、`×` とトレイ「終了」を共通の終了シーケンスに統一。終了時はワーカー停止（`stop_worker` + `join(timeout=3.0)`）→トレイ停止→GUI破棄の順で実行し、`_is_shutting_down` / `_is_destroying` で二重終了を防止。

2026-04-07（終了処理の安定化）: `gui_app.py` の終了系をブラッシュアップし、ワーカー停止処理を `_stop_worker()` に共通化。`×` / トレイ終了 / `destroy()` の全経路で同一処理に収束し、`stop_worker`・`join`・`tray_icon.stop` の各失敗時も例外を握り潰さずログを残して終了シーケンスを継続するようにした。加えて、終了開始後は UI 更新系コールバック（`_safe_update_*`）の `after` 投入を抑止して、破棄中の `TclError` ノイズと後追い更新を防止。`main.py` では単一起動リスナー終了処理を強化し、待受スレッドの `WaitForSingleObject` / UI 通知 / `SetEvent` / `join` / `CloseHandle` を安全化して、終了時のハンドル解放漏れとスレッド残留リスクを低減。

2026-04-07（全体ブラッシュアップ）: `OCRWorker` を `ocr_worker.py` に分離。`pipeline_profile.py` で監視ループのフェーズ計測（`SMASH_ROOM_OCR_PROFILE`）。`OBS` 取得を `asyncio.to_thread` 化し、`decode_screenshot_payload` をテスト可能に分離。`config_manager` に原子的保存・バックアップ・数値サニタイズ・スクショ用 `AppConfig` フィールドを追加。`image_processor` に粗い照合による早期スキップと `O` 分岐列挙の上限（`MAX_O_BRANCH_POSITIONS`）。`ocr_engine` で BGRA を `ascontiguousarray` 化。`tests/` に `pytest` 回帰テスト追加。`requirements.txt` に `pytest` を追記。
