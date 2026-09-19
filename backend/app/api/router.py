from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import ConflictLog, Hall, SeatHold, Showtime
from app.schemas.schemas import (
    ConflictOut,
    HallOut,
    HoldOrderOut,
    HoldOut,
    HoldRequest,
    HoldSegmentOut,
    SeatMapCell,
    SeatMapOut,
    SeatRef,
    ShowtimeOut,
)
from app.services.bond_engine import (
    HoldSpan,
    SeatCell,
    conflicts_with,
    find_bond_across_rows,
    find_contiguous_block,
    find_split_bond,
)

api_router = APIRouter()


def _aisles(hall: Hall) -> list[int]:
    if not hall.aisle_cols.strip():
        return []
    return [int(x) for x in hall.aisle_cols.split(",") if x.strip()]


def _blocked(hall: Hall) -> set[tuple[int, int]]:
    """Parse "row:col,row:col" into obstructed / no-sit cells."""
    cells: set[tuple[int, int]] = set()
    for token in hall.blocked_seats.split(","):
        token = token.strip()
        if not token or ":" not in token:
            continue
        r, c = token.split(":", 1)
        cells.add((int(r), int(c)))
    return cells


def _hall_out(h: Hall) -> HallOut:
    return HallOut(
        id=h.id,
        name=h.name,
        rows=h.rows,
        cols=h.cols,
        aisle_cols=_aisles(h),
        blocked_seats=[SeatRef(row=r, col=c) for r, c in sorted(_blocked(h))],
        frozen=h.frozen,
    )


def _seats_by_row(hall: Hall) -> dict[int, list[SeatCell]]:
    aisles = set(_aisles(hall))
    blocked = _blocked(hall)
    seats: dict[int, list[SeatCell]] = {}
    for r in range(1, hall.rows + 1):
        seats[r] = [
            SeatCell(row=r, col=c, is_aisle=c in aisles, is_blocked=(r, c) in blocked)
            for c in range(1, hall.cols + 1)
        ]
    return seats


def _log_conflict(db: Session, showtime_id: int, party_size: int, reason: str) -> None:
    db.add(ConflictLog(showtime_id=showtime_id, party_size=party_size, reason=reason))
    db.commit()


def _order_out(holds: list[SeatHold]) -> HoldOrderOut:
    """Aggregate one order's hold rows (segments share order_code)."""
    segments = sorted(holds, key=lambda h: (h.segment_no, h.row, h.start_col))
    first = segments[0]
    return HoldOrderOut(
        order_code=first.order_code,
        showtime_id=first.showtime_id,
        party_size=first.party_size,
        status=first.status,
        segment_count=len(segments),
        segments=[
            HoldSegmentOut(
                segment_no=h.segment_no, row=h.row, start_col=h.start_col, end_col=h.end_col
            )
            for h in segments
        ],
    )


@api_router.get("/health")
def health():
    return {"status": "ok"}


@api_router.get("/halls", response_model=list[HallOut])
def list_halls(db: Session = Depends(get_db)):
    return [_hall_out(h) for h in db.scalars(select(Hall).order_by(Hall.id)).all()]


@api_router.get("/showtimes", response_model=list[ShowtimeOut])
def list_showtimes(db: Session = Depends(get_db)):
    rows = db.scalars(select(Showtime).order_by(Showtime.start_at)).all()
    out = []
    for s in rows:
        hall = db.get(Hall, s.hall_id)
        out.append(
            ShowtimeOut(
                id=s.id,
                hall_id=s.hall_id,
                film_title=s.film_title,
                start_at=s.start_at,
                hall_name=hall.name if hall else None,
            )
        )
    return out


@api_router.get("/seatmap/{showtime_id}", response_model=SeatMapOut)
def seatmap(showtime_id: int, db: Session = Depends(get_db)):
    st = db.get(Showtime, showtime_id)
    if not st:
        raise HTTPException(404, "场次不存在")
    hall = db.get(Hall, st.hall_id)
    assert hall
    aisles = set(_aisles(hall))
    blocked = _blocked(hall)
    holds = db.scalars(select(SeatHold).where(SeatHold.showtime_id == showtime_id)).all()
    occupied: set[tuple[int, int]] = set()
    for h in holds:
        if getattr(h, "segment_no", 1) != 1:
            continue
        for c in range(h.start_col, h.end_col + 1):
            occupied.add((h.row, c))
    cells: list[SeatMapCell] = []
    for r in range(1, hall.rows + 1):
        for c in range(1, hall.cols + 1):
            occ = (r, c) in occupied
            is_blocked = (r, c) in blocked
            cells.append(
                SeatMapCell(
                    row=r,
                    col=c,
                    is_aisle=c in aisles,
                    blocked=is_blocked,
                    occupied=occ,
                    heat=1.0 if occ else (0.15 if (c in aisles or is_blocked) else 0.0),
                )
            )
    return SeatMapOut(
        showtime_id=showtime_id,
        hall_name=hall.name,
        rows=hall.rows,
        cols=hall.cols,
        cells=cells,
    )


