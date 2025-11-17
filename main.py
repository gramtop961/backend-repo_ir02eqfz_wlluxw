import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timezone

from database import db, create_document, get_documents

# Optional dependency for RSS parsing
try:
    import feedparser  # type: ignore
except Exception:  # pragma: no cover
    feedparser = None

# Use requests to fetch feeds with proper headers (some hosts block default agents)
try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None

app = FastAPI(title="CRE8 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "CRE8 API is running"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from CRE8 backend API!"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:20]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:120]}"
    return response

# ------------ CRE8 Domain Endpoints -------------
# Simple response models
class Paginated(BaseModel):
    total: int
    items: list

# Principles
@app.get("/principles", response_model=Paginated)
def list_principles():
    items = get_documents("principle") if db else []
    return {"total": len(items), "items": items}

# Podcasts
@app.get("/podcasts", response_model=Paginated)
def list_podcasts(
    q: Optional[str] = None,
    guest: Optional[str] = None,
    pillar: Optional[str] = None,
    tag: Optional[str] = None,
):
    query = {}
    if guest:
        query["guest_name"] = {"$regex": guest, "$options": "i"}
    if pillar:
        query["pillars"] = pillar
    if tag:
        query["tags"] = tag
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"summary": {"$regex": q, "$options": "i"}},
            {"guest_name": {"$regex": q, "$options": "i"}},
        ]
    items = get_documents("podcastepisode", query) if db else []
    # Sort newest first if field present
    def _dt(v):
        if isinstance(v, datetime):
            return v
        try:
            return datetime.fromisoformat(v)
        except Exception:
            return datetime.min
    items.sort(key=lambda x: _dt(x.get("published_at", datetime.min)), reverse=True)
    return {"total": len(items), "items": items}

@app.get("/podcasts/{slug}")
def get_podcast_by_slug(slug: str):
    items = get_documents("podcastepisode", {"slug": slug}) if db else []
    if not items:
        raise HTTPException(status_code=404, detail="Episode not found")
    return items[0]

# Import from Transistor RSS
class ImportRequest(BaseModel):
    feed_url: Optional[str] = None


def _slugify(text: str) -> str:
    import re
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "episode"


def _fetch_feed_content(url: str) -> bytes:
    if requests is None:
        raise HTTPException(status_code=500, detail="HTTP client not available")
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CRE8Bot/1.0; +https://cre8.example)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.8",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch feed: {str(e)[:200]}")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f"Feed fetch failed with status {resp.status_code}")
    return resp.content


@app.post("/podcasts/import/transistor")
def import_transistor(req: ImportRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    if feedparser is None:
        raise HTTPException(status_code=500, detail="RSS parser not available. Install feedparser.")

    # Default Transistor feed pattern for a show hosted at https://creconnection.transistor.fm/
    default_feed = "https://feeds.transistor.fm/creconnection"
    feed_url = req.feed_url or os.getenv("TRANSISTOR_FEED_URL") or default_feed

    # Fetch with headers to avoid 403/HTML responses
    content = _fetch_feed_content(feed_url)
    parsed = feedparser.parse(content)
    if getattr(parsed, "bozo", 0):
        raise HTTPException(status_code=400, detail=f"Failed to parse feed: {getattr(parsed, 'bozo_exception', 'Unknown')}")

    created = 0
    updated = 0
    for entry in parsed.entries:
        title = entry.get("title", "Untitled")
        link = entry.get("link")
        guid = entry.get("id") or entry.get("guid") or link or title
        slug = _slugify(guid)[:80]
        if not slug:
            slug = _slugify(title)[:80]
        # Find audio enclosure
        audio_url = None
        for en in entry.get("enclosures", []) or []:
            if en.get("type", "").startswith("audio"):
                audio_url = en.get("href") or en.get("url")
                break
        if not audio_url:
            # Some feeds use links in the summary
            audio_url = entry.get("audio") or (entry.get("media_content", [{}])[0].get("url") if entry.get("media_content") else None)
        # Published date
        pub = None
        if entry.get("published_parsed"):
            try:
                pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pub = None
        elif entry.get("updated_parsed"):
            try:
                pub = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pub = None
        summary = entry.get("summary") or entry.get("subtitle") or ""
        author = entry.get("author") or (entry.get("authors", [{}])[0].get("name") if entry.get("authors") else None)
        tags = [t.get("term") for t in (entry.get("tags") or []) if t.get("term")]

        # Upsert behavior based on slug
        existing = list(db["podcastepisode"].find({"slug": slug}))
        payload = {
            "title": title,
            "slug": slug,
            "summary": summary,
            "audio_url": audio_url,
            "guest_name": author,
            "pillars": [],
            "tags": tags,
            "published_at": pub or datetime.now(timezone.utc),
            "external_url": link,
            "source": "transistor"
        }
        if existing:
            db["podcastepisode"].update_one({"_id": existing[0]["_id"]}, {"$set": payload, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}, "$currentDate": {"updated_at": True}})
            updated += 1
        else:
            create_document("podcastepisode", payload)
            created += 1

    total = db["podcastepisode"].count_documents({}) if db else 0
    return {"status": "ok", "created": created, "updated": updated, "total": total, "feed": feed_url}

