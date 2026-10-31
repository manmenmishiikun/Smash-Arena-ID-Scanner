/**
 * smatch-jp.com のレーティング対戦ルーム（`/rate/<数>/`）向け・第1段。
 * SSE で受け取った部屋 ID を `form#arenaForm input[name="arena_id"]` へ書くだけ。
 * submit「設定」の自動クリック、キーボード補助はしない（スマメイト用 content.js と分離）。
 *
 * ホスト画面の目印: `b.host-mark`（「部屋を立てる人」）。ゲスト画面の DOM は未確定のため、
 * `#arenaForm` が無い／入力が無効なときは何もしない。
 */

/** @type {string | null} */
let lastAppliedRoomId = null;

/** 部屋ID欄が空のとき、次に届く SSE を 1 回だけスキップする */
let _sseSkipOneWhileEmpty = false;

/** @type {string} */
let _watchedPathname =
  typeof window !== "undefined" ? window.location.pathname : "";

/** @type {ReturnType<typeof setTimeout> | null} */
let _pathnamePollTimer = null;

const PATHNAME_POLL_MS_ON_PROFILE = 700;
const PATHNAME_POLL_MS_OFF_PROFILE = 2500;

const ARENA_FORM_SELECTOR = "form#arenaForm";
const ARENA_INPUT_SELECTOR = 'form#arenaForm input[name="arena_id"]';
/** ホスト側の目印（ゲスト DOM 取得後にゲートを厳しくしてもよい） */
const HOST_MARK_SELECTOR = "b.host-mark";

const MAX_ROOM_CODE_LENGTH = 64;
/** Python `image_processor.ROOM_ID_PATTERN` と同じ（I / O / Z 除外の 5 文字） */
const ROOM_ID_RE = /^[A-HJ-NP-Y0-9]{5}$/;

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
 * @param {{ requireEnabled?: boolean }} [opts]
 * @returns {HTMLInputElement | null}
 */
function findArenaIdInput(opts = {}) {
  const requireEnabled = Boolean(opts.requireEnabled);
  const form = document.querySelector(ARENA_FORM_SELECTOR);
  if (!(form instanceof HTMLFormElement) || !isVisible(form)) {
    return null;
  }
  const el = document.querySelector(ARENA_INPUT_SELECTOR);
  if (!(el instanceof HTMLInputElement) || !isVisible(el)) {
    return null;
  }
  if (requireEnabled && (el.disabled || el.readOnly)) {
    return null;
  }
  return el;
}

/**
 * ホスト目印があるか。ゲスト DOM 未確定のあいだの補助ゲート。
 * フォーム自体がホスト専用なら将来はフォーム有無だけで足りる。
 * @returns {boolean}
 */
function looksLikeHostArenaUi() {
  const mark = document.querySelector(HOST_MARK_SELECTOR);
  if (mark instanceof HTMLElement && isVisible(mark)) {
    return true;
  }
  // host-mark が一時的に無い遷移でも、募集中フォームがあれば書く（ゲスト確定後に見直し）
  return findArenaIdInput({ requireEnabled: true }) != null;
}

/**
 * @param {HTMLInputElement} input
 * @param {string} value
 */
function applyToInput(input, value) {
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function armEmptyInputSseGateIfNeeded() {
  if (!isRateProfilePath(window.location.pathname)) {
    return;
  }
  const inp = findArenaIdInput({ requireEnabled: true });
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
function onArenaInputForEmptyGate(ev) {
  if (!isRateProfilePath(window.location.pathname)) {
    return;
  }
  if (!(ev.target instanceof HTMLInputElement)) {
    return;
  }
  if (!ev.target.matches(ARENA_INPUT_SELECTOR)) {
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
 * @param {string} roomId
 */
function applyRoomId(roomId) {
  if (!isRateProfilePath(window.location.pathname)) {
    return;
  }
  if (!looksLikeHostArenaUi()) {
    return;
  }

  const raw = typeof roomId === "string" ? roomId : String(roomId);
  if (raw.length > MAX_ROOM_CODE_LENGTH) {
    console.info(
      "[Scanmate Pal / Smatch] 部屋コードが長すぎるためスキップしました"
    );
    return;
  }

  const trimmed = raw.trim();
  if (!ROOM_ID_RE.test(trimmed)) {
    console.info(
      "[Scanmate Pal / Smatch] 部屋コードの形式が不正のためスキップしました（5 文字・I/O/Z 除外）"
    );
    return;
  }

  const input = findArenaIdInput({ requireEnabled: true });
  if (!input) {
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
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "SMASH_ARENA_ROOM_ID") {
    return;
  }
  try {
    applyRoomId(msg.roomId);
    sendResponse({ ok: true });
  } catch (e) {
    sendResponse({ ok: false, error: String(e) });
  }
  return true;
});

document.addEventListener("input", onArenaInputForEmptyGate, true);
document.addEventListener("change", onArenaInputForEmptyGate, true);
document.addEventListener("visibilitychange", onDocumentVisibilityForPathnamePoll);
window.addEventListener("popstate", pollPathnameForSpa);
schedulePathnamePoll();

if (isRateProfilePath(window.location.pathname)) {
  armEmptyInputSseGateIfNeeded();
}
