const BR = globalThis.SMASH_ARENA_BRIDGE || { DEFAULT_PORT: 2206, SSE_PATH: "/events" };

function clampPort(n) {
  const x = Number.parseInt(String(n), 10);
  if (!Number.isFinite(x)) return BR.DEFAULT_PORT;
  return Math.max(1, Math.min(65535, x));
}

function updateUrlPreview() {
  const port = clampPort(document.getElementById("bridgePort").value);
  const el = document.getElementById("urlPreview");
  if (el) {
    el.textContent = `http://127.0.0.1:${port}${BR.SSE_PATH}`;
  }
}

function setPortFieldEnabled(enabled) {
  const port = document.getElementById("bridgePort");
  const wrap = document.getElementById("urlPreviewWrap");
  if (port) port.disabled = !enabled;
  if (wrap) wrap.style.opacity = enabled ? "1" : "0.5";
}

async function load() {
  const { bridgeEnabled, bridgePort, autoClickMatchingPostBtn } =
    await chrome.storage.sync.get({
      bridgeEnabled: false,
      bridgePort: BR.DEFAULT_PORT,
      autoClickMatchingPostBtn: false,
    });
  document.getElementById("bridgeEnabled").checked = Boolean(bridgeEnabled);
  document.getElementById("bridgePort").value = String(clampPort(bridgePort));
  document.getElementById("autoClickMatchingPostBtn").checked = Boolean(
    autoClickMatchingPostBtn
  );
  setPortFieldEnabled(Boolean(bridgeEnabled));
  updateUrlPreview();
}

async function save() {
  const enabled = document.getElementById("bridgeEnabled").checked;
  const port = clampPort(document.getElementById("bridgePort").value);
  const autoClickMatchingPostBtn = document.getElementById(
    "autoClickMatchingPostBtn"
  ).checked;
  await chrome.storage.sync.set({
    bridgeEnabled: enabled,
    bridgePort: port,
    autoClickMatchingPostBtn,
  });
  document.getElementById("bridgePort").value = String(port);
  updateUrlPreview();
  const status = document.getElementById("status");
  status.textContent = "保存しました。数秒以内に接続が更新されます。";
  status.classList.add("is-success");
  setTimeout(() => {
    status.textContent = "";
    status.classList.remove("is-success");
  }, 2800);
}

function onBridgeEnabledChange() {
  const on = document.getElementById("bridgeEnabled").checked;
  setPortFieldEnabled(on);
}

document.addEventListener("DOMContentLoaded", () => {
  load();

  document.getElementById("save").addEventListener("click", save);

  document.getElementById("bridgeEnabled").addEventListener("change", () => {
    onBridgeEnabledChange();
  });

  document.getElementById("bridgePort").addEventListener("input", () => {
    updateUrlPreview();
  });

  document.getElementById("bridgePort").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      save();
    }
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "sync") return;
    if (
      changes.bridgeEnabled ||
      changes.bridgePort ||
      changes.autoClickMatchingPostBtn
    ) {
      load();
    }
  });
});
