/**
 * smashmate.net 上で pathname が rate プロフィール形式のときのみ動作。
 * URL パス中の数値はユーザー識別子であり、SSE の部屋コードではない。
 *
 * 送信系ボタン（クラス `matching_post_btn`）が DOM にある場合のみ入力反映。表示文言は「設定」
 * （初回）／「変更」（2回目以降）など可変のため、**ラベル文字列には依存しない**（サイト改修で要メンテ）。
 * 部屋ID入力は実ページの `input.room_matching_id`（`type="url"`）を優先。
 * オプション ON のとき、入力後に同ボタンを `click()`（サイト側の確認ダイアログはユーザー操作前提）。
 * 手入力時も、部屋ID欄で Enter または Space を押したら同ボタンを `click()` 扱いにする（拡張オプションで各キー ON/OFF）。
 * 確認ダイアログ表示中は Enter または Space=OK / Escape または Backspace=キャンセルで操作できるようにする（同上）。
 * 部屋ID欄が空のときは、再接続直後などに届く可能性のある **1 回目の SSE 反映だけ**スキップし、
 * **2 回目以降**の SSE から貼り付ける（空欄に戻したら再び同様）。
 * 空欄かつ「前回の部屋IDを呼び出す」UIがあるときは Enter または Space でそちらを優先クリック。
 */

/** @type {string | null} */
let lastAppliedRoomId = null;

/** 部屋ID欄が空のとき、次に届く SSE を 1 回だけスキップする（古い値の即時反映を抑止） */
let _sseSkipOneWhileEmpty = false;

/** SPA 相当の遷移検知用（`pushState` は `popstate` が飛ばないためポーリング併用） */
let _watchedPathname =
  typeof window !== "undefined" ? window.location.pathname : "";

/** 対戦ルームプロフィール URL 上では短め、それ以外の rate 配下では間隔を広げて負荷を抑える */
const PATHNAME_POLL_MS_ON_PROFILE = 700;
const PATHNAME_POLL_MS_OFF_PROFILE = 2500;
/** @type {ReturnType<typeof setTimeout> | null} */
let _pathnamePollTimer = null;

/** サイト改修で要メンテ。文言ではなく `matching_post_btn` のみで判定する */
const MATCHING_POST_BUTTON_SELECTOR = "button.matching_post_btn";

/**
 * 部屋ID入力（実サイトでは type="url"）
 * 例: <input class="width100 form-control room_matching_id" name="room_matching_id" type="url" ...>
 */
const ROOM_MATCHING_INPUT_SELECTOR =
  'input.room_matching_id[name="room_matching_id"]';
/** 新規対戦ルーム時などに表示される「前回の部屋IDを呼び出す」系（要メンテ） */
const PREV_ROOM_RECALL_SPAN_SELECTOR = "span.cursor";
const SWAL_CANCEL_BUTTON_SELECTOR = "button.swal-button.swal-button--cancel";
const SWAL_OK_BUTTON_SELECTOR = "button.swal-button.swal-button--ok";
const KEYBOARD_SHORTCUTS_INSTALLED_FLAG = "__smashArenaKeyboardShortcutsInstalled";
const NON_TEXT_INPUT_TYPES = new Set([
  "button",
  "checkbox",
  "color",
  "file",
  "hidden",
  "image",
  "radio",
  "range",
  "reset",
  "submit",
]);

/** 防御: デスクトップの抽出に委ね、長さのみ制限 */
const MAX_ROOM_CODE_LENGTH = 64;

/** Python `image_processor.ROOM_ID_PATTERN` と同じ（I / O / Z 除外の 5 文字） */
const ROOM_ID_RE = /^[A-HJ-NP-Y0-9]{5}$/;

/** `autoClickMatchingPostBtn` を毎回 storage 読みしない（onChanged で同期） */
let _autoClickCache = false;
let _autoClickLoaded = false;

/** キーボードショートカット（拡張オプション。既定はすべて ON） */
let _keyboardShortcutsLoaded = false;
/** @type {{ enter: boolean, space: boolean, escape: boolean, backspace: boolean }} */
let _keyboardShortcutsCache = {
  enter: true,
  space: true,
  escape: true,
  backspace: true,
};
let _lastAutoClickAtMs = 0;
/** @type {Map<string, number>} */
const _autoClickedRoomIdAtMs = new Map();
/** @type {ReturnType<typeof setTimeout> | null} */
let _focusRestoreTimer = null;

