const BR = globalThis.SMASH_ARENA_BRIDGE || { DEFAULT_PORT: 2206, SSE_PATH: "/events" };
const BRIDGE_STATUS_POLL_MS = 4000;
const STALE_ACTIVITY_WARN_MS = 60000;
const PORT_DEBOUNCE_MS = 300;

let statusTimer = null;
/** @type {ReturnType<typeof setInterval> | null} */
let bridgeStatePollTimer = null;
/** @type {Promise<void> | null} */
let bridgeStateRefreshPromise = null;
/** @type {ReturnType<typeof setTimeout> | null} */
let portDebounceTimer = null;

function clampPort(n) {
  const x = Number.parseInt(String(n), 10);
  if (!Number.isFinite(x)) return BR.DEFAULT_PORT;
  return Math.max(1, Math.min(65535, x));
}

/**
 * ポップアップ上の連携・自動クリック・キーボード設定をまとめて読む（要素欠落時は null）。
 * @returns {{
 *   bridgeEnabled: boolean,
 *   autoClickMatchingPostBtn: boolean,
 *   keyboardShortcutEnter: boolean,
 *   keyboardShortcutSpace: boolean,
 *   keyboardShortcutEscape: boolean,
 *   keyboardShortcutBackspace: boolean
 * } | null}
 */
function readExtensionFormState() {
  const bridgeEnabledEl = document.getElementById("bridgeEnabled");
  const autoClickEl = document.getElementById("autoClickMatchingPostBtn");
  const kEnter = document.getElementById("keyboardShortcutEnter");
  const kSpace = document.getElementById("keyboardShortcutSpace");
  const kEsc = document.getElementById("keyboardShortcutEscape");
  const kBs = document.getElementById("keyboardShortcutBackspace");
  if (!(bridgeEnabledEl instanceof HTMLInputElement) || !(autoClickEl instanceof HTMLInputElement)) {
    return null;
  }
  return {
    bridgeEnabled: bridgeEnabledEl.checked,
    autoClickMatchingPostBtn: autoClickEl.checked,
    keyboardShortcutEnter: kEnter instanceof HTMLInputElement ? kEnter.checked : true,
    keyboardShortcutSpace: kSpace instanceof HTMLInputElement ? kSpace.checked : true,
    keyboardShortcutEscape: kEsc instanceof HTMLInputElement ? kEsc.checked : true,
    keyboardShortcutBackspace: kBs instanceof HTMLInputElement ? kBs.checked : true,
  };
}

function parsePortInput(raw) {
  const txt = String(raw ?? "").trim();
  if (txt === "") {
    return { ok: false, reason: "ポート番号を入力してください。" };
  }
  if (!/^\d+$/.test(txt)) {
    return { ok: false, reason: "ポート番号は半角数字で入力してください。" };
  }
  const x = Number.parseInt(txt, 10);
  if (!Number.isFinite(x) || x < 1 || x > 65535) {
    return { ok: false, reason: "ポート番号は 1〜65535 の範囲で入力してください。" };
  }
  return { ok: true, value: x };
}

function setStatus(message, kind = "info", autoClearMs = 0) {
  const status = document.getElementById("status");
  if (!status) {
    return;
  }
  status.textContent = message || "";
  status.classList.remove("is-success", "is-error", "is-warning");
  if (kind === "success") status.classList.add("is-success");
  if (kind === "error") status.classList.add("is-error");
  if (kind === "warning") status.classList.add("is-warning");

  if (statusTimer != null) {
    clearTimeout(statusTimer);
    statusTimer = null;
  }
  if (autoClearMs > 0) {
    statusTimer = setTimeout(() => {
      status.textContent = "";
      status.classList.remove("is-success", "is-error", "is-warning");
      statusTimer = null;
    }, autoClearMs);
  }
}

function setPortError(message) {
  const el = document.getElementById("bridgePortError");
  if (!el) {
    return;
  }
  el.textContent = String(message || "");
}

function applyConnectionStateStyle(style) {
  const el = document.getElementById("connectionState");
  if (!el) {
    return;
  }
  el.classList.remove("is-success", "is-warning", "is-error");
  if (style === "success") el.classList.add("is-success");
  if (style === "warning") el.classList.add("is-warning");
  if (style === "error") el.classList.add("is-error");
}

