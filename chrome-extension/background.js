/**
 * ローカル SSE (GET http://127.0.0.1:<port>/events) を購読し、
 * smashmate.net の rate ページに開いているタブへ部屋コードを送る。
 * EventSource は SW での互換差を避けるため fetch + ReadableStream でパースする。
 *
 * SSE 接続は「拡張の接続 ON」かつ **pathname が `/rate/<数>/` のタブが 1 つ以上あるときだけ**
 * 張る（トップや別ページだけのときは localhost へ繋がない）。
 */

importScripts("constants.js", "shared-path.js");

const { SSE_PATH, DEFAULT_PORT, MAX_SSE_BUFFER_BYTES } = globalThis.SMASH_ARENA_BRIDGE;
const MAX_BACKOFF_MS = 30000;
const SSE_READ_TIMEOUT_MS = 45000;
const MAX_CONNECTION_DETAIL_CHARS = 180;

let abortController = null;
let activeConnectionPort = null;
/** @type {ReturnType<typeof setTimeout> | null} */
let connectionDebounceTimer = null;
let refreshConnectionSeq = 0;
let connectionState = "idle";
let connectionStateDetail = "";
let lastSseActivityAtMs = 0;
/** @type {Map<number, string>} */
const rateProfileTabCache = new Map();
let rateProfileTabCacheReady = false;
/** @type {Promise<void> | null} */
let rebuildRateProfileTabCachePromise = null;
/** @type {boolean | null} */
let lastToolbarIconConnected = null;

function setConnectionState(state, detail = "") {
  const nextDetail = normalizeConnectionDetail(detail);
  if (connectionState === state && connectionStateDetail === nextDetail) {
    return;
  }
  connectionState = state;
  connectionStateDetail = nextDetail;
  void syncToolbarIcon();
  void syncToolbarTitle();
}

/** ツールバーホバー用（専門用語は極力出さない短い日本語） */
async function syncToolbarTitle() {
  let title = "Arena Scan Bridge — 状態を確認中";
  const d = String(connectionStateDetail || "").trim();
  switch (connectionState) {
    case "disabled":
      title = "Arena Scan Bridge — 連携オフ（アイコンをタップで設定）";
      break;
    case "no_rate_tab":
      title = "Arena Scan Bridge — 対戦ルームのタブを開くとつながります";
      break;
    case "connecting":
      title = "Arena Scan Bridge — つなぎ込み中（PC アプリを確認）";
      break;
    case "retrying":
      title = "Arena Scan Bridge — 再接続を試しています";
      break;
    case "connected":
      title = "Arena Scan Bridge — つながっています";
      break;
    case "error": {
      let hint = "接続に問題があります（番号と監視を確認）";
      if (/timeout/i.test(d)) {
        hint = "応答がありません（PC アプリ側を確認）";
      } else if (/HTTP\s*404|\b404\b/i.test(d)) {
        hint = "Arena Scan に届いていません（番号の見直しを）";
      } else if (d) {
        hint = `接続の問題（${d.slice(0, 100)}${d.length > 100 ? "…" : ""}）`;
      }
      title = `Arena Scan Bridge — ${hint}`;
      break;
    }
    case "idle":
    default:
      title = "Arena Scan Bridge — 待機中（アイコンをタップで設定）";
  }
  try {
    await chrome.action.setTitle({ title });
  } catch {
    // ignore
  }
}

/** 接続状態に応じてツールバーアイコンを緑（動作中）／赤（非動作）へ切り替える。 */
async function syncToolbarIcon() {
  const active = connectionState === "connected";
  if (lastToolbarIconConnected === active) {
    return;
  }
  lastToolbarIconConnected = active;
  const path = active
    ? {
        16: "icons/action-green-16.png",
        32: "icons/action-green-32.png",
        48: "icons/action-green-48.png",
      }
    : {
        16: "icons/action-red-16.png",
        32: "icons/action-red-32.png",
        48: "icons/action-red-48.png",
      };
  try {
    await chrome.action.setIcon({ path });
  } catch {
    // ignore
  }
}

/**
 * @param {unknown} detail
 * @returns {string}
 */
