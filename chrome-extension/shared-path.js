/**
 * background（importScripts）と content（先行読込）で共有する pathname / host 判定。
 * URL パス中の数値はサイト側のルーム／プロフィール識別子であり、ゲームの部屋コードではない。
 */

/** @type {ReadonlySet<string>} */
const RATE_TAB_HOSTS = new Set(["smashmate.net", "smatch-jp.com"]);

/**
 * @param {string} pathname
 * @returns {boolean}
 */
function isRateProfilePath(pathname) {
  return /^\/rate\/\d+\/?$/.test(pathname);
}

/**
 * @param {string} hostname
 * @returns {boolean}
 */
function isSupportedRateHost(hostname) {
  return RATE_TAB_HOSTS.has(String(hostname || "").toLowerCase());
}

/**
 * @param {string} url
 * @returns {boolean}
 */
function isSupportedRateTabUrl(url) {
  try {
    const u = new URL(url);
    return isSupportedRateHost(u.hostname) && isRateProfilePath(u.pathname);
  } catch {
    return false;
  }
}

/**
 * `chrome.tabs.query` 用。両サイトの rate 配下。
 * @returns {string[]}
 */
function rateTabUrlPatterns() {
  return ["https://smashmate.net/rate/*", "https://smatch-jp.com/rate/*"];
}