function setConnectionStateLabel(message) {
  const el = document.getElementById("connectionState");
  if (el) {
    const next = String(message || "");
    if (el.textContent !== next) {
      el.textContent = next;
    }
  }
}

function setConnectionHint(message) {
  const el = document.getElementById("connectionHint");
  if (!el) {
    return;
  }
  el.textContent = message || "";
}

function setConnectionStateView({ label, style = "info", hint = "" }) {
  setConnectionStateLabel(label);
  applyConnectionStateStyle(style);
  setConnectionHint(hint);
}

function validatePortInput(showError = true) {
  const bridgePort = document.getElementById("bridgePort");
  if (!(bridgePort instanceof HTMLInputElement)) {
    return { ok: false, reason: "ポート欄が見つかりません。" };
  }
  const parsed = parsePortInput(bridgePort.value);
  if (!parsed.ok) {
    if (showError) {
      setPortError(parsed.reason);
    }
  } else {
    setPortError("");
  }
  return parsed;
}

function setPortFieldEnabled(enabled) {
  const port = document.getElementById("bridgePort");
  const openBtn = document.getElementById("openPortDetail");
  if (port) port.disabled = !enabled;
  if (openBtn) openBtn.disabled = !enabled;
  if (!enabled) {
    setConnectionStateView({
      label: "連携オフ",
      style: "info",
      hint: "「PC アプリと連携する」をオンにすると、状態を表示します。",
    });
  }
}

/**
 * @param {Record<string, chrome.storage.StorageChange>} changes
 */
function applyStoragePatch(changes) {
  if (changes.bridgeEnabled) {
    const el = document.getElementById("bridgeEnabled");
    if (el) {
      el.checked = Boolean(changes.bridgeEnabled.newValue);
    }
    setPortFieldEnabled(Boolean(changes.bridgeEnabled.newValue));
  }
  if (changes.autoClickMatchingPostBtn) {
    const el = document.getElementById("autoClickMatchingPostBtn");
    if (el) {
      el.checked = Boolean(changes.autoClickMatchingPostBtn.newValue);
    }
  }
  if (changes.keyboardShortcutEnter) {
    const el = document.getElementById("keyboardShortcutEnter");
    if (el instanceof HTMLInputElement) {
      el.checked = Boolean(changes.keyboardShortcutEnter.newValue);
    }
  }
  if (changes.keyboardShortcutSpace) {
    const el = document.getElementById("keyboardShortcutSpace");
    if (el instanceof HTMLInputElement) {
      el.checked = Boolean(changes.keyboardShortcutSpace.newValue);
    }
  }
  if (changes.keyboardShortcutEscape) {
    const el = document.getElementById("keyboardShortcutEscape");
    if (el instanceof HTMLInputElement) {
      el.checked = Boolean(changes.keyboardShortcutEscape.newValue);
    }
  }
  if (changes.keyboardShortcutBackspace) {
    const el = document.getElementById("keyboardShortcutBackspace");
    if (el instanceof HTMLInputElement) {
      el.checked = Boolean(changes.keyboardShortcutBackspace.newValue);
    }
  }
  if (changes.bridgePort) {
    const bridgePortEl = document.getElementById("bridgePort");
    const editingPort =
      bridgePortEl instanceof HTMLInputElement && document.activeElement === bridgePortEl;
    if (!editingPort && bridgePortEl instanceof HTMLInputElement) {
      bridgePortEl.value = String(clampPort(changes.bridgePort.newValue));
    }
  }
  validatePortInput(false);
  void refreshBridgeState();
}

/**
 * @param {{ refreshBridge?: boolean }} opts
 */
