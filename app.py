import os
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import database
import onet_scraper
import refresher

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Onet Reader")

@app.on_event("startup")
def startup():
    database.init_db()
    refresher.start()

@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/api/categories")
def categories():
    return list(onet_scraper.CATEGORIES.keys())

@app.post("/api/refresh")
def refresh():
    """Odświeża artykuły z throttlingiem (min. 140 s między odświeżeniami)."""
    return refresher.refresh(trigger="user")

@app.get("/api/refresh/status")
def refresh_status():
    """Stan systemu odświeżania (throttling, quota, tryb, coverage)."""
    return refresher.status()

@app.get("/api/articles")
def articles(
    category: str = Query("wszystkie"),
    q: str = Query(""),
    sort: str = Query("newest"),
    unread: bool = Query(False),
):
    return database.get_articles(category, q, sort, unread)

@app.get("/api/articles/{link:path}/read")
def read_article(link: str):
    """Oznacza artykuł jako przeczytany i zapisuje jego treść."""
    arts = database.get_articles()
    if not any(a["link"] == link for a in arts):
        raise HTTPException(404, "Artykuł nie istnieje")

    details = onet_scraper.fetch_article_details(link)
    database.mark_read_and_store(link, details)

    row = [a for a in database.get_articles() if a["link"] == link][0]
    return {
        **row,
        "details": details,
    }

@app.get("/api/health")
def health():
    return {"status": "ok"}

app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()