/** 短時間の連打を防ぐための最短間隔（ms） */
const AUTO_CLICK_COOLDOWN_MS = 15000;
/** 同一IDを再クリック可能にするまでの保持時間（ms） */
const AUTO_CLICK_ROOM_ID_TTL_MS = 120000;

async function getAutoClickMatchingPostBtn() {
  if (_autoClickLoaded) return _autoClickCache;
  try {
    const r = await chrome.storage.sync.get({ autoClickMatchingPostBtn: false });
    _autoClickCache = Boolean(r.autoClickMatchingPostBtn);
  } catch {
    _autoClickCache = false;
  }
  _autoClickLoaded = true;
  return _autoClickCache;
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "sync") {
    return;
  }
  if (changes.autoClickMatchingPostBtn) {
    _autoClickCache = Boolean(changes.autoClickMatchingPostBtn.newValue);
    _autoClickLoaded = true;
  }
  if (changes.keyboardShortcutEnter) {
    _keyboardShortcutsCache.enter = Boolean(changes.keyboardShortcutEnter.newValue);
    _keyboardShortcutsLoaded = true;
  }
  if (changes.keyboardShortcutSpace) {
    _keyboardShortcutsCache.space = Boolean(changes.keyboardShortcutSpace.newValue);
    _keyboardShortcutsLoaded = true;
  }
  if (changes.keyboardShortcutEscape) {
    _keyboardShortcutsCache.escape = Boolean(changes.keyboardShortcutEscape.newValue);
    _keyboardShortcutsLoaded = true;
  }
  if (changes.keyboardShortcutBackspace) {
    _keyboardShortcutsCache.backspace = Boolean(changes.keyboardShortcutBackspace.newValue);
    _keyboardShortcutsLoaded = true;
  }
});

async function getKeyboardShortcuts() {
  if (_keyboardShortcutsLoaded) {
    return _keyboardShortcutsCache;
  }
  try {
    const r = await chrome.storage.sync.get({
      keyboardShortcutEnter: true,
      keyboardShortcutSpace: true,
      keyboardShortcutEscape: true,
      keyboardShortcutBackspace: true,
    });
    _keyboardShortcutsCache = {
      enter: Boolean(r.keyboardShortcutEnter),
      space: Boolean(r.keyboardShortcutSpace),
      escape: Boolean(r.keyboardShortcutEscape),
      backspace: Boolean(r.keyboardShortcutBackspace),
    };
  } catch {
    // 既定のまま
  }
  _keyboardShortcutsLoaded = true;
  return _keyboardShortcutsCache;
}

/**
 * 明示セレクタで取得。見つからない／非表示のときは null。
 * @param {{ requireEnabled?: boolean }} [opts]
 * @returns {HTMLInputElement | null}
 */