async function persistSyncSettings(opts = {}) {
  const refreshBridge = Boolean(opts.refreshBridge);
  const form = readExtensionFormState();
  if (!form) {
    return;
  }
  const portEl = document.getElementById("bridgePort");
  const parsed =
    portEl instanceof HTMLInputElement ? parsePortInput(portEl.value) : { ok: false };
  const { bridgePort } = await chrome.storage.sync.get({ bridgePort: BR.DEFAULT_PORT });
  const port = parsed.ok ? parsed.value : clampPort(bridgePort);
  try {
    await chrome.storage.sync.set({
      bridgeEnabled: form.bridgeEnabled,
      bridgePort: port,
      autoClickMatchingPostBtn: form.autoClickMatchingPostBtn,
      keyboardShortcutEnter: form.keyboardShortcutEnter,
      keyboardShortcutSpace: form.keyboardShortcutSpace,
      keyboardShortcutEscape: form.keyboardShortcutEscape,
      keyboardShortcutBackspace: form.keyboardShortcutBackspace,
    });
    setStatus("保存しました", "success", 1800);
    if (refreshBridge) {
      await refreshBridgeState();
    }
  } catch (err) {
    setStatus(`保存に失敗しました。（${String(err?.message || err)}）`, "error");
  }
}

async function persistBridgeEnabled() {
  await persistSyncSettings({ refreshBridge: true });
}

async function persistAutoClickOnly() {
  await persistSyncSettings({ refreshBridge: false });
}

async function persistPortValue(portNum) {
  const form = readExtensionFormState();
  if (!form) {
    return;
  }
  try {
    await chrome.storage.sync.set({
      bridgeEnabled: form.bridgeEnabled,
      bridgePort: portNum,
      autoClickMatchingPostBtn: form.autoClickMatchingPostBtn,
      keyboardShortcutEnter: form.keyboardShortcutEnter,
      keyboardShortcutSpace: form.keyboardShortcutSpace,
      keyboardShortcutEscape: form.keyboardShortcutEscape,
      keyboardShortcutBackspace: form.keyboardShortcutBackspace,
    });
    const el = document.getElementById("bridgePort");
    if (el instanceof HTMLInputElement) {
      el.value = String(portNum);
    }
    setStatus("ポートを保存しました", "success", 1800);
    await refreshBridgeState();
  } catch (err) {
    setStatus(`保存に失敗しました。（${String(err?.message || err)}）`, "error");
  }
}

function scheduleDebouncedPortSave() {
  if (portDebounceTimer != null) {
    clearTimeout(portDebounceTimer);
    portDebounceTimer = null;
  }
  portDebounceTimer = setTimeout(() => {
    portDebounceTimer = null;
    const parsed = validatePortInput(true);
    if (parsed.ok) {
      void persistPortValue(parsed.value);
    }
  }, PORT_DEBOUNCE_MS);
}

async function load() {
  const bridgeEnabledEl = document.getElementById("bridgeEnabled");
  const bridgePortEl = document.getElementById("bridgePort");
  const autoClickEl = document.getElementById("autoClickMatchingPostBtn");
  const kEnter = document.getElementById("keyboardShortcutEnter");
  const kSpace = document.getElementById("keyboardShortcutSpace");
  const kEsc = document.getElementById("keyboardShortcutEscape");
  const kBs = document.getElementById("keyboardShortcutBackspace");
  if (
    !(bridgeEnabledEl instanceof HTMLInputElement) ||
    !(bridgePortEl instanceof HTMLInputElement) ||
    !(autoClickEl instanceof HTMLInputElement) ||
    !(kEnter instanceof HTMLInputElement) ||
    !(kSpace instanceof HTMLInputElement) ||
    !(kEsc instanceof HTMLInputElement) ||
    !(kBs instanceof HTMLInputElement)
  ) {
    return;
  }
  const {
    bridgeEnabled,
    bridgePort,
    autoClickMatchingPostBtn,
    keyboardShortcutEnter,
    keyboardShortcutSpace,
    keyboardShortcutEscape,
    keyboardShortcutBackspace,
  } = await chrome.storage.sync.get({
    bridgeEnabled: false,
    bridgePort: BR.DEFAULT_PORT,
    autoClickMatchingPostBtn: false,
    keyboardShortcutEnter: true,
    keyboardShortcutSpace: true,
    keyboardShortcutEscape: true,
    keyboardShortcutBackspace: true,
  });
  bridgeEnabledEl.checked = Boolean(bridgeEnabled);
  bridgePortEl.value = String(clampPort(bridgePort));
  autoClickEl.checked = Boolean(autoClickMatchingPostBtn);
  kEnter.checked = Boolean(keyboardShortcutEnter);
  kSpace.checked = Boolean(keyboardShortcutSpace);
  kEsc.checked = Boolean(keyboardShortcutEscape);
  kBs.checked = Boolean(keyboardShortcutBackspace);
  const hintEl = document.getElementById("defaultPortHint");
  if (hintEl) {
    hintEl.textContent = `既定の番号: ${BR.DEFAULT_PORT}（PC アプリと同じにしてください）`;
  }
  setPortFieldEnabled(Boolean(bridgeEnabled));
  validatePortInput(false);
  await refreshBridgeState();
}

