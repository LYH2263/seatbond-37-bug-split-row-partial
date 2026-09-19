from datetime import datetime
from pydantic import BaseModel, Field


class SeatRef(BaseModel):
    row: int
    col: int


class HallOut(BaseModel):
    id: int
    name: str
    rows: int
    cols: int
    aisle_cols: list[int]
    blocked_seats: list[SeatRef] = []
    frozen: bool = False
    model_config = {"from_attributes": True}


class ShowtimeOut(BaseModel):
    id: int
    hall_id: int
    film_title: str
    start_at: datetime
    hall_name: str | None = None
    model_config = {"from_attributes": True}


class HoldOut(BaseModel):
    id: int
    showtime_id: int
    order_code: str
    segment_no: int = 1
    row: int
    start_col: int
    end_col: int
    party_size: int
    status: str
    model_config = {"from_attributes": True}


class HoldSegmentOut(BaseModel):
    segment_no: int
    row: int
    start_col: int
    end_col: int
    model_config = {"from_attributes": True}


class HoldOrderOut(BaseModel):
    """One lock order (锁座单号) aggregating every held segment."""

    order_code: str
    showtime_id: int
    party_size: int
    status: str
    segment_count: int
    segments: list[HoldSegmentOut]


class HoldRequest(BaseModel):
    showtime_id: int
    party_size: int = Field(ge=1, le=12)
    preferred_row: int | None = None
    allow_split: bool = False  # 拆排开关：默认关闭，开启才允许多排多段同单


class ConflictOut(BaseModel):
    id: int
    showtime_id: int
    party_size: int
    reason: str
    created_at: datetime
    model_config = {"from_attributes": True}


class SeatMapCell(BaseModel):
    row: int
    col: int
    is_aisle: bool
    blocked: bool = False
    occupied: bool
    heat: float


class SeatMapOut(BaseModel):
    showtime_id: int
    hall_name: str
    rows: int
    cols: int
    cells: list[SeatMapCell]