function normalizeConnectionDetail(detail) {
  const text = String(detail || "").replace(/\s+/g, " ").trim();
  if (text.length <= MAX_CONNECTION_DETAIL_CHARS) {
    return text;
  }
  return `${text.slice(0, MAX_CONNECTION_DETAIL_CHARS)}…`;
}

function getBridgeStatusSnapshot() {
  return {
    state: connectionState,
    detail: connectionStateDetail,
    port: activeConnectionPort,
    hasRateTabs: rateProfileTabCache.size > 0,
    rateTabCount: rateProfileTabCache.size,
    lastSseActivityAtMs,
    readTimeoutMs: SSE_READ_TIMEOUT_MS,
    nowMs: Date.now(),
  };
}

chrome.runtime.onInstalled.addListener(() => {
  void rebuildRateProfileTabCache();
  refreshConnection();
});

chrome.runtime.onStartup.addListener(() => {
  void rebuildRateProfileTabCache();
  refreshConnection();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "sync") return;
  if (changes.bridgeEnabled || changes.bridgePort) {
    refreshConnection();
  }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (tab?.id != null && tab.url) {
    updateRateProfileTabCacheEntry(tab.id, tab.url);
  } else if (changeInfo.url != null && tabId != null) {
    removeRateProfileTabCacheEntry(tabId);
  }
  if (changeInfo.url != null || changeInfo.status === "complete") {
    scheduleConnectionRefresh();
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  removeRateProfileTabCacheEntry(tabId);
  scheduleConnectionRefresh();
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "SMASH_ARENA_GET_BRIDGE_STATUS") {
    sendResponse({ ok: true, status: getBridgeStatusSnapshot() });
    return false;
  }
  return false;
});

function scheduleConnectionRefresh() {
  if (connectionDebounceTimer != null) {
    clearTimeout(connectionDebounceTimer);
  }
  connectionDebounceTimer = setTimeout(() => {
    connectionDebounceTimer = null;
    refreshConnection();
  }, 150);
}

/**
 * `/rate/<数>/` 形式の smashmate タブが 1 つでもあれば true（アクティブでなくてよい）。
 * @returns {Promise<boolean>}
 */
async function hasAnyRateProfileTab() {
  if (!rateProfileTabCacheReady) {
    await rebuildRateProfileTabCache();
  }
  return rateProfileTabCache.size > 0;
}

function updateRateProfileTabCacheEntry(tabId, url) {
  let pathname;
  try {
    pathname = new URL(url).pathname;
  } catch {
    rateProfileTabCache.delete(tabId);
    return;
  }
  if (isRateProfilePath(pathname)) {
    rateProfileTabCache.set(tabId, url);
    return;
  }
  rateProfileTabCache.delete(tabId);
}

function removeRateProfileTabCacheEntry(tabId) {
  rateProfileTabCache.delete(tabId);
}

async function rebuildRateProfileTabCache() {
  if (rebuildRateProfileTabCachePromise) {
    return rebuildRateProfileTabCachePromise;
  }
  rebuildRateProfileTabCachePromise = (async () => {
    try {
      const tabs = await chrome.tabs.query({ url: "https://smashmate.net/rate/*" });
      rateProfileTabCache.clear();
      for (const tab of tabs) {
        if (tab.id == null || !tab.url) {
          continue;
        }
        updateRateProfileTabCacheEntry(tab.id, tab.url);
      }
    } catch {
      // クエリ失敗時は空キャッシュでよい（次の onUpdated で復旧）
      rateProfileTabCache.clear();
    } finally {
      rateProfileTabCacheReady = true;
      rebuildRateProfileTabCachePromise = null;
    }
  })();
  return rebuildRateProfileTabCachePromise;
}

refreshConnection();

async function getSettings() {
  const raw = await chrome.storage.sync.get({
    bridgeEnabled: false,
    bridgePort: DEFAULT_PORT,
  });
  let port = Number.parseInt(String(raw.bridgePort), 10);
  if (!Number.isFinite(port) || port < 1 || port > 65535) {
    port = DEFAULT_PORT;
  }
  return { bridgeEnabled: Boolean(raw.bridgeEnabled), bridgePort: port };
}

