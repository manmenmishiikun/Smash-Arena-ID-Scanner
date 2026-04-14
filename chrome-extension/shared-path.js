/**
 * background（importScripts）と content（先行読込）で共有する pathname 判定。
 * URL パス中の数値はプロフィール ID であり、部屋コードではない。
 *
 * @param {string} pathname
 * @returns {boolean}
 */
function isRateProfilePath(pathname) {
  return /^\/rate\/\d+\/?$/.test(pathname);
}
