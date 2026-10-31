# DOM セレクタ（要メンテ）

サイト改修で **壊れる可能性**があります。動かなくなったら開発者ツールで該当要素を確認し、定数を更新してください。

---

## スマッチ（`smatch-jp.com`）— 第1段（自動ペーストのみ）

確認日: 2026-10-31（ホスト／募集中・ルーム `#27847`）

実装: [`content-smatch.js`](content-smatch.js)

### 部屋ID入力

```html
<form class="arena-form" id="arenaForm">
  <input class="form-control" name="arena_id" maxlength="5" placeholder="ABCDE" value="" autocomplete="off">
  <button class="btn btn-primary" type="submit">設定</button>
</form>
```

- 入力: `form#arenaForm input[name="arena_id"]`
- フォーム: `form#arenaForm`
- 確定ボタン: `#arenaForm button[type="submit"]`（文言「設定」）— **第1段では自動 click しない**

### ホスト目印

```html
<b class="host-mark">部屋を立てる人</b>
```

- セレクタ: `b.host-mark`
- 案内文言例: `専用部屋を立てて、部屋IDを入れてください。`
- 未設定: `div.bold.red`「部屋IDが未設定です」

### 触らない

- `#commentForm` / サイト内検索 `#searchForm`
- パスワード表示（配信者は独自桁になりうる）
- 部屋ID帯 `.af-arena` / `.af-close`
- 待ち時間ミニゲーム（`.rv-cell` / `.cs-cell` / `.sg-cell` / `.gm-cell`）

### 未確認

- ゲスト（入る側）画面の DOM。取得後に「書かない」ゲートを厳しくする。

---

## スマメイト（`smashmate.net`）— 旧サイト

実装: [`content.js`](content.js)

### 部屋ID入力欄（優先）

実ページで確認したマークアップ例:

入力前:

```html
<input class="width100 form-control room_matching_id" name="room_matching_id" type="url" value placeholder="部屋IDを入力">
```

入力後:

```html
<input class="width100 form-control room_matching_id" name="room_matching_id" type="url" value="2M4TR" placeholder="部屋IDを入力">
```

拡張では次を **最優先**（`type` は `url` のため、汎用の `input[type=text]` だけの探索では拾えない）:

- `input.room_matching_id[name="room_matching_id"]`

定数: `ROOM_MATCHING_INPUT_SELECTOR`（[`content.js`](content.js)）

一致しない場合のみ、`matching_post_btn` 周辺のフォールバック探索に回します。

### 送信ボタン（ゲート・ラベル非依存）

同一クラスで、**初回のみ**ボタン文言が「設定」、**2回目以降**は「変更」になることがある。将来文言が変わっても、**クラス `matching_post_btn` が付いた `button` が存在するか**だけでゲートする（ラベルテキストは見ない）。

初回:

```html
<button class="width100 btn btn-default bold matching_post_btn">設定</button>
```

2回目以降の例:

```html
<button class="width100 btn btn-default bold matching_post_btn">変更</button>
```

拡張でのセレクタ（幅広のクラス列に依存しない最小形）:

- `button.matching_post_btn`

定数: `MATCHING_POST_BUTTON_SELECTOR`（[`content.js`](content.js)）

このボタンが DOM にないページでは **入力反映を行いません**（誤った画面への書き込み防止）。

### 「前回の部屋IDを呼び出す」（要メンテ）

新規対戦ルーム作成直後などに表示されることがある **テキストリンク**（例: `⇒前回の部屋IDを呼び出す`）。実ページでは **`span.cursor`** で、文言はサイト改修で変わりうる。

拡張では **`span.cursor`** を列挙し、表示テキストに **「前回」** と **「呼び出」** の両方を含む要素を **Enter / Space 優先クリック**の対象にする（[`content.js`](content.js) の `PREV_ROOM_RECALL_SPAN_SELECTOR` / `findPrevRoomRecallControl`）。

### 送信ボタンの自動クリック（オプション）

`chrome.storage.sync` のキー **`autoClickMatchingPostBtn`** が `true` のとき、[`content.js`](content.js) は部屋IDを入れたあと **同じセレクタのボタンを再取得して `click()`** します（`setTimeout(0)` で 1 ティック遅延）。既定は `false` です。**スマッチ第1段では未使用。**