async function refreshConnection() {
  const currentSeq = ++refreshConnectionSeq;
  const { bridgeEnabled, bridgePort } = await getSettings();
  if (currentSeq !== refreshConnectionSeq) {
    return;
  }

  if (!bridgeEnabled) {
    setConnectionState("disabled");
    stopActiveConnection();
    try {
      await chrome.action.setBadgeText({ text: "" });
    } catch {
      // ignore
    }
    return;
  }

  const wantSse = await hasAnyRateProfileTab();
  if (currentSeq !== refreshConnectionSeq) {
    return;
  }
  if (!wantSse) {
    setConnectionState("no_rate_tab");
    stopActiveConnection();
    try {
      await chrome.action.setBadgeText({ text: "" });
    } catch {
      // ignore
    }
    return;
  }

  // 同一ポートで接続中なら再接続しない（tabs.onUpdated 連打時の接続チラつき抑制）。
  if (abortController && activeConnectionPort === bridgePort) {
    if (connectionState === "idle" || connectionState === "no_rate_tab") {
      setConnectionState("connected");
    }
    return;
  }

  setConnectionState("connecting");
  stopActiveConnection();
  const localAbortController = new AbortController();
  abortController = localAbortController;
  activeConnectionPort = bridgePort;
  lastSseActivityAtMs = 0;
  runSseWithBackoff(bridgePort, localAbortController.signal)
    .catch(() => {})
    .finally(() => {
      if (abortController === localAbortController) {
        abortController = null;
        activeConnectionPort = null;
        if (connectionState !== "disabled" && connectionState !== "no_rate_tab") {
          setConnectionState("idle");
        }
      }
    });
}

function stopActiveConnection() {
  if (abortController) {
    abortController.abort();
    abortController = null;
  }
  activeConnectionPort = null;
  lastSseActivityAtMs = 0;
}

/**
 * @param {number} port
 * @param {AbortSignal} signal
 */
async function runSseWithBackoff(port, signal) {
  let backoffMs = 1000;
  while (!signal.aborted) {
    const cfg = await getSettings();
    if (!cfg.bridgeEnabled || cfg.bridgePort !== port) {
      break;
    }

    try {
      setConnectionState(backoffMs > 1000 ? "retrying" : "connecting");
      await connectSseOnce(port, signal);
      backoffMs = 1000;
    } catch (e) {
      if (signal.aborted || e?.name === "AbortError") {
        break;
      }
      setConnectionState("error", String(e?.message || e || "unknown_error"));
      try {
        await chrome.action.setBadgeBackgroundColor({ color: "#c62828" });
        await chrome.action.setBadgeText({ text: "!" });
      } catch {
        // ignore
      }
    }

    if (signal.aborted) break;

    const next = await getSettings();
    if (!next.bridgeEnabled || next.bridgePort !== port) {
      break;
    }

    const base = Math.min(backoffMs, MAX_BACKOFF_MS);
    const jitter = base * (0.85 + Math.random() * 0.15);
    const wait = Math.max(0, Math.round(jitter));
    try {
      await sleep(wait, signal);
    } catch {
      break;
    }
    backoffMs = Math.min(backoffMs * 2, MAX_BACKOFF_MS);
  }
}

/**
 * @param {number} ms
 * @param {AbortSignal} signal
 */
function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const t = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(t);
      signal.removeEventListener("abort", onAbort);
      reject(new DOMException("Aborted", "AbortError"));
    }
    signal.addEventListener("abort", onAbort);
  });
}

/**
 * @param {number} port
 * @param {AbortSignal} signal
 */