function findRoomMatchingInputPrimary(opts = {}) {
  const requireEnabled = Boolean(opts.requireEnabled);
  const el = document.querySelector(ROOM_MATCHING_INPUT_SELECTOR);
  if (el instanceof HTMLInputElement && isVisible(el)) {
    if (requireEnabled && (el.disabled || el.readOnly)) {
      return null;
    }
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
  if (st.display === "none" || st.visibility === "hidden") {
    return false;
  }
  return el.getClientRects().length > 0;
}

/**
 * @param {Element | null} el
 * @returns {el is HTMLElement}
 */
function isClickableMatchingPostButton(el) {
  if (!(el instanceof HTMLElement) || !isVisible(el)) {
    return false;
  }
  if ("disabled" in el && el.disabled === true) {
    return false;
  }
  return true;
}

/**
 * @param {Element | null} el
 * @returns {el is HTMLButtonElement}
 */
function isClickableSwalButton(el) {
  return el instanceof HTMLButtonElement && isVisible(el) && !el.disabled;
}

/**
 * 「⇒前回の部屋IDを呼び出す」等。文言全文ではなく短い部分一致で拾う。
 * @returns {HTMLElement | null}
 */
function findPrevRoomRecallControl() {
  const nodes = document.querySelectorAll(PREV_ROOM_RECALL_SPAN_SELECTOR);
  for (const el of nodes) {
    if (!(el instanceof HTMLElement) || !isVisible(el)) {
      continue;
    }
    const t = (el.textContent || "").replace(/\s+/g, " ").trim();
    if (t.includes("前回") && /呼び出/.test(t)) {
      return el;
    }
  }
  return null;
}

/**
 * @param {Element | null} el
 * @returns {el is HTMLElement}
 */
function isClickableRecallControl(el) {
  if (!(el instanceof HTMLElement) || !isVisible(el)) {
    return false;
  }
  if (window.getComputedStyle(el).pointerEvents === "none") {
    return false;
  }
  return true;
}

/**
 * 部屋ID欄が空のときだけ、次の SSE 1 件をスキップ対象にする。
 */
function armEmptyInputSseGateIfNeeded() {
  if (!isRateProfilePath(window.location.pathname)) {
    return;
  }
  const inp = findRoomMatchingInputPrimary({ requireEnabled: true });
  if (!inp) {
    return;
  }
  if (String(inp.value || "").trim() === "") {
    _sseSkipOneWhileEmpty = true;
  }
}

/**
 * @param {Event} ev
 */
function onRoomMatchingInputForEmptyGate(ev) {
  if (!isRateProfilePath(window.location.pathname)) {
    return;
  }
  if (!isRoomMatchingInputTarget(ev.target)) {
    return;
  }
  if (String(ev.target.value || "").trim() === "") {
    _sseSkipOneWhileEmpty = true;
  } else {
    _sseSkipOneWhileEmpty = false;
  }
}

function pollPathnameForSpa() {
  const p = window.location.pathname;
  if (p === _watchedPathname) {
    return;
  }
  _watchedPathname = p;
  if (isRateProfilePath(p)) {
    lastAppliedRoomId = null;
    armEmptyInputSseGateIfNeeded();
  }
}

function clearPathnamePollTimer() {
  if (_pathnamePollTimer != null) {
    clearTimeout(_pathnamePollTimer);
    _pathnamePollTimer = null;
  }
}

/**
 * タブが非表示のときはタイマーを止め、表示に戻ったときだけ再開する。
 */
function schedulePathnamePoll() {
  clearPathnamePollTimer();
  if (document.hidden) {
    return;
  }
  const ms = isRateProfilePath(window.location.pathname)
    ? PATHNAME_POLL_MS_ON_PROFILE
    : PATHNAME_POLL_MS_OFF_PROFILE;
  _pathnamePollTimer = window.setTimeout(() => {
    _pathnamePollTimer = null;
    pollPathnameForSpa();
    schedulePathnamePoll();
  }, ms);
}

function onDocumentVisibilityForPathnamePoll() {
  if (document.hidden) {
    clearPathnamePollTimer();
    return;
  }
  pollPathnameForSpa();
  schedulePathnamePoll();
}

/**
 * @param {string} value
 */
function applyToInput(input, value) {
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function pruneAutoClickedRoomIds(now) {
  for (const [id, atMs] of _autoClickedRoomIdAtMs) {
    if (now - atMs >= AUTO_CLICK_ROOM_ID_TTL_MS) {
      _autoClickedRoomIdAtMs.delete(id);
    }
  }
}

/**
 * @param {string} roomId
 * @param {number} now
 * @returns {boolean}
 */
function canAutoClickForRoomId(roomId, now) {
  pruneAutoClickedRoomIds(now);

  if (now - _lastAutoClickAtMs < AUTO_CLICK_COOLDOWN_MS) {
    return false;
  }

  const lastClickedForId = _autoClickedRoomIdAtMs.get(roomId);
  if (typeof lastClickedForId === "number" && now - lastClickedForId < AUTO_CLICK_ROOM_ID_TTL_MS) {
    return false;
  }

  return true;
}

/**
 * @param {string} roomId
 * @param {number} now
 */
function markAutoClickedRoomId(roomId, now) {
  _lastAutoClickAtMs = now;
  _autoClickedRoomIdAtMs.set(roomId, now);
}

/** 入力反映のあと、サイトのハンドラが走ってから押すため 1 ティック遅延。 */
function clickMatchingPostButtonDeferred(roomId) {
  window.setTimeout(() => {
    const btn = document.querySelector(MATCHING_POST_BUTTON_SELECTOR);
    if (!isClickableMatchingPostButton(btn)) {
      return;
    }
    const now = Date.now();
    if (!canAutoClickForRoomId(roomId, now)) {
      return;
    }
    markAutoClickedRoomId(roomId, now);
    btn.click();
  }, 0);
}

/**
 * @param {KeyboardEvent} ev
 * @returns {boolean}
 */
function baseModifiersOk(ev) {
  return (
    !ev.repeat &&
    !ev.isComposing &&
    ev.keyCode !== 229 &&
    !ev.altKey &&
    !ev.ctrlKey &&
    !ev.metaKey &&
    !ev.shiftKey
  );
}

/**
 * 部屋ID欄の送信・SweetAlert の OK など、**確定**に使うキー（Enter / Space）。オプションで個別に無効化可。
 * @param {KeyboardEvent} ev
 * @returns {boolean}
 */
function matchesConfiguredPrimaryKey(ev) {
  if (!baseModifiersOk(ev)) {
    return false;
  }
  const cfg = _keyboardShortcutsCache;
  if (ev.key === "Enter" && cfg.enter) {
    return true;
  }
  if ((ev.key === " " || ev.code === "Space") && cfg.space) {
    return true;
  }
  return false;
}

/**
 * SweetAlert のキャンセル相当（Escape または Backspace）。オプションで個別に無効化可。
 * @param {KeyboardEvent} ev
 * @returns {boolean}
 */
function matchesConfiguredCancelKey(ev) {
  if (!baseModifiersOk(ev)) {
    return false;
  }
  const cfg = _keyboardShortcutsCache;
  if ((ev.key === "Escape" || ev.key === "Esc") && cfg.escape) {
    return true;
  }
  if (ev.key === "Backspace" && cfg.backspace) {
    return true;
  }
  return false;
}

/**
 * @param {KeyboardEvent} ev
 * @returns {boolean}
 */
function isSwalShortcutKey(ev) {
  return matchesConfiguredPrimaryKey(ev) || matchesConfiguredCancelKey(ev);
}

/**
 * @param {Element | null} el
 * @returns {boolean}
 */
function isEditableElement(el) {
  if (!(el instanceof Element)) {
    return false;
  }
  if (el instanceof HTMLTextAreaElement) {
    return true;
  }
  if (el instanceof HTMLInputElement) {
    const t = (el.type || "text").toLowerCase();
    return !NON_TEXT_INPUT_TYPES.has(t);
  }
  if (el instanceof HTMLSelectElement) {
    return true;
  }
  return el.isContentEditable;
}

/**
 * @param {EventTarget | null} target
 * @returns {boolean}
 */
function isFromNonRoomEditableTarget(target) {
  if (!(target instanceof Element)) {
    return false;
  }
  const editableRoot = target.closest("input, textarea, select, [contenteditable]");
  if (!editableRoot) {
    return false;
  }
  if (
    editableRoot instanceof HTMLInputElement &&
    editableRoot.matches(ROOM_MATCHING_INPUT_SELECTOR)
  ) {
    return false;
  }
  return isEditableElement(editableRoot);
}

/**
 * @param {EventTarget | null} target
 * @returns {target is HTMLInputElement}
 */
function isRoomMatchingInputTarget(target) {
  return (
    target instanceof HTMLInputElement && target.matches(ROOM_MATCHING_INPUT_SELECTOR)
  );
}

/**
 * @returns {boolean}
 */
function isRoomMatchingInputFocused() {
  return isRoomMatchingInputTarget(document.activeElement);
}

/**
 * @returns {HTMLInputElement | null}
 */
function findVisibleRoomMatchingInput() {
  return findRoomMatchingInputPrimary({ requireEnabled: true });
}

function focusRoomMatchingInputSoon() {
  if (_focusRestoreTimer != null) {
    clearTimeout(_focusRestoreTimer);
    _focusRestoreTimer = null;
  }
  _focusRestoreTimer = window.setTimeout(() => {
    const input = findVisibleRoomMatchingInput();
    _focusRestoreTimer = null;
    if (!input) {
      return;
    }
    input.focus();
    if (typeof input.select === "function") {
      input.select();
    }
  }, 0);
}

/**
 * 手入力の Enter / Space でも「設定/変更」ボタン押下と同じ扱いにする。
 * @param {KeyboardEvent} ev
 */
function onRoomMatchingInputEnter(ev) {
  if (!isRateProfilePath(window.location.pathname)) {
    return;
  }
  if (!matchesConfiguredPrimaryKey(ev) || ev.defaultPrevented) {
    return;
  }
  if (!isRoomMatchingInputTarget(ev.target)) {
    return;
  }
  const roomInput = ev.target;
  if (roomInput.disabled || roomInput.readOnly) {
    return;
  }

  const trimmed = String(roomInput.value || "").trim();
  if (trimmed === "") {
    const recall = findPrevRoomRecallControl();
    if (recall && isClickableRecallControl(recall)) {
      ev.preventDefault();
      recall.click();
      return;
    }
  }

  const changeBtn = document.querySelector(MATCHING_POST_BUTTON_SELECTOR);
  if (!isClickableMatchingPostButton(changeBtn)) {
    return;
  }

  ev.preventDefault();
  changeBtn.click();
}

/**
 * SweetAlert の確認ダイアログ表示中のみキーボードで押せるようにする。
 * Enter または Space: OK / Escape または Backspace: キャンセル
 * @param {KeyboardEvent} ev
 */
function onSwalDialogKeyboardShortcut(ev) {
  if (!isRateProfilePath(window.location.pathname) || ev.defaultPrevented) {
    return;
  }
  if (!isSwalShortcutKey(ev)) {
    return;
  }
  // 部屋ID欄での Enter / Space は常に「設定/変更」押下へ流し、SWAL 側で奪わない。
  if (isRoomMatchingInputTarget(ev.target) || isRoomMatchingInputFocused()) {
    return;
  }
  if (isFromNonRoomEditableTarget(ev.target)) {
    return;
  }

  const okBtn = document.querySelector(SWAL_OK_BUTTON_SELECTOR);
  const cancelBtn = document.querySelector(SWAL_CANCEL_BUTTON_SELECTOR);
  const hasOk = isClickableSwalButton(okBtn);
  const hasCancel = isClickableSwalButton(cancelBtn);
  if (!hasOk && !hasCancel) {
    return;
  }

  if (matchesConfiguredPrimaryKey(ev) && hasOk) {
    ev.preventDefault();
    okBtn.click();
    return;
  }

  if (matchesConfiguredCancelKey(ev) && hasCancel) {
    ev.preventDefault();
    cancelBtn.click();
    // キャンセル後に Enter / Space だけで再送しやすいよう、入力欄へフォーカスを戻す。
    focusRoomMatchingInputSoon();
  }
}

/**
 * SweetAlert の「キャンセル」ボタンクリックでも入力欄にフォーカスを戻す。
 * @param {MouseEvent} ev
 */
function onSwalCancelButtonClick(ev) {
  if (!isRateProfilePath(window.location.pathname)) {
    return;
  }
  if (!(ev.target instanceof Element)) {
    return;
  }
  const cancelBtn = ev.target.closest(SWAL_CANCEL_BUTTON_SELECTOR);
  if (!isClickableSwalButton(cancelBtn)) {
    return;
  }
  focusRoomMatchingInputSoon();
}

function installKeyboardShortcutsOnce() {
  if (window[KEYBOARD_SHORTCUTS_INSTALLED_FLAG]) {
    return;
  }
  window[KEYBOARD_SHORTCUTS_INSTALLED_FLAG] = true;
  document.addEventListener("keydown", onRoomMatchingInputEnter);
  document.addEventListener("keydown", onSwalDialogKeyboardShortcut, true);
  document.addEventListener("click", onSwalCancelButtonClick, true);
  document.addEventListener("input", onRoomMatchingInputForEmptyGate, true);
  window.addEventListener("pageshow", () => {
    if (isRateProfilePath(window.location.pathname)) {
      armEmptyInputSseGateIfNeeded();
    }
    pollPathnameForSpa();
    if (!document.hidden) {
      schedulePathnamePoll();
    }
  });
  window.addEventListener("popstate", () => {
    pollPathnameForSpa();
    schedulePathnamePoll();
  });
  document.addEventListener("visibilitychange", onDocumentVisibilityForPathnamePoll);
  onDocumentVisibilityForPathnamePoll();
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

  const input = findRoomCodeInput(changeBtn);
  if (!input) {
    return;
  }
  if (input.disabled || input.readOnly) {
    return;
  }

  if (_sseSkipOneWhileEmpty) {
    if (String(input.value || "").trim() === "") {
      _sseSkipOneWhileEmpty = false;
      return;
    }
    _sseSkipOneWhileEmpty = false;
  }

  if (lastAppliedRoomId === trimmed && String(input.value || "").trim() === trimmed) {
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
    isClickableMatchingPostButton(changeBtn)
  ) {
    clickMatchingPostButtonDeferred(trimmed);
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

installKeyboardShortcutsOnce();
void getKeyboardShortcuts();
if (isRateProfilePath(window.location.pathname)) {
  armEmptyInputSseGateIfNeeded();
}
