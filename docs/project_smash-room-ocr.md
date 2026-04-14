# smash-room-ocr プロジェクト仕様・設計

OBS WebSocket 機能を利用し、スマブラSPの配信・録画画面から「部屋ID」を WinRT OCR で読み取り、クリップボードへ自動コピーおよび通知を行う **Windows 専用**のデスクトップ支援ツール。

# 技術スタック

- **言語**: Python 3.10+
- **GUI**: `customtkinter`, `tkinter`
- **画像処理**: `opencv-python`, `numpy`（二値化、ROI、テンプレートマッチング）
- **OCR**: `winsdk`（Windows 10/11 WinRT OCR）
- **OBS**: `obsws-python`（WebSocket v5・ソースのスクリーンショット取得）
- **その他**: `pystray` / `Pillow`（トレイアイコン描画。`requirements.txt` に明示）、`pyperclip`（クリップボード）、`winsound`（通知音）、`pyinstaller`（exe ビルド用）

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
- **レイアウト**: `frame_dynamic` にカード・`frame_run_middle`（監視＋ステータス）のみを置き `expand=True` で伸縮。**下端**は `frame_toggles` を先に `pack(side="bottom")` し、その上にインデント付きの細い区切り線（`frame_bottom_separator`）、その上に `frame_dynamic` を `pack(side="top", expand=True)`。状態切替では **トグル帯と区切り線は pack し直さない**（見切れ防止）。**Z 順**: 巨大ID帯は `frame_dynamic` より **先に** `pack` されるが、後から `pack` したウィジェットが手前に描画されるため、構築後に `_frame_id_outer.lift()` で ID 帯を前面へ（ヒント「クリックで再コピー」が角丸カードに隠れないようにする）。
- **動的中間は `grid`**: 状態A/B の切替で OBS/ソースの**カード枠**は `grid_forget` せず行の付け替えのみ（点滅軽減）。可変行（スペーサー・`frame_run_middle`）だけ `grid_forget`。
- **ウィンドウ高さ**: 起動完了時に **`_compute_fixed_window_height`** で `_fixed_window_height` を確定。状態切替のたびに **`_fit_window_height_to_content`** を **同一イベント内で即時**呼び、その後 **`update()`** で描画を確定する（遅延 `after` は使わず、段階的リサイズに見える挙動を防ぐ）。角丸が親で切れないよう、固定値は setup/run 両方の実寸に基づく。**起動時**: UI 構築・縦幅スナップまで **`withdraw()`** し、完了後 **`deiconify()`** で初めて表示する（暫定寸法の一瞬表示を防ぐ）。
- **区切り線**: 高さ `BOTTOM_SEPARATOR_HEIGHT`（2px。DPI により 1px が消えるのを防ぐ）。色は `_get_bottom_separator_color()`（ダークでは履歴枠と同じ `HISTORY_BORDER` / `#555555`、ライトでは `#666666`）。`BOTTOM_SEPARATOR_PADY_TOP`（5px）で上側余白（監視クラスタ〜区切りの見た目バランス用に調整）。区切りとトグルを `lift()`。
- **状態A**: OBS 展開、対象ソースは畳み。スペーサーは **対象ソースカードの下** に置き余白を吸収（カード同士の間には伸びない）。監視ボタン＋`label_status` は非表示。セットアップ時にステータス行が見えないため、接続エラー時は（状態Aなら）`messagebox` で補足。
- **状態B**: OBS 畳み、対象ソース展開、監視行＋`label_status` を `frame_run_cluster`（親は `tk.Frame` の `frame_run_middle`）に載せ、`frame_run_middle` 内は **`grid` の行ウェイト**（上スペーサー＞下スペーサー）でソース直下〜区切り線付近の帯に縦配置。`frame_run_middle` の `grid` 余白は `RUN_MIDDLE_GRID_PADY`（既定 `(4, 1)`）。ボタン行（`frame_ctrl`）と `label_status` の間は `RUN_CLUSTER_BTN_STATUS_GAP`（既定 6px）。接続完了（`_safe_update_sources`）で自動的に状態Bへ。
- **切断時の扱い**: OBS 側切断時は **状態Aへ戻し**、`label_status` に加えて setup 側で常に見える OBS カード内ラベル（`label_setup_status`）にも「再接続してください」を表示する。切断通知の `messagebox` は表示しない。
- **初期表示（近似）**: `auto_start` かつ `target_source` が空でないときは起動時から状態B。
- **自動接続フラグ**: OBS 接続成否や切断イベントでは `auto_start` を変更しない。`⚡ 自動接続` チェックボックスの操作時のみ `config.json` に保存される。

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
| `main.py` | エントリ。ルートロガー＋`image_processor` 用ログ初期化、単一起動（Mutex）、既存インスタンス前面化イベントの受信。 |
| `gui_app.py` | UI、トレイ、履歴UI（監視ワーカーは `ocr_worker.py`）。 |
| `ocr_worker.py` | `OCRWorker`（`threading` + `asyncio`）：OBS 取得→ROI→OCR→確定。 |
| `pipeline_profile.py` | 監視ループのフェーズ時間計測（環境変数で有効化）。 |
| `room_id_detector.py` | 部屋ID確定のステートマシン（`reset_pending_only` 等）。 |
| `clipboard_history_win.py` | Windows クリップボード履歴のテキスト一致削除（非Windowsでは no-op）。 |
| `image_processor.py` | テンプレ・ROI・前処理・ID正規表現抽出。 |
| `ocr_engine.py` | WinRT OCR（`WinRTOcrEngine` のみ。差し替え時は同契約のクラスで可）。 |
| `obs_capture.py` | OBS WebSocket スクショ取得。 |
| `config_manager.py` | 設定 JSON の読み書き（原子的保存・バックアップ・数値サニタイズ）。 |
| `run_app.bat` | venv 有効化して起動。 |
| `tests/` | `pytest` による回帰テスト（検出ロジック・テキスト抽出・デコード・設定）。 |
| `pytest.ini` | pytest の `testpaths=tests`。 |
| `tools/test_pipeline.py` | ローカル画像 / OBS 連携の統合検証スクリプト。 |
| `tools/test_boot.py` | 短時間の起動スモーク。 |
| `scripts/_treq.py` | 開発用: 接続カード setup/run の要請高さをコンソールに出すワンオフ（本番起動経路では未使用）。 |
| `assets/templates/` | テンプレート画像（`arenahere*.png` など）。 |
| `assets/samples/` | OCR 回帰確認に使うサンプル画像群。 |

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
- 回帰確認用に `tools/test_sample_suite.py` を追加し、`test_screen_<正解>_<誤読>.png` 規約の固定サンプルで一括検証できるようにした（今回サンプルで 7/7 正解）。

