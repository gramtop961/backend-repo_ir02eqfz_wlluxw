import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime

from database import db, create_document, get_documents

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
    items.sort(key=lambda x: x.get("published_at", datetime.min), reverse=True)
    return {"total": len(items), "items": items}

@app.get("/podcasts/{slug}")
def get_podcast_by_slug(slug: str):
    items = get_documents("podcastepisode", {"slug": slug}) if db else []
    if not items:
        raise HTTPException(status_code=404, detail="Episode not found")
    return items[0]

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
    items.sort(key=lambda x: x.get("date", datetime.min), reverse=True)
    if upcoming is not None:
        now = datetime.utcnow()
        if upcoming:
            items = [e for e in items if e.get("date") and e["date"] >= now]
        else:
            items = [e for e in items if e.get("date") and e["date"] < now]
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
            "published_at": datetime.utcnow(),
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
            "date": datetime.utcnow(),
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
