# DOM セレクタ（要メンテ）

スマメイトのマークアップ変更で **壊れる可能性**があります。動かなくなったら開発者ツールで該当要素を確認し、`content.js` 先頭の定数を更新してください。

## 部屋ID入力欄（優先）

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

## 送信ボタン（ゲート・ラベル非依存）

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

## 送信ボタンの自動クリック（オプション）

`chrome.storage.sync` のキー **`autoClickMatchingPostBtn`** が `true` のとき、[`content.js`](content.js) は部屋IDを入れたあと **同じセレクタのボタンを再取得して `click()`** します（`setTimeout(0)` で 1 ティック遅延）。既定は `false` です。