async function connectSseOnce(port, signal) {
  const url = `http://127.0.0.1:${port}${SSE_PATH}`;
  const resp = await fetch(url, {
    signal,
    headers: { Accept: "text/event-stream" },
  });

  if (!resp.ok) {
    throw new Error(`SSE HTTP ${resp.status}`);
  }

  try {
    await chrome.action.setBadgeBackgroundColor({ color: "#2e7d32" });
    await chrome.action.setBadgeText({ text: "OK" });
  } catch {
    // ignore
  }
  setConnectionState("connected");
  lastSseActivityAtMs = Date.now();

  const reader = resp.body?.getReader();
  if (!reader) {
    throw new Error("No response body");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (!signal.aborted) {
    const { done, value } = await readWithTimeout(reader, SSE_READ_TIMEOUT_MS, signal);
    if (done) break;
    lastSseActivityAtMs = Date.now();
    buffer += decoder.decode(value, { stream: true });
    if (buffer.length > MAX_SSE_BUFFER_BYTES) {
      // 区切りなしの巨大ストリーム等: 末尾のみ保持しイベント境界の復旧を試みる
      buffer = buffer.slice(-Math.min(8192, MAX_SSE_BUFFER_BYTES));
    }

    let consumed;
    while ((consumed = consumeNextSseEvent(buffer)) !== null) {
      buffer = consumed.rest;
      const payload = parseSseDataBlock(consumed.eventText);
      if (payload !== null && payload !== "") {
        lastSseActivityAtMs = Date.now();
        await broadcastRoomId(payload);
      }
    }
  }
}

/**
 * @template T
 * @param {{ read: () => Promise<T>, cancel?: () => Promise<void> }} reader
 * @param {number} timeoutMs
 * @param {AbortSignal} signal
 * @returns {Promise<T>}
 */
function readWithTimeout(reader, timeoutMs, signal) {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    let settled = false;
    const cancelReader = () => {
      try {
        const p = reader.cancel?.();
        if (p && typeof p.then === "function") {
          void p.catch(() => {});
        }
      } catch {
        // ignore
      }
    };
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      signal.removeEventListener("abort", onAbort);
      cancelReader();
      reject(new Error(`SSE read timeout (${timeoutMs}ms)`));
    }, timeoutMs);

    function onAbort() {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal.removeEventListener("abort", onAbort);
      cancelReader();
      reject(new DOMException("Aborted", "AbortError"));
    }
    signal.addEventListener("abort", onAbort);

    reader
      .read()
      .then((value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        signal.removeEventListener("abort", onAbort);
        resolve(value);
      })
      .catch((err) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        signal.removeEventListener("abort", onAbort);
        reject(err);
      });
  });
}

/**
 * @param {string} buffer
 * @returns {{ eventText: string, rest: string } | null}
 */
function consumeNextSseEvent(buffer) {
  let idx = buffer.indexOf("\r\n\r\n");
  let sepLen = 4;
  if (idx === -1) {
    idx = buffer.indexOf("\n\n");
    sepLen = 2;
  }
  if (idx === -1) {
    return null;
  }
  const eventText = buffer.slice(0, idx);
  const rest = buffer.slice(idx + sepLen);
  return { eventText, rest };
}

/**
 * SSE イベントブロックから data: 行を集約（複数行 data は改行で結合）
 * @param {string} block
 * @returns {string | null}
 */
function parseSseDataBlock(block) {
  const lines = block.split(/\r?\n/);
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) return null;
  return dataLines.join("\n");
}

/**
 * コンテンツ未注入など一時的な失敗ではタブをキャッシュから外さない。
 * Promise 拒否時は `chrome.runtime.lastError` が使えないことがあるため message を優先。
 * @param {unknown} err
 */
function isTransientSendMessageFailure(err) {
  const fromErr =
    err && typeof err === "object" && "message" in err && err.message != null
      ? String(err.message)
      : String(err || "");
  const fromLast =
    typeof chrome !== "undefined" && chrome.runtime?.lastError?.message
      ? String(chrome.runtime.lastError.message)
      : "";
  const msg = `${fromErr} ${fromLast}`.trim();
  return /Receiving end does not exist|Could not establish connection/i.test(msg);
}

/**
 * @param {string} roomId
 */
async function broadcastRoomId(roomId) {
  if (!rateProfileTabCacheReady) {
    await rebuildRateProfileTabCache();
  }
  if (rateProfileTabCache.size === 0) {
    return;
  }
  const tasks = [];
  for (const [tabId] of rateProfileTabCache) {
    tasks.push(
      chrome.tabs
        .sendMessage(tabId, {
          type: "SMASH_ARENA_ROOM_ID",
          roomId,
        })
        .catch((err) => {
          if (isTransientSendMessageFailure(err)) {
            return;
          }
          removeRateProfileTabCacheEntry(tabId);
        })
    );
  }
  await Promise.all(tasks);
}

void syncToolbarIcon();
void syncToolbarTitle();
