from app.services.bond_engine import (
    HoldSpan,
    SeatCell,
    conflicts_with,
    contiguous_runs,
    find_bond_across_rows,
    find_contiguous_block,
    find_split_bond,
    free_segments,
)


def _row(cols, aisles=(), blocked=(), row=1):
    return [
        SeatCell(row=row, col=c, is_aisle=(c in aisles), is_blocked=(c in blocked)) for c in cols
    ]


def test_aisle_breaks_runs():
    cells = _row(range(1, 11), aisles={5, 6})
    assert contiguous_runs(cells) == [(1, 4), (7, 10)]


def test_blocked_breaks_runs():
    cells = _row(range(1, 9), blocked={4})
    assert contiguous_runs(cells) == [(1, 3), (5, 8)]


def test_find_contiguous_skips_occupied():
    cells = _row(range(1, 9))
    holds = [HoldSpan(row=1, start_col=2, end_col=3)]
    block = find_contiguous_block(cells, holds, 1, 3)
    assert block == HoldSpan(row=1, start_col=4, end_col=6)


def test_find_contiguous_skips_blocked():
    cells = _row(range(1, 9), blocked={4})
    block = find_contiguous_block(cells, [], 1, 3)
    assert block == HoldSpan(row=1, start_col=1, end_col=3)
    # 左侧被占后，只能在遮挡格右侧找连座
    holds = [HoldSpan(row=1, start_col=1, end_col=3)]
    block = find_contiguous_block(cells, holds, 1, 3)
    assert block == HoldSpan(row=1, start_col=5, end_col=7)


def test_free_segments_around_holds():
    cells = _row(range(1, 9))
    holds = [HoldSpan(row=1, start_col=3, end_col=4)]
    assert free_segments(cells, holds, 1) == [(1, 2), (5, 8)]


def test_party_too_large_returns_none():
    cells = _row(range(1, 5), aisles={3})
    assert find_contiguous_block(cells, [], 1, 3) is None


def test_conflict_overlap():
    existing = [HoldSpan(row=2, start_col=4, end_col=6)]
    cand = HoldSpan(row=2, start_col=6, end_col=8)
    assert conflicts_with(existing, cand) == existing


def test_find_across_rows():
    seats = {
        1: _row(range(1, 5)),
        2: [SeatCell(row=2, col=c) for c in range(1, 9)],
    }
    holds = [HoldSpan(row=1, start_col=1, end_col=4)]
    block = find_bond_across_rows(seats, holds, 4)
    assert block == HoldSpan(row=2, start_col=1, end_col=4)


def _hall(rows, cols, aisles=(), blocked=()):
    # blocked 为 (row, col) 元组集合，按排拆分为各排的遮挡列
    return {
        r: _row(
            range(1, cols + 1),
            aisles=aisles,
            blocked={c for rr, c in blocked if rr == r},
            row=r,
        )
        for r in rows
    }


def test_split_fewest_segments_across_rows():
    # 每排最长连续 3，6 人需两段（3+3），而非更多碎段；同长时按排号、列号取
    seats = _hall(rows=(1, 2, 3), cols=8, aisles={4, 5})
    segs = find_split_bond(seats, [], 6)
    assert segs == [
        HoldSpan(row=1, start_col=1, end_col=3),
        HoldSpan(row=1, start_col=6, end_col=8),
    ]


def test_split_never_crosses_aisle():
    # 单段最长 3，过道 4/5 断开；4 人只能 3+1，且任何段不得含过道列
    seats = _hall(rows=(1, 2), cols=8, aisles={4, 5})
    segs = find_split_bond(seats, [], 4)
    assert segs is not None
    assert sum(s.end_col - s.start_col + 1 for s in segs) == 4
    for s in segs:
        assert not ({4, 5} & set(range(s.start_col, s.end_col + 1)))


def test_split_respects_blocked_cells():
    # 第1排 1-4 中 2 被遮挡 → 最长连续仅 2（3-4）；第2排 1-4 全空
    seats = _hall(rows=(1, 2), cols=4, blocked={(1, 2)})
    segs = find_split_bond(seats, [], 6)
    assert segs == [
        HoldSpan(row=1, start_col=3, end_col=4),
        HoldSpan(row=2, start_col=1, end_col=4),
    ]


def test_split_avoids_existing_holds():
    seats = _hall(rows=(1, 2), cols=6)
    holds = [HoldSpan(row=1, start_col=1, end_col=3), HoldSpan(row=2, start_col=4, end_col=6)]
    segs = find_split_bond(seats, holds, 5)
    assert segs == [
        HoldSpan(row=1, start_col=4, end_col=6),
        HoldSpan(row=2, start_col=1, end_col=2),
    ]


def test_split_insufficient_total_returns_none():
    seats = _hall(rows=(1, 2), cols=4, aisles={2})
    # 每排可用 1+2=3，两排共 6；要 7 人 → None
    assert find_split_bond(seats, [], 7) is None


def test_split_zero_party_returns_none():
    assert find_split_bond(_hall(rows=(1,), cols=4), [], 0) is None
