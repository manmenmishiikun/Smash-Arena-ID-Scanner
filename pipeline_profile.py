"""
監視ループの時間内訳を取るための軽量プロファイラ。

有効化: 環境変数 SMASH_ROOM_OCR_PROFILE=1（または true / yes / on）

一定フレームごとに DEBUG ログで平均 ms を出す（本番では無効のまま）。
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict

logger = logging.getLogger(__name__)


def _env_enabled() -> bool:
    v = os.environ.get("SMASH_ROOM_OCR_PROFILE", "").strip().lower()
    return v in ("1", "true", "yes", "on", "debug")


@dataclass
class PipelineProfiler:
    """フェーズ名ごとの累積秒・サンプル数。一定間隔で平均をログする。"""

    enabled: bool = field(default_factory=_env_enabled)
    interval_frames: int = 30
    _sums: DefaultDict[str, float] = field(default_factory=lambda: defaultdict(float))
    _counts: DefaultDict[str, int] = field(default_factory=lambda: defaultdict(int))
    _frame_count: int = 0
    _t0: float = field(default_factory=time.perf_counter)

    def reset_frame(self) -> None:
        if not self.enabled:
            return
        self._t0 = time.perf_counter()

    def add_phase(self, name: str, start: float) -> None:
        if not self.enabled:
            return
        dt = time.perf_counter() - start
        self._sums[name] += dt
        self._counts[name] += 1

    def end_frame(self) -> None:
        if not self.enabled:
            return
        self._frame_count += 1
        total = time.perf_counter() - self._t0
        self._sums["total"] += total
        self._counts["total"] += 1

        if self._frame_count % self.interval_frames != 0:
            return

        parts = []
        for key in sorted(self._sums.keys()):
            n = max(self._counts[key], 1)
            ms = (self._sums[key] / n) * 1000.0
            parts.append(f"{key}={ms:.1f}ms")
        logger.debug("[profile] avg over last ~%d frames: %s", self.interval_frames, " ".join(parts))
        self._sums.clear()
        self._counts.clear()
