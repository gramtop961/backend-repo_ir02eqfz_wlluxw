"""
Database Schemas for CRE8 Platform

Each Pydantic model represents one MongoDB collection. Collection name is the lowercase class name.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime

# Core models
class Principle(BaseModel):
    key: str = Field(..., description="Slug key, e.g., 'capital'")
    title: str
    description: str
    color: Optional[str] = Field(None, description="Tailwind color hint, e.g., emerald")
    icon: Optional[str] = Field(None, description="Lucide icon name")

class PodcastEpisode(BaseModel):
    title: str
    slug: str
    summary: str
    audio_url: Optional[HttpUrl] = None
    guest_name: Optional[str] = None
    guest_bio: Optional[str] = None
    pillars: List[str] = []
    tags: List[str] = []
    published_at: Optional[datetime] = None

class Resource(BaseModel):
    title: str
    slug: str
    kind: str = Field(..., description="article|video|case-study|download")
    url: Optional[HttpUrl] = None
    pillars: List[str] = []
    tags: List[str] = []
    level: Optional[str] = Field(None, description="beginner|intermediate|advanced")

class ToolTemplate(BaseModel):
    title: str
    slug: str
    category: str = Field(..., description="acquisition|financing|leasing|...")
    format: str = Field(..., description="excel|pdf|gdoc|sheet|ppt")
    level: Optional[str] = None
    download_url: Optional[HttpUrl] = None
    pillars: List[str] = []
    tags: List[str] = []

class DirectoryProfile(BaseModel):
    name: str
    company: Optional[str] = None
    category: str = Field(..., description="Lender|Broker|Architect|...")
    pillars: List[str] = []
    location: Optional[str] = None
    website: Optional[HttpUrl] = None
    contact_email: Optional[str] = None
    bio: Optional[str] = None
    featured: bool = False
    worked_with_cre8: bool = False

class Event(BaseModel):
    title: str
    slug: str
    date: Optional[datetime] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    rsvp_url: Optional[HttpUrl] = None
    media_urls: List[HttpUrl] = []
