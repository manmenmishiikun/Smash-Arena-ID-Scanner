/**
 * smashmate.net 上で pathname が rate プロフィール形式のときのみ動作。
 * URL パス中の数値はユーザー識別子であり、SSE の部屋コードではない。
 *
 * 送信系ボタン（クラス `matching_post_btn`）が DOM にある場合のみ入力反映。表示文言は「設定」
 * （初回）／「変更」（2回目以降）など可変のため、**ラベル文字列には依存しない**（サイト改修で要メンテ）。
 * 部屋ID入力は実ページの `input.room_matching_id`（`type="url"`）を優先。
 * オプション ON のとき、入力後に同ボタンを `click()`（サイト側の確認ダイアログはユーザー操作前提）。
 */

/** @type {string | null} */
let lastAppliedRoomId = null;

/** サイト改修で要メンテ。文言ではなく `matching_post_btn` のみで判定する */
const MATCHING_POST_BUTTON_SELECTOR = "button.matching_post_btn";

/**
 * 部屋ID入力（実サイトでは type="url"）
 * 例: <input class="width100 form-control room_matching_id" name="room_matching_id" type="url" ...>
 */
const ROOM_MATCHING_INPUT_SELECTOR =
  'input.room_matching_id[name="room_matching_id"]';

/** 防御: デスクトップの抽出に委ね、長さのみ制限 */
const MAX_ROOM_CODE_LENGTH = 64;

/** Python `image_processor.ROOM_ID_PATTERN` と同じ（I / O / Z 除外の 5 文字） */
const ROOM_ID_RE = /^[A-HJ-NP-Y0-9]{5}$/;

/** `autoClickMatchingPostBtn` を毎回 storage 読みしない（onChanged で同期） */
let _autoClickCache = false;
let _autoClickLoaded = false;

async function getAutoClickMatchingPostBtn() {
  if (_autoClickLoaded) return _autoClickCache;
  const r = await chrome.storage.sync.get({ autoClickMatchingPostBtn: false });
  _autoClickCache = Boolean(r.autoClickMatchingPostBtn);
  _autoClickLoaded = true;
  return _autoClickCache;
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "sync" && changes.autoClickMatchingPostBtn) {
    _autoClickCache = Boolean(changes.autoClickMatchingPostBtn.newValue);
    _autoClickLoaded = true;
  }
});

/**
 * 明示セレクタで取得。見つからない／非表示のときは null。
 * @returns {HTMLInputElement | null}
 */
function findRoomMatchingInputPrimary() {
  const el = document.querySelector(ROOM_MATCHING_INPUT_SELECTOR);
  if (el instanceof HTMLInputElement && isVisible(el)) {
    return el;
  }
  return null;
}

/**
 * `matching_post_btn` 周辺から部屋コード用 input を推定（セレクタ変更時のフォールバック）
 * type="url" も対象（旧実装は text/search のみで漏れていた）
 * @param {Element} changeBtn
 * @returns {HTMLInputElement | null}
 */
function findRoomCodeInputFallback(changeBtn) {
  const form = changeBtn.closest("form");
  if (form) {
    const inputs = form.querySelectorAll(
      'input[type="text"], input[type="search"], input[type="url"], input:not([type])'
    );
    for (const el of inputs) {
      if (el instanceof HTMLInputElement && isVisible(el)) {
        return el;
      }
    }
    const first = form.querySelector("input");
    if (first instanceof HTMLInputElement) return first;
  }

  let el = changeBtn.previousElementSibling;
  for (let i = 0; i < 8 && el; i++) {
    if (el instanceof HTMLInputElement) return el;
    const inner = el.querySelector?.(
      'input[type="text"], input[type="search"], input[type="url"], input:not([type])'
    );
    if (inner instanceof HTMLInputElement) return inner;
    el = el.previousElementSibling;
  }

  return null;
}

/**
 * @param {Element} changeBtn
 * @returns {HTMLInputElement | null}
 */
function findRoomCodeInput(changeBtn) {
  const primary = findRoomMatchingInputPrimary();
  if (primary) {
    return primary;
  }
  return findRoomCodeInputFallback(changeBtn);
}

/**
 * @param {Element} el
 */
function isVisible(el) {
  const st = window.getComputedStyle(el);
  return st.display !== "none" && st.visibility !== "hidden" && el.offsetParent !== null;
}

/**
 * @param {string} value
 */
function applyToInput(input, value) {
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

/** 入力反映のあと、サイトのハンドラが走ってから押すため 1 ティック遅延。 */
function clickMatchingPostButtonDeferred() {
  window.setTimeout(() => {
    const btn = document.querySelector(MATCHING_POST_BUTTON_SELECTOR);
    if (!(btn instanceof HTMLElement) || !isVisible(btn)) {
      return;
    }
    btn.click();
  }, 0);
}

/**
 * @param {string} roomId
 */
async function applyRoomId(roomId) {
  if (!isRateProfilePath(window.location.pathname)) {
    return;
  }

  const changeBtn = document.querySelector(MATCHING_POST_BUTTON_SELECTOR);
  if (!changeBtn) {
    return;
  }

  const raw = typeof roomId === "string" ? roomId : String(roomId);
  if (raw.length > MAX_ROOM_CODE_LENGTH) {
    console.info(
      "[Smash Arena ID Bridge] 部屋コードが長すぎるためスキップしました（SSE の値をそのまま扱う前提で長さのみ防御）"
    );
    return;
  }

  const trimmed = raw.trim();
  if (!ROOM_ID_RE.test(trimmed)) {
    console.info(
      "[Smash Arena ID Bridge] 部屋コードの形式が不正のためスキップしました（5 文字・I/O/Z 以外）"
    );
    return;
  }

  if (lastAppliedRoomId === trimmed) {
    return;
  }

  const input = findRoomCodeInput(changeBtn);
  if (!input) {
    return;
  }

  applyToInput(input, trimmed);
  lastAppliedRoomId = trimmed;

  try {
    const prev = input.style.outline;
    const dark =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    input.style.outline = dark ? "2px solid #81c784" : "2px solid #2e7d32";
    input.style.outlineOffset = "2px";
    setTimeout(() => {
      input.style.outline = prev;
      input.style.outlineOffset = "";
    }, 450);
  } catch {
    // ignore
  }

  const autoClickMatchingPostBtn = await getAutoClickMatchingPostBtn();
  if (
    autoClickMatchingPostBtn &&
    changeBtn instanceof HTMLElement &&
    isVisible(changeBtn)
  ) {
    clickMatchingPostButtonDeferred();
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "SMASH_ARENA_ROOM_ID") {
    return;
  }
  (async () => {
    try {
      await applyRoomId(msg.roomId);
      sendResponse({ ok: true });
    } catch (e) {
      sendResponse({ ok: false, error: String(e) });
    }
  })();
  return true;
});
