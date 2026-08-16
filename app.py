import os
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import database
import onet_scraper

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Onet Reader")

@app.on_event("startup")
def startup():
    database.init_db()

@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/api/categories")
def categories():
    return list(onet_scraper.CATEGORIES.keys())

@app.post("/api/refresh")
def refresh():
    """Scrapuje wszystkie kategorie i zapisuje nowe artykuły."""
    added = 0
    errors = {}
    for cat in onet_scraper.CATEGORIES:
        try:
            arts = onet_scraper.scrape_category(cat)
            for a in arts:
                database.upsert_article(a)
            added += len(arts)
        except Exception as e:
            errors[cat] = str(e)

    removed = database.cleanup_old()
    return {"added": added, "errors": errors, "purged": removed}

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