"""
room_id_detector.py

OBS から取得した部屋ID候補の逐次検出結果をもとに、
「何回連続で同じIDが検出されたら確定とするか」を判定するための
小さなステートマシン。

GUI やワーカースレッドから独立させることで、ロジック単体のテストや
閾値調整を容易にする。
"""

from dataclasses import dataclass
from typing import Optional


# OCR が同一部屋で揺れうる置換（双方向）
_CONFUSABLE_PAIRS = frozenset({
    ("0", "Q"),
    ("Q", "0"),
    ("6", "G"),
    ("G", "6"),
})


def is_confusable_equivalent(a: str, b: str) -> bool:
    """
    長さ5の部屋ID同士が、0/Q または 6/G の入れ替えのみで一致するか。
    クリップボード往復（4Q1PG <-> 401P6 等）の抑制に使う。
    """
    if len(a) != 5 or len(b) != 5:
        return False
    if a == b:
        return True
    for i in range(5):
        ca, cb = a[i], b[i]
        if ca == cb:
            continue
        if (ca, cb) not in _CONFUSABLE_PAIRS:
            return False
    return True


@dataclass
class DetectionConfig:
    """部屋ID確定ロジックのパラメータ（確定条件とポーリング間隔を1か所にまとめる）。"""

    confirm_needed: int = 2  # 何回連続で同じIDが検出されたら確定とするか
    poll_fast: float = 1.0  # 探索中・再探索の推奨待機（秒）
    poll_slow: float = 3.0  # 同一ID確定後の省電力ポーリング（秒）


@dataclass
class DetectionState:
    """現在までの検出状態。"""

    # ワーカーがクリップボードへコピー成功した後に更新される（確定直後ではない）
    last_copied_id: str = ""
    pending_id: str = ""
    pending_count: int = 0


@dataclass
class DetectionResult:
    """
    1フレーム分の処理結果。

    Attributes:
        confirmed_id: 今回新たに「確定」したID。なければ None。
        state: 更新後の状態。
        poll_interval: 推奨ポーリング間隔（秒）。高速・低速の切り替えに利用する。
    """

    confirmed_id: Optional[str]
    state: DetectionState
    poll_interval: float


class RoomIdDetector:
    """
    部屋ID検出のステートマシン。

    OCR から渡される room_id 候補を逐次与えることで、いつ「確定」したとみなすかを判定する。
    `process` は戻り値で意思決定する。`acknowledge_copy` はワーカーがクリップボード成功後に
    内部状態（last_copied_id）を更新するため、I/O 境界の外で呼ぶ。
    """

    def __init__(self, config: Optional[DetectionConfig] = None):
        self._cfg = config or DetectionConfig()
        self._state = DetectionState()

    @property
    def state(self) -> DetectionState:
        return self._state

    @property
    def poll_fast(self) -> float:
        return self._cfg.poll_fast

    @property
    def poll_slow(self) -> float:
        return self._cfg.poll_slow

    def reset(self) -> None:
        """テンプレート未検出など画面コンテキストが変わったときに状態をリセットする。"""
        self._state = DetectionState()

    def reset_pending_only(self) -> None:
        """
        連続確定カウントだけ捨てる。last_copied_id は維持する。
        テンプレが一瞬外れるなどで同じ部屋IDが再度確定しても通知・コピーを繰り返さないために使う。
        """
        self._state.pending_id = ""
        self._state.pending_count = 0

    def acknowledge_copy(self, room_id: str) -> None:
        """クリップボードへのコピーが成功したあとに呼ぶ。last_copied_id を更新する。"""
        self._state.last_copied_id = room_id

    def process(self, room_id: Optional[str]) -> DetectionResult:
        """
        1フレーム分の OCR 結果を処理し、確定IDと次回までのポーリング間隔を返す。

        Args:
            room_id: OCR によって検出された部屋ID候補。検出できなかった場合は None。
        """
        s = self._state

        # デフォルトは高速ポーリング
        poll_interval = self._cfg.poll_fast
        confirmed: Optional[str] = None

        if not room_id:
            # OCR 上は未検出だが、直前までコピーした ID は維持（再確定での二重通知を防ぐ）
            self._state.pending_id = ""
            self._state.pending_count = 0
            return DetectionResult(confirmed_id=None, state=self._state, poll_interval=poll_interval)

        # すでにコピー済みのIDと同じ、または 0/Q・6/G の揺れのみ → 再コピーしない
        if room_id == s.last_copied_id or (
            s.last_copied_id and is_confusable_equivalent(room_id, s.last_copied_id)
        ):
            self._state.pending_id = ""
            self._state.pending_count = 0
            poll_interval = self._cfg.poll_slow
            return DetectionResult(confirmed_id=None, state=self._state, poll_interval=poll_interval)

        # 前回と同じ候補が続いている
        if room_id == s.pending_id:
            self._state.pending_count += 1
            if self._state.pending_count == self._cfg.confirm_needed:
                # 確定（コピーはワーカー側。成功時のみ acknowledge_copy で last_copied_id を更新）
                confirmed = room_id
                self._state.pending_id = ""
                self._state.pending_count = 0
                poll_interval = self._cfg.poll_slow
        else:
            # 新しい候補が来たのでリセットしてカウント1
            self._state.pending_id = room_id
            self._state.pending_count = 1

        return DetectionResult(confirmed_id=confirmed, state=self._state, poll_interval=poll_interval)


if __name__ == "__main__":
    assert is_confusable_equivalent("4Q1PG", "401P6")
    assert not is_confusable_equivalent("4Q1PG", "4Q1PH")
    d = RoomIdDetector()
    d.state.last_copied_id = "4Q1PG"
    r = d.process("401P6")
    assert r.confirmed_id is None and r.poll_interval == d.poll_slow
    print("room_id_detector checks ok")
