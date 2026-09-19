"""拆排锁座 API 测例：

- 关拆排：单段不够即 409 并写冲突；
- 开拆排：多排合计够 → 成功，多段共用同一锁座单号；
- 开拆排仍因过道 / 遮挡禁坐 / 冻结厅图失败 → 整单回滚，无残留段。
"""

from datetime import datetime

from sqlalchemy import select

from app.models.models import ConflictLog, Hall, SeatHold, Showtime


def _mk_showtime(db, name="测试厅", rows=2, cols=6, aisle_cols="3", blocked_seats="", frozen=False):
    hall = Hall(
        name=name,
        rows=rows,
        cols=cols,
        aisle_cols=aisle_cols,
        blocked_seats=blocked_seats,
        frozen=frozen,
    )
    db.add(hall)
    db.flush()
    st = Showtime(hall_id=hall.id, film_title="测试片", start_at=datetime(2026, 9, 18, 20, 0))
    db.add(st)
    db.commit()
    return hall, st


def _holds_of(db, showtime_id):
    return db.scalars(select(SeatHold).where(SeatHold.showtime_id == showtime_id)).all()


def _conflicts_of(db, showtime_id):
    return db.scalars(select(ConflictLog).where(ConflictLog.showtime_id == showtime_id)).all()


def test_split_disabled_fails_and_logs_conflict(client, db):
    _, st = _mk_showtime(db)  # 过道第3列 → 单排最长连续 3
    resp = client.post("/api/holds", json={"showtime_id": st.id, "party_size": 4})
    assert resp.status_code == 409
    assert _holds_of(db, st.id) == []
    logs = _conflicts_of(db, st.id)
    assert len(logs) == 1
    assert logs[0].party_size == 4
    assert "无足够连续空座" in logs[0].reason


def test_split_enabled_succeeds_with_shared_order_code(client, db):
    _, st = _mk_showtime(db)
    resp = client.post(
        "/api/holds", json={"showtime_id": st.id, "party_size": 4, "allow_split": True}
    )
    assert resp.status_code == 200
    order = resp.json()
    assert order["segment_count"] == 2
    assert order["party_size"] == 4
    segs = order["segments"]
    assert sum(s["end_col"] - s["start_col"] + 1 for s in segs) == 4
    # 每段自身连续且不跨过道（第3列）
    for s in segs:
        assert s["start_col"] <= s["end_col"]
        assert not (s["start_col"] <= 3 <= s["end_col"])

    # 落库：两段共用同一锁座单号，段号递增
    holds = _holds_of(db, st.id)
    assert len(holds) == 2
    assert {h.order_code for h in holds} == {order["order_code"]}
    assert sorted(h.segment_no for h in holds) == [1, 2]

    # 按单号聚合：一单两段，起止清晰
    orders = client.get("/api/holds/orders").json()
    assert len(orders) == 1
    assert orders[0]["order_code"] == order["order_code"]
    assert [(s["row"], s["start_col"], s["end_col"]) for s in orders[0]["segments"]] == [
        (s["row"], s["start_col"], s["end_col"]) for s in segs
    ]

    # 座位图同时点亮多段占用
    cells = client.get(f"/api/seatmap/{st.id}").json()["cells"]
    lit = {(c["row"], c["col"]) for c in cells if c["occupied"]}
    expect = set()
    for s in segs:
        expect |= {(s["row"], c) for c in range(s["start_col"], s["end_col"] + 1)}
    assert lit == expect


def test_split_single_row_still_preferred(client, db):
    _, st = _mk_showtime(db, rows=1, cols=6, aisle_cols="")
    resp = client.post(
        "/api/holds", json={"showtime_id": st.id, "party_size": 3, "allow_split": True}
    )
    assert resp.status_code == 200
    assert resp.json()["segment_count"] == 1


def test_split_fails_when_aisle_fragments_total_no_residue(client, db):
    # 过道第2列：每排 1+2=3 座，两排共 6；要 7 人，开拆排也不够
    _, st = _mk_showtime(db, rows=2, cols=4, aisle_cols="2")
    resp = client.post(
        "/api/holds", json={"showtime_id": st.id, "party_size": 7, "allow_split": True}
    )
    assert resp.status_code == 409
    assert _holds_of(db, st.id) == []  # 整单回滚，无残留段
    logs = _conflicts_of(db, st.id)
    assert len(logs) == 1
    assert "拆排后仍无足够空座" in logs[0].reason


