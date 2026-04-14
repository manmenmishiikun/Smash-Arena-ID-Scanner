"""room_id_detector のステートマシン・同値判定の回帰テスト。"""

from room_id_detector import (
    DetectionConfig,
    RoomIdDetector,
    is_confusable_equivalent,
)


def test_is_confusable_equivalent_basic() -> None:
    assert is_confusable_equivalent("4Q1PG", "401P6")
    assert not is_confusable_equivalent("4Q1PG", "4Q1PH")
    assert is_confusable_equivalent("AAAAA", "AAAAA")


def test_confirm_after_two_same_reads() -> None:
    d = RoomIdDetector(DetectionConfig(confirm_needed=2))
    assert d.process("ABCDE").confirmed_id is None
    r = d.process("ABCDE")
    assert r.confirmed_id == "ABCDE"
    assert d.state.last_copied_id == "ABCDE"


def test_confusable_same_as_last_no_copy() -> None:
    d = RoomIdDetector()
    d.state.last_copied_id = "4Q1PG"
    r = d.process("401P6")
    assert r.confirmed_id is None
    assert r.poll_interval == d.poll_slow


def test_no_room_id_resets_pending() -> None:
    d = RoomIdDetector(DetectionConfig(confirm_needed=2))
    d.process("AAAAA")
    assert d.process(None).confirmed_id is None
    assert d.state.pending_count == 0


def test_poll_interval_fast_when_pending() -> None:
    d = RoomIdDetector(DetectionConfig(confirm_needed=3))
    r = d.process("ZZZZZ")
    assert r.poll_interval == d.poll_fast


def test_reset_pending_only() -> None:
    d = RoomIdDetector(DetectionConfig(confirm_needed=2))
    d.process("AAAAA")
    d.reset_pending_only()
    assert d.state.pending_count == 0
    assert d.state.last_copied_id == ""
