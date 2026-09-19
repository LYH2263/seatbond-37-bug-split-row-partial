"""Contiguous seat bonding: aisle columns break runs; holds conflict on overlap.

Split bonding (拆排): when no single row fits the party, multiple contiguous
segments across rows may share one order — but only via find_split_bond, which
keeps every segment inside one contiguous run (never crossing aisles, blocked
seats, or occupied seats) and uses as few segments as possible.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeatCell:
    row: int
    col: int
    is_aisle: bool = False
    is_blocked: bool = False  # 遮挡/禁坐格：不可占、不可跨


@dataclass(frozen=True)
class HoldSpan:
    row: int
    start_col: int
    end_col: int  # inclusive


def contiguous_runs(row_cells: list[SeatCell]) -> list[tuple[int, int]]:
    """Return inclusive (start_col, end_col) runs of sittable seats.

    Aisle columns and blocked (obstructed / no-sit) cells both break a run:
    a hold segment may neither include nor span across them.
    """
    runs: list[tuple[int, int]] = []
    start: int | None = None
    prev_col: int | None = None
    for cell in sorted(row_cells, key=lambda c: c.col):
        if cell.is_aisle or cell.is_blocked:
            if start is not None and prev_col is not None:
                runs.append((start, prev_col))
            start = None
            prev_col = None
            continue
        if start is None:
            start = cell.col
        elif prev_col is not None and cell.col != prev_col + 1:
            runs.append((start, prev_col))
            start = cell.col
        prev_col = cell.col
    if start is not None and prev_col is not None:
        runs.append((start, prev_col))
    return runs


def occupied_cols(holds: list[HoldSpan], row: int) -> set[int]:
    cols: set[int] = set()
    for h in holds:
        if h.row != row:
            continue
        for c in range(h.start_col, h.end_col + 1):
            cols.add(c)
    return cols


def free_segments(row_cells: list[SeatCell], holds: list[HoldSpan], row: int) -> list[tuple[int, int]]:
    """Maximal empty consecutive (start_col, end_col) segments still available in a row."""
    taken = occupied_cols(holds, row)
    segments: list[tuple[int, int]] = []
    for start, end in contiguous_runs(row_cells):
        seg_start: int | None = None
        prev: int | None = None
        for col in range(start, end + 1):
            if col in taken:
                if seg_start is not None and prev is not None:
                    segments.append((seg_start, prev))
                seg_start = None
                prev = None
                continue
            if seg_start is None:
                seg_start = col
            prev = col
        if seg_start is not None and prev is not None:
            segments.append((seg_start, prev))
    return segments


def find_contiguous_block(
    row_cells: list[SeatCell],
    holds: list[HoldSpan],
    row: int,
    party_size: int,
) -> HoldSpan | None:
    """Find leftmost contiguous empty seats of party_size in a row."""
    if party_size <= 0:
        return None
    for seg_start, seg_end in free_segments(row_cells, holds, row):
        if seg_end - seg_start + 1 >= party_size:
            return HoldSpan(row=row, start_col=seg_start, end_col=seg_start + party_size - 1)
    return None


def find_bond_across_rows(
    seats_by_row: dict[int, list[SeatCell]],
    holds: list[HoldSpan],
    party_size: int,
) -> HoldSpan | None:
    for row in sorted(seats_by_row.keys()):
        block = find_contiguous_block(seats_by_row[row], holds, row, party_size)
        if block is not None:
            return block
    return None


def find_split_bond(
    seats_by_row: dict[int, list[SeatCell]],
    holds: list[HoldSpan],
    party_size: int,
) -> list[HoldSpan] | None:
    """Split a party across rows into as few segments as possible."""
    if party_size <= 0:
        return None
    segments: list[HoldSpan] = []
    remaining = party_size
    for row in sorted(seats_by_row.keys()):
        if remaining <= 0:
            break
        cols = sorted(c.col for c in seats_by_row[row])
        if not cols:
            continue
        take = min(remaining, len(cols))
        segments.append(HoldSpan(row=row, start_col=cols[0], end_col=cols[take - 1]))
        remaining -= take
    if remaining > 0:
        return None
    return segments


def conflicts_with(existing: list[HoldSpan], candidate: HoldSpan) -> list[HoldSpan]:
    hits: list[HoldSpan] = []
    for h in existing:
        if h.row != candidate.row:
            continue
        if h.end_col < candidate.start_col or candidate.end_col < h.start_col:
            continue
        hits.append(h)
    return hits