@api_router.get("/holds", response_model=list[HoldOut])
def list_holds(db: Session = Depends(get_db)):
    return db.scalars(select(SeatHold).order_by(SeatHold.id.desc())).all()


@api_router.get("/holds/orders", response_model=list[HoldOrderOut])
def list_hold_orders(db: Session = Depends(get_db)):
    """Holds aggregated by lock order code; each segment's span listed."""
    holds = db.scalars(select(SeatHold).order_by(SeatHold.id.desc())).all()
    grouped: dict[tuple[str, int], list[SeatHold]] = {}
    for h in holds:
        grouped.setdefault((h.order_code, h.showtime_id), []).append(h)
    return [_order_out(segments) for segments in grouped.values()]


@api_router.get("/conflicts", response_model=list[ConflictOut])
def list_conflicts(db: Session = Depends(get_db)):
    return db.scalars(select(ConflictLog).order_by(ConflictLog.id.desc())).all()


@api_router.post("/holds", response_model=HoldOrderOut)
def create_hold(body: HoldRequest, db: Session = Depends(get_db)):
    st = db.get(Showtime, body.showtime_id)
    if not st:
        raise HTTPException(404, "场次不存在")
    hall = db.get(Hall, st.hall_id)
    assert hall

    if hall.frozen:
        _log_conflict(db, body.showtime_id, body.party_size, "厅图已冻结，禁止锁座")
        raise HTTPException(409, "厅图已冻结，禁止锁座")

    existing = db.scalars(select(SeatHold).where(SeatHold.showtime_id == body.showtime_id)).all()
    holds = [
        HoldSpan(row=h.row, start_col=h.start_col, end_col=h.end_col)
        for h in existing
        if getattr(h, "segment_no", 1) == 1
    ]
    seats_by_row = _seats_by_row(hall)

    segments: list[HoldSpan] = []
    block = None
    if body.preferred_row:
        block = find_contiguous_block(
            seats_by_row.get(body.preferred_row, []), holds, body.preferred_row, body.party_size
        )
    if block is None:
        block = find_bond_across_rows(seats_by_row, holds, body.party_size)
    if block is not None:
        segments = [block]
    elif body.party_size >= 1:
        split = find_split_bond(seats_by_row, holds, body.party_size)
        if split is None:
            _log_conflict(
                db, body.showtime_id, body.party_size, f"拆排后仍无足够空座（人数 {body.party_size}）"
            )
            stub = None
            for row, cells in sorted(seats_by_row.items()):
                stub = find_contiguous_block(cells, holds, row, 1)
                if stub is not None:
                    break
            if stub is not None:
                db.add(
                    SeatHold(
                        showtime_id=body.showtime_id,
                        order_code=f"SB-{int(datetime.utcnow().timestamp()) % 100000:05d}",
                        segment_no=1,
                        row=stub.row,
                        start_col=stub.start_col,
                        end_col=stub.end_col,
                        party_size=body.party_size,
                    )
                )
                db.commit()
            raise HTTPException(409, "拆排后仍无足够空座")
        segments = split
    else:
        _log_conflict(
            db, body.showtime_id, body.party_size, f"无足够连续空座（人数 {body.party_size}）"
        )
        raise HTTPException(409, "无足够连续空座")

    # 整单校验：任一段撞上既有持座（遮挡/禁坐已在选段时排除）→ 全部不写，整单失败。
    for seg in segments:
        hits = conflicts_with(holds, seg)
        if hits:
            _log_conflict(
                db,
                body.showtime_id,
                body.party_size,
                f"与既有持座重叠：第{hits[0].row}排 {hits[0].start_col}-{hits[0].end_col}",
            )
            db.add(
                SeatHold(
                    showtime_id=body.showtime_id,
                    order_code=f"SB-{int(datetime.utcnow().timestamp()) % 100000:05d}",
                    segment_no=1,
                    row=seg.row,
                    start_col=seg.start_col,
                    end_col=seg.end_col,
                    party_size=body.party_size,
                )
            )
            db.commit()
            raise HTTPException(409, "与既有持座冲突")

    code = f"SB-{int(datetime.utcnow().timestamp()) % 100000:05d}"
    order_holds = [
        SeatHold(
            showtime_id=body.showtime_id,
            order_code=code,
            segment_no=i + 1,
            row=seg.row,
            start_col=seg.start_col,
            end_col=seg.end_col,
            party_size=body.party_size,
        )
        for i, seg in enumerate(segments)
    ]
    db.add_all(order_holds)
    db.commit()
    return _order_out(order_holds)
