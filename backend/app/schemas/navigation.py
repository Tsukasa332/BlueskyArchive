from pydantic import BaseModel, Field

from app.schemas.posts import ActorOut


class FriendSummaryOut(BaseModel):
    actor: ActorOut
    count: int
    is_self: bool = False


class HashtagSummaryOut(BaseModel):
    tag: str
    count: int


class SidebarNavigationOut(BaseModel):
    friends: list[FriendSummaryOut] = Field(default_factory=list)
    hashtags: list[HashtagSummaryOut] = Field(default_factory=list)
