# Chrome拡張・SSE 回帰テスト計画

この文書は、`background.js` / `content.js` / `options.js` と Python 側 SSE サーバーの改修で壊れやすい箇所を、継続的に確認するためのチェックリストです。

## 1) 自動テスト（pytest）

- 対象: `tests/test_extension_bridge_server.py`
- 目的:
  - `GET /events` の接続で直近 ID がリプレイされること
  - 無通信時 heartbeat が送られること
  - `stop()` 中に `notify_room_id()` が並行してもハングしないこと

## 2) 拡張の手動スモーク（毎リリース）

- 対象: `chrome-extension/background.js`, `chrome-extension/options.js`, `chrome-extension/content.js`
- 手順:
  1. `bridgeEnabled=ON`, `bridgePort` をデスクトップ側と一致させる
  2. `https://smashmate.net/rate/<数字>/` タブを1枚開く
  3. オプションの「接続テスト」を実行し成功すること
  4. デスクトップ監視でIDを確定し、入力欄反映を確認
  5. 同一ID連投時に過剰クリックされないこと（15秒CD + 同一ID TTL）
  6. `rate` タブを全部閉じると接続が停止状態へ遷移すること

## 3) 障害注入テスト（手動）

- デスクトップアプリ停止時:
  - 拡張の接続状態が `再試行中` または `接続エラー` へ遷移する
- ポート不一致時:
  - オプションの接続テストが失敗し、理由が表示される
- `rate` 以外のページのみ開いている時:
  - 接続状態が `rateプロフィールページのタブ待ち` になる

## 4) 将来の自動化候補

- Playwright で options 画面の保存・接続テストUIをE2E化
- Chrome Extension Test Runner 等で `background.js` の状態遷移をモック検証
- `content.js` のキーボードショートカット判定を DOM モックで単体テスト化
