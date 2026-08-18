import os
import sys
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database
import license
import onet_scraper
import refresher

# W wersji skompilowanej (PyInstaller onefile) pliki dodatkowe (index.html)
# są rozpakowane do sys._MEIPASS; w dev używamy katalogu projektu.
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="News Reader")

@app.on_event("startup")
def startup():
    database.init_db()
    database.migrate_article_keys(onet_scraper.article_key)
    onet_scraper.migrate_legacy_categories()
    # Anti-tamper: jeśli klucz publiczny został podmieniony, nie startuj refreshera.
    if not license.check_pubkey():
        return
    refresher.start()

@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/api/categories")
def categories():
    return list(onet_scraper.CATEGORIES.keys())

@app.get("/api/status")
def system_status():
    """Stan licencji: licznik artykułów, blokada, kod systemu."""
    count = database.count_articles()
    unlocked = license.is_unlocked()
    locked = count >= license.LIMIT and not unlocked
    # Kod systemu zawsze dostępny — użytkownik może wprowadzić klucz
    # prewencyjnie (zanim baza osiągnie limit).
    return {
        "article_count": count,
        "limit": license.LIMIT,
        "locked": locked,
        "unlocked": unlocked,
        "system_code": license.system_code() if not unlocked else None,
    }

class UnlockReq(BaseModel):
    key: str

@app.post("/api/unlock")
def unlock(req: UnlockReq):
    if license.verify(license.system_code(), req.key):
        license.store_key(req.key)
        return {"ok": True, "unlocked": True}
    raise HTTPException(403, "Nieprawidłowy klucz")

@app.post("/api/refresh")
def refresh():
    """Odświeża artykuły z throttlingiem (min. 140 s między odświeżeniami)."""
    if database.count_articles() >= license.LIMIT and not license.is_unlocked():
        raise HTTPException(403, "Osiągnięto limit artykułów — wprowadź klucz, aby kontynuować")
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
    favorite: bool = Query(False),
    hide_stale: bool = Query(True),
):
    return database.get_articles(category, q, sort, unread, favorite, hide_stale)

@app.post("/api/articles/{link:path}/favorite")
def set_favorite(link: str, favorite: bool = Query(True)):
    """Ustawia lub zdejmuje oznaczenie artykułu jako ulubionego."""
    if not database.is_known(link):
        raise HTTPException(404, "Artykuł nie istnieje")
    database.set_favorite(link, favorite)
    return {"link": link, "is_favorite": 1 if favorite else 0}

@app.get("/api/articles/{link:path}/read")
def read_article(link: str):
    """Oznacza artykuł jako przeczytany i zapisuje jego treść."""
    row = database.get_article_by_key(link)
    if not row:
        raise HTTPException(404, "Artykuł nie istnieje")

    details = onet_scraper.fetch_article_details(link)
    database.mark_read_and_store(link, details)

    row = database.get_article_by_key(link)
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