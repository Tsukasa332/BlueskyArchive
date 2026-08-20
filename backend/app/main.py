from fastapi import FastAPI

from app.api.analytics import router as analytics_router
from app.api.navigation import router as navigation_router
from app.api.posts import router as posts_router

app = FastAPI(
    title="BlueskyArchive API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.include_router(posts_router, prefix="/api")
app.include_router(navigation_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
