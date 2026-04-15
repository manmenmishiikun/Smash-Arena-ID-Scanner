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

let abortController = null;
/** @type {ReturnType<typeof setTimeout> | null} */
let connectionDebounceTimer = null;

chrome.runtime.onInstalled.addListener(() => {
  refreshConnection();
});

chrome.runtime.onStartup.addListener(() => {
  refreshConnection();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "sync") return;
  if (changes.bridgeEnabled || changes.bridgePort) {
    refreshConnection();
  }
});

chrome.tabs.onUpdated.addListener((_tabId, changeInfo, _tab) => {
  if (changeInfo.url != null || changeInfo.status === "complete") {
    scheduleConnectionRefresh();
  }
});

chrome.tabs.onRemoved.addListener(() => {
  scheduleConnectionRefresh();
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
  const tabs = await chrome.tabs.query({ url: "https://smashmate.net/rate/*" });
  for (const tab of tabs) {
    if (!tab.url) continue;
    let pathname;
    try {
      pathname = new URL(tab.url).pathname;
    } catch {
      continue;
    }
    if (isRateProfilePath(pathname)) {
      return true;
    }
  }
  return false;
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
  if (abortController) {
    abortController.abort();
    abortController = null;
  }

  const { bridgeEnabled, bridgePort } = await getSettings();

  if (!bridgeEnabled) {
    await chrome.action.setBadgeText({ text: "" });
    return;
  }

  const wantSse = await hasAnyRateProfileTab();
  if (!wantSse) {
    await chrome.action.setBadgeText({ text: "" });
    return;
  }

  abortController = new AbortController();
  const signal = abortController.signal;

  runSseWithBackoff(bridgePort, signal).catch(() => {});
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
      await connectSseOnce(port, signal);
      backoffMs = 1000;
    } catch (e) {
      if (signal.aborted || e?.name === "AbortError") {
        break;
      }
      await chrome.action.setBadgeBackgroundColor({ color: "#c62828" });
      await chrome.action.setBadgeText({ text: "!" });
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

  await chrome.action.setBadgeBackgroundColor({ color: "#2e7d32" });
  await chrome.action.setBadgeText({ text: "OK" });

  const reader = resp.body?.getReader();
  if (!reader) {
    throw new Error("No response body");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) break;
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
        await broadcastRoomId(payload);
      }
    }
  }
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
 * @param {string} roomId
 */
async function broadcastRoomId(roomId) {
  const tabs = await chrome.tabs.query({ url: "https://smashmate.net/rate/*" });
  const tasks = [];
  for (const tab of tabs) {
    if (tab.id == null || !tab.url) continue;
    let pathname;
    try {
      pathname = new URL(tab.url).pathname;
    } catch {
      continue;
    }
    if (!isRateProfilePath(pathname)) continue;
    tasks.push(
      chrome.tabs
        .sendMessage(tab.id, {
          type: "SMASH_ARENA_ROOM_ID",
          roomId,
        })
        .catch(() => {})
    );
  }
  await Promise.all(tasks);
}