def test_split_around_blocked_seats_succeeds(client, db):
    # 1:3 遮挡 → 可用段 (1-2)、(4-6) 共 5 座；5 人拆两段成功，段不含遮挡格
    _, st = _mk_showtime(db, rows=1, cols=6, aisle_cols="", blocked_seats="1:3")
    resp = client.post(
        "/api/holds", json={"showtime_id": st.id, "party_size": 5, "allow_split": True}
    )
    assert resp.status_code == 200
    segs = resp.json()["segments"]
    assert len(segs) == 2
    for s in segs:
        assert not (s["start_col"] <= 3 <= s["end_col"])
    cells = client.get(f"/api/seatmap/{st.id}").json()["cells"]
    blocked = {(c["row"], c["col"]) for c in cells if c["blocked"]}
    assert blocked == {(1, 3)}


def test_split_fails_when_blocked_seats_reduce_total_no_residue(client, db):
    # 遮挡后全场仅 5 座可用；6 人开拆排也整单失败，不留半成功多段
    _, st = _mk_showtime(db, rows=1, cols=6, aisle_cols="", blocked_seats="1:3")
    resp = client.post(
        "/api/holds", json={"showtime_id": st.id, "party_size": 6, "allow_split": True}
    )
    assert resp.status_code == 409
    assert _holds_of(db, st.id) == []
    assert len(_conflicts_of(db, st.id)) == 1


def test_split_disabled_does_not_split_even_with_switch_true_omitted(client, db):
    # 关拆排且不勾开关：单排最长 3，要 4 人 → 整单失败、不占座
    _, st = _mk_showtime(db)  # 过道第3列 → 单排最长连续 3
    resp = client.post("/api/holds", json={"showtime_id": st.id, "party_size": 4, "allow_split": False})
    assert resp.status_code == 409
    assert _holds_of(db, st.id) == []


def test_later_hold_cannot_overlap_any_segment_of_split_order(client, db):
    # 2 排 × 7 列，过道第4列 → 每排 run(1-3)、run(5-7) 各 3 座。
    # 4 人拆排：(1排1-3) + (1排5)。旧逻辑只认 segment_no==1，
    # 再锁 3 人会压到 (1排5-7) 与第二段重叠；修复后必须落到 (2排1-3)。
    _, st = _mk_showtime(db, rows=2, cols=7, aisle_cols="4")
    first = client.post(
        "/api/holds", json={"showtime_id": st.id, "party_size": 4, "allow_split": True}
    )
    assert first.status_code == 200
    segs = first.json()["segments"]
    assert [(s["row"], s["start_col"], s["end_col"]) for s in segs] == [
        (1, 1, 3),
        (1, 5, 5),
    ]

    second = client.post("/api/holds", json={"showtime_id": st.id, "party_size": 3})
    assert second.status_code == 200
    new_segs = second.json()["segments"]
    assert [(s["row"], s["start_col"], s["end_col"]) for s in new_segs] == [(2, 1, 3)]
    for ns in new_segs:
        for s in segs:
            if s["row"] != ns["row"]:
                continue
            assert ns["end_col"] < s["start_col"] or ns["start_col"] > s["end_col"]

    # 座位图点亮两段 + 新单的全部座位
    cells = client.get(f"/api/seatmap/{st.id}").json()["cells"]
    lit = {(c["row"], c["col"]) for c in cells if c["occupied"]}
    expect = set()
    for s in segs + new_segs:
        expect |= {(s["row"], c) for c in range(s["start_col"], s["end_col"] + 1)}
    assert lit == expect
    assert len(lit) == 7  # 4 + 3，无重复压座


def test_split_segment_never_spans_aisle_or_blocked(client, db):
    # 过道第3列：任何成功段都不得包含第3列，且总人数与各段长度一致
    _, st = _mk_showtime(db, rows=2, cols=6, aisle_cols="3")
    resp = client.post(
        "/api/holds", json={"showtime_id": st.id, "party_size": 6, "allow_split": True}
    )
    assert resp.status_code == 200
    segs = resp.json()["segments"]
    assert sum(s["end_col"] - s["start_col"] + 1 for s in segs) == 6
    for s in segs:
        assert not (s["start_col"] <= 3 <= s["end_col"])


def test_frozen_hall_rejects_even_when_seats_free(client, db):
    _, st = _mk_showtime(db, rows=2, cols=6, aisle_cols="", frozen=True)
    resp = client.post(
        "/api/holds", json={"showtime_id": st.id, "party_size": 2, "allow_split": True}
    )
    assert resp.status_code == 409
    assert "冻结" in resp.json()["detail"]
    assert _holds_of(db, st.id) == []
    logs = _conflicts_of(db, st.id)
    assert len(logs) == 1
    assert "冻结" in logs[0].reason