# Resources
@app.get("/resources", response_model=Paginated)
def list_resources(
    pillar: Optional[str] = None,
    level: Optional[str] = None,
    kind: Optional[str] = None,
    tag: Optional[str] = None,
    q: Optional[str] = None,
):
    query = {}
    if pillar:
        query["pillars"] = pillar
    if level:
        query["level"] = level
    if kind:
        query["kind"] = kind
    if tag:
        query["tags"] = tag
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"slug": {"$regex": q, "$options": "i"}},
        ]
    items = get_documents("resource", query) if db else []
    return {"total": len(items), "items": items}

# Tools & Templates
@app.get("/tools", response_model=Paginated)
def list_tools(
    category: Optional[str] = None,
    format: Optional[str] = Query(None, alias="fmt"),
    level: Optional[str] = None,
    pillar: Optional[str] = None,
):
    query = {}
    if category:
        query["category"] = category
    if format:
        query["format"] = format
    if level:
        query["level"] = level
    if pillar:
        query["pillars"] = pillar
    items = get_documents("tooltemplate", query) if db else []
    return {"total": len(items), "items": items}

# Directory
@app.get("/directory", response_model=Paginated)
def list_directory(
    category: Optional[str] = None,
    pillar: Optional[str] = None,
    location: Optional[str] = None,
    featured: Optional[bool] = None,
    worked_with_cre8: Optional[bool] = Query(None, alias="worked"),
    q: Optional[str] = None,
):
    query = {}
    if category:
        query["category"] = category
    if pillar:
        query["pillars"] = pillar
    if location:
        query["location"] = {"$regex": location, "$options": "i"}
    if featured is not None:
        query["featured"] = featured
    if worked_with_cre8 is not None:
        query["worked_with_cre8"] = worked_with_cre8
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"company": {"$regex": q, "$options": "i"}},
            {"bio": {"$regex": q, "$options": "i"}},
        ]
    items = get_documents("directoryprofile", query) if db else []
    # Featured first
    items.sort(key=lambda x: (not x.get("featured", False), x.get("name", "")))
    return {"total": len(items), "items": items}

# Events
@app.get("/events", response_model=Paginated)
def list_events(upcoming: Optional[bool] = None):
    items = get_documents("event") if db else []
    # sort by date desc
    def _dt(v):
        if isinstance(v, datetime):
            return v
        try:
            return datetime.fromisoformat(v)
        except Exception:
            return datetime.min
    items.sort(key=lambda x: _dt(x.get("date", datetime.min)), reverse=True)
    if upcoming is not None:
        now = datetime.utcnow()
        if upcoming:
            items = [e for e in items if e.get("date") and _dt(e["date"]) >= now]
        else:
            items = [e for e in items if e.get("date") and _dt(e["date"]) < now]
    return {"total": len(items), "items": items}

# Seed minimal data for demo
@app.post("/seed")
def seed():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    created = {"principles": 0, "episodes": 0, "profiles": 0, "tools": 0, "resources": 0, "events": 0}
    # Principles
    principles = [
        ("capital", "Capital"), ("development", "Development"), ("investment", "Investment"),
        ("operations", "Operations"), ("leasing", "Leasing"), ("advisory", "Advisory"),
        ("technology", "Technology"), ("community", "Community")
    ]
    if db["principle"].count_documents({}) == 0:
        for key, title in principles:
            create_document("principle", {"key": key, "title": title, "description": f"Everything about {title}", "color": "emerald"})
            created["principles"] += 1
    # Podcast sample
    if db["podcastepisode"].count_documents({}) == 0:
        create_document("podcastepisode", {
            "title": "Building the Future of CRE Networks",
            "slug": "future-of-cre-networks",
            "summary": "How collaborative ecosystems unlock better deals.",
            "guest_name": "Alex Morgan",
            "pillars": ["community", "capital"],
            "tags": ["networking", "ecosystem"],
            "published_at": datetime.now(timezone.utc),
            "audio_url": "https://cdn.simplecast.com/audio.mp3"
        })
        created["episodes"] += 1
    # Directory sample
    if db["directoryprofile"].count_documents({}) == 0:
        create_document("directoryprofile", {
            "name": "Horizon Capital Partners",
            "company": "Horizon Capital",
            "category": "Lender",
            "pillars": ["capital"],
            "location": "New York, NY",
            "website": "https://example.com",
            "contact_email": "contact@example.com",
            "bio": "Debt and equity across core to opportunistic.",
            "featured": True,
            "worked_with_cre8": True
        })
        created["profiles"] += 1
    # Tool sample
    if db["tooltemplate"].count_documents({}) == 0:
        create_document("tooltemplate", {
            "title": "Acquisition Underwriting Model",
            "slug": "acq-underwriting-model",
            "category": "acquisition",
            "format": "excel",
            "level": "intermediate",
            "pillars": ["investment"],
            "download_url": "https://example.com/model.xlsx"
        })
        created["tools"] += 1
    # Resource sample
    if db["resource"].count_documents({}) == 0:
        create_document("resource", {
            "title": "LOI Template",
            "slug": "letter-of-intent-template",
            "kind": "download",
            "pillars": ["leasing"],
            "tags": ["templates"],
            "level": "beginner",
            "url": "https://example.com/loi.pdf"
        })
        created["resources"] += 1
    # Event sample
    if db["event"].count_documents({}) == 0:
        create_document("event", {
            "title": "CRE8 Summit 2025",
            "slug": "cre8-summit-2025",
            "date": datetime.now(timezone.utc),
            "location": "Austin, TX",
            "summary": "A gathering of dealmakers and innovators.",
            "rsvp_url": "https://example.com/rsvp"
        })
        created["events"] += 1

    return {"status": "ok", "created": created}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
