from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


AnalyticsPeriod = Literal["all", "year", "month", "week"]


class PostTypeCountsOut(BaseModel):
    own_posts: int = 0
    replies: int = 0
    reposts: int = 0
    total: int = 0


class HeatmapCellOut(BaseModel):
    weekday: int = Field(ge=1, le=7)
    hour: int = Field(ge=0, le=23)
    count: int = 0


class AnalyticsOut(BaseModel):
    period: AnalyticsPeriod
    start_at: datetime | None = None
    counts: PostTypeCountsOut
    heatmap: list[HeatmapCellOut] = Field(default_factory=list)
