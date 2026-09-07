"""FastAPI + NiceGUI entrypoint for the NASA Image Explorer."""

from fastapi import FastAPI, HTTPException, Query
from nicegui import ui

from nasa_api import DEFAULT_LIMIT, NasaApiError, search_images
from ui import render_main_page

app = FastAPI(title="NASA Image Explorer")


@app.get("/api/search")
async def api_search(
    q: str = Query(..., min_length=1, description="Search term"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=100),
) -> dict:
    """JSON view of the same search the UI performs."""
    try:
        results = await search_images(q, limit=limit)
    except NasaApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"query": q, "count": len(results), "results": results}


# Mounted last: NiceGUI claims "/", so any FastAPI route must be registered above.
ui.run_with(app, root=render_main_page, title="NASA Image Explorer", favicon="🚀")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