function mapBridgeState(status) {
  const state = String(status?.state || "");
  switch (state) {
    case "disabled":
      return {
        label: "連携オフ",
        style: "info",
        hint: "「PC アプリと連携する」をオンにすると、状態を表示します。",
      };
    case "no_rate_tab":
      return {
        label: "対戦ルームのタブ待ち",
        style: "warning",
        hint: "スマメイトの対戦ルーム（プロフィール）ページをひとつ開くとつながります。",
      };
    case "connecting":
      return {
        label: "つなぎ込み中…",
        style: "warning",
        hint: "PC の Arena Scan で連携オンかつ監視中か確認してください。",
      };
    case "retrying":
      return {
        label: "再接続を試しています…",
        style: "warning",
        hint: "PC 側の Arena Scan が動いているか、ポート番号が同じか確認してください。",
      };
    case "connected": {
      const lastSseActivityAtMs = Number(status?.lastSseActivityAtMs || 0);
      const nowMs = Number(status?.nowMs || Date.now());
      if (
        Number.isFinite(lastSseActivityAtMs) &&
        Number.isFinite(nowMs) &&
        lastSseActivityAtMs > 0 &&
        nowMs > lastSseActivityAtMs
      ) {
        const elapsedMs = nowMs - lastSseActivityAtMs;
        if (elapsedMs >= STALE_ACTIVITY_WARN_MS) {
          const elapsedSec = Math.floor(elapsedMs / 1000);
          return {
            label: `つながっています（部屋 ID の通知待ち ${elapsedSec} 秒）`,
            style: "warning",
            hint: "接続は維持されています。新しい部屋 ID が確定すると届きます。",
          };
        }
      }
      return {
        label: "つながっています（部屋 ID の通知待ち）",
        style: "success",
        hint: "この状態で対戦ルーム画面に部屋 ID が届きます。",
      };
    }
    case "error": {
      const raw = String(status?.detail || "").trim();
      let friendly = "Arena Scan に届いていません";
      if (/HTTP\s*404/i.test(raw) || /\b404\b/.test(raw)) {
        friendly = "Arena Scan に届いていません（番号の見直しを）";
      } else if (/timeout/i.test(raw)) {
        friendly = "応答がありません（PC アプリ側を確認）";
      }
      return {
        label: `問題: ${friendly}`,
        style: "error",
        hint: "詳細のポート番号が PC の Arena Scan と同じか、監視が始まっているか確認してください。",
      };
    }
    case "idle":
    default:
      return {
        label: "待機中",
        style: "warning",
        hint: "ツールバーのアイコンに理由が表示されます。番号は「詳細」から合わせてください。",
      };
  }
}

async function refreshBridgeState() {
  if (bridgeStateRefreshPromise) {
    return bridgeStateRefreshPromise;
  }
  bridgeStateRefreshPromise = (async () => {
    try {
      const resp = await chrome.runtime.sendMessage({ type: "SMASH_ARENA_GET_BRIDGE_STATUS" });
      if (!resp?.ok || !resp.status) {
        setConnectionStateView({
          label: "状態を取得できませんでした",
          style: "error",
          hint: "拡張機能を再読み込みしてから再度開いてください。",
        });
        return;
      }
      setConnectionStateView(mapBridgeState(resp.status));
    } catch {
      setConnectionStateView({
        label: "状態を取得できませんでした",
        style: "error",
        hint: "拡張機能を再読み込みしてから再度開いてください。",
      });
    }
  })().finally(() => {
    bridgeStateRefreshPromise = null;
  });
  return bridgeStateRefreshPromise;
}

function stopBridgeStatePolling() {
  if (bridgeStatePollTimer != null) {
    clearInterval(bridgeStatePollTimer);
    bridgeStatePollTimer = null;
  }
}

function startBridgeStatePolling() {
  stopBridgeStatePolling();
  if (document.visibilityState === "hidden") {
    return;
  }
  bridgeStatePollTimer = window.setInterval(() => {
    void refreshBridgeState();
  }, BRIDGE_STATUS_POLL_MS);
}