# 軽量化・構成の方針（2026-04 整理）

- **実行時の無駄を減らす**: 不要なファイル I/O・デバッグ用フックを本番コードから外す。
- **依存の明示**: GUI が `Pillow` でトレイ画像を生成するため `requirements.txt` に記載（従来は間接依存のみの可能性あり）。
- **OCR モジュール**: 単一実装のため抽象基底クラスは置かず、`WinRTOcrEngine` の `recognize` 契約で差し替え可能とする。
- **設定の単一ソース**（実行時コストは増やさない）:
  - `AppConfig.to_obs_connection_config()` で `ObsConnectionConfig` を生成し、ホスト／ポート／パスワードの重複指定を避ける。
  - `AppConfig` に **スクショ取得パラメータ**を追加: `screenshot_width` / `screenshot_height` / `screenshot_quality` / `screenshot_format`（`config.json` で上書き可能。`ConfigManager.load` で範囲サニタイズ）。
  - `config.json` の保存は **一時ファイル→`os.replace`** で原子的に行い、上書き前に `config.json.bak` へ退避。読み込み失敗時はバックアップを試す。
  - `RoomIdDetector` のポーリング間隔（`poll_fast` / `poll_slow`）は `DetectionConfig` に含め、確定ロジックと同じ dataclass で調整可能にする。`RoomIdDetector.poll_fast` 等は `_cfg` を参照するプロパティ（読み取り専用）。
- **UI の軽量最適化**:
  - 履歴トリガー幅計算で使用する `tkfont.Font` は毎回再生成せずキャッシュする。
  - 履歴トリガー幅が前回と同じ場合は `configure(width=...)` をスキップし、不要な再レイアウトを減らす。
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
