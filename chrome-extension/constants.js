/**
 * Python 側 `extension_bridge_server` の `SSE_PATH` / 既定ポートと揃える。
 * 変更時は `extension_bridge_server.py` も確認すること。
 */
globalThis.SMASH_ARENA_BRIDGE = Object.freeze({
  SSE_PATH: "/events",
  DEFAULT_PORT: 2206,
  /** 異常な SSE 応答で background のバッファが無制限に増えないようにする上限 */
  MAX_SSE_BUFFER_BYTES: 65536,
});