document.addEventListener("DOMContentLoaded", () => {
  const bridgeEnabledEl = document.getElementById("bridgeEnabled");
  const autoClickEl = document.getElementById("autoClickMatchingPostBtn");
  if (!(bridgeEnabledEl instanceof HTMLInputElement) || !(autoClickEl instanceof HTMLInputElement)) {
    return;
  }

  void load();
  startBridgeStatePolling();

  for (const id of [
    "keyboardShortcutEnter",
    "keyboardShortcutSpace",
    "keyboardShortcutEscape",
    "keyboardShortcutBackspace",
  ]) {
    const el = document.getElementById(id);
    if (el instanceof HTMLInputElement) {
      el.addEventListener("change", () => {
        void persistSyncSettings({ refreshBridge: false });
      });
    }
  }

  bridgeEnabledEl.addEventListener("change", () => {
    const on = bridgeEnabledEl.checked;
    setPortFieldEnabled(on);
    if (on) {
      void refreshBridgeState();
    }
    void persistBridgeEnabled();
  });

  autoClickEl.addEventListener("change", () => {
    void persistAutoClickOnly();
  });

  const portEl = document.getElementById("bridgePort");
  if (portEl instanceof HTMLInputElement) {
    portEl.addEventListener("input", () => {
      validatePortInput(true);
      scheduleDebouncedPortSave();
    });
    portEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const parsed = validatePortInput(true);
        if (parsed.ok) {
          void persistPortValue(parsed.value);
        }
      }
    });
  }

  const dlg = document.getElementById("portDetail");
  const openBtn = document.getElementById("openPortDetail");
  const portDetailCancel = document.getElementById("portDetailCancel");
  const portDetailOk = document.getElementById("portDetailOk");
  const openGuide = document.getElementById("openGuide");

  if (openBtn) {
    openBtn.addEventListener("click", async () => {
      if (!(dlg instanceof HTMLDialogElement)) return;
      const { bridgePort } = await chrome.storage.sync.get({ bridgePort: BR.DEFAULT_PORT });
      if (portEl instanceof HTMLInputElement) {
        portEl.value = String(clampPort(bridgePort));
        validatePortInput(false);
        dlg.showModal();
        portEl.focus();
        portEl.select();
      }
    });
  }

  if (portDetailCancel) {
    portDetailCancel.addEventListener("click", async () => {
      if (!(dlg instanceof HTMLDialogElement)) return;
      dlg.close();
      const { bridgePort } = await chrome.storage.sync.get({ bridgePort: BR.DEFAULT_PORT });
      if (portEl instanceof HTMLInputElement) {
        portEl.value = String(clampPort(bridgePort));
      }
      validatePortInput(false);
    });
  }

  if (portDetailOk) {
    portDetailOk.addEventListener("click", () => {
      const parsed = validatePortInput(true);
      if (!parsed.ok) {
        setStatus(parsed.reason, "error");
        return;
      }
      void persistPortValue(parsed.value).then(() => {
        if (dlg instanceof HTMLDialogElement) {
          dlg.close();
        }
      });
    });
  }

  if (openGuide) {
    openGuide.addEventListener("click", () => {
      chrome.tabs.create({ url: chrome.runtime.getURL("guide.html") });
    });
  }

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "sync") return;
    if (
      !changes.bridgeEnabled &&
      !changes.bridgePort &&
      !changes.autoClickMatchingPostBtn &&
      !changes.keyboardShortcutEnter &&
      !changes.keyboardShortcutSpace &&
      !changes.keyboardShortcutEscape &&
      !changes.keyboardShortcutBackspace
    ) {
      return;
    }
    const bridgePortEl = document.getElementById("bridgePort");
    const editingPort =
      bridgePortEl instanceof HTMLInputElement && document.activeElement === bridgePortEl;
    if (editingPort && changes.bridgePort) {
      applyStoragePatch(changes);
      return;
    }
    void load();
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      stopBridgeStatePolling();
      return;
    }
    startBridgeStatePolling();
    void refreshBridgeState();
  });

  window.addEventListener("beforeunload", () => {
    stopBridgeStatePolling();
  });
});
