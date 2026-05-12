"""
One Piece Anime Scraper API
============================
A lightweight FastAPI scraper that extracts HLS (m3u8) streaming URLs
from anitaku.to (Gogoanime). Designed to pair with the iOS Scriptable
shortcut for VLC playback.

Endpoints:
  GET /                         → Health check & docs
  GET /api/search?keyword=...   → Search anime titles
  GET /api/episodes/{anime_id}  → List episodes with numbers
  GET /api/stream/{anime_id}/{episode_number} → Get m3u8 stream URL

Deploy: Render, Railway, Vercel, or run locally with `uvicorn main:app`
"""

import re
import asyncio
from typing import Optional
from contextlib import asynccontextmanager

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel


# ─── Configuration ───────────────────────────────────────────
# The base domain for Gogoanime/Anitaku. Change this if the domain shifts.
BASE_URL = "https://anitaku.to"

# Fallback domains to try if the primary is down
FALLBACK_URLS = [
    "https://www14.gogoanimes.fi",
    "https://anitaku.pe",
]

# Common headers to mimic a browser
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ─── HTTP Client ─────────────────────────────────────────────
# Shared async client with connection pooling for performance
_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the shared httpx client lifecycle."""
    global _client
    _client = httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=True,
        timeout=httpx.Timeout(20.0, connect=10.0),
    )
    yield
    await _client.aclose()


def get_client() -> httpx.AsyncClient:
    assert _client is not None, "HTTP client not initialized"
    return _client


# ─── FastAPI App ─────────────────────────────────────────────
app = FastAPI(
    title="One Piece Anime Scraper API",
    description="Extracts HLS streaming URLs from Gogoanime/Anitaku for VLC playback",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Response Models ─────────────────────────────────────────
class SearchResult(BaseModel):
    id: str
    title: str
    url: str
    image: str | None = None
    released: str | None = None


class Episode(BaseModel):
    number: int
    episodeId: str
    url: str


class StreamSource(BaseModel):
    name: str
    url: str
    type: str  # "sub", "dub", "raw"


class StreamResponse(BaseModel):
    episode: int
    m3u8: str | None = None
    referer: str
    sources: list[StreamSource]


# ─── Scraping Helpers ────────────────────────────────────────

async def fetch_page(path: str, base: str | None = None) -> BeautifulSoup:
    """Fetch a page and return parsed BeautifulSoup, trying fallback domains."""
    client = get_client()
    urls_to_try = [f"{base or BASE_URL}{path}"] + [f"{fb}{path}" for fb in FALLBACK_URLS]

    last_error = None
    for url in urls_to_try:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            if len(resp.text) < 500:
                # Probably a placeholder/CF challenge page
                continue
            return BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            last_error = e
            continue

    raise HTTPException(
        status_code=502,
        detail=f"All source domains failed. Last error: {last_error}",
    )


async def extract_m3u8_from_embed(embed_url: str, referer: str) -> str | None:
    """Fetch an embed player page and extract the m3u8 URL."""
    client = get_client()
    try:
        resp = await client.get(embed_url, headers={"Referer": referer})
        resp.raise_for_status()

        # Method 1: Direct regex for m3u8 URLs
        m3u8_urls = re.findall(
            r'https?://[^\s"\',]+\.m3u8[^\s"\',]*', resp.text
        )
        if m3u8_urls:
            return m3u8_urls[0]

        # Method 2: Look for src = "..." patterns in JS
        src_match = re.search(
            r'(?:src|file|source|url)\s*[:=]\s*["\']'
            r'(https?://[^"\']+\.m3u8[^"\']*)["\']',
            resp.text,
        )
        if src_match:
            return src_match.group(1)

        return None
    except Exception:
        return None


# ─── API Endpoints ───────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root():
    """Health check and API info."""
    return {
        "status": "ok",
        "name": "One Piece Anime Scraper API",
        "version": "1.0.0",
        "source": BASE_URL,
        "endpoints": {
            "search": "/api/search?keyword=one+piece",
            "episodes": "/api/episodes/one-piece",
            "stream": "/api/stream/one-piece/1",
        },
    }


@app.get("/api/search", response_model=list[SearchResult], tags=["Anime"])
async def search_anime(keyword: str = Query(..., min_length=1)):
    """Search for anime by keyword."""
    path = f"/search.html?keyword={keyword.replace(' ', '+')}"
    soup = await fetch_page(path)

    results = []
    for item in soup.select(".items li, .last_episodes li"):
        link = item.find("a")
        if not link:
            continue

        href = link.get("href", "")
        title_tag = link.get("title") or link.text.strip()
        img = item.find("img")
        released = item.find("p", class_="released")

        # Extract anime ID from href: /category/one-piece → one-piece
        anime_id = href.replace("/category/", "").strip("/")
        if not anime_id:
            anime_id = href.strip("/").split("/")[-1]

        results.append(
            SearchResult(
                id=anime_id,
                title=title_tag.strip(),
                url=f"{BASE_URL}{href}",
                image=img.get("src") if img else None,
                released=released.text.strip().replace("Released: ", "") if released else None,
            )
        )

    return results


@app.get("/api/episodes/{anime_id}", tags=["Anime"])
async def get_episodes(anime_id: str):
    """Get all episodes for an anime by its slug/ID."""
    soup = await fetch_page(f"/category/{anime_id}")

    # Extract episode links
    ep_links = soup.select(f'a[href*="{anime_id}-episode-"]')
    if not ep_links:
        # Try more generic pattern
        ep_links = soup.select('a[href*="episode"]')

    episodes = []
    seen = set()
    for link in ep_links:
        href = link.get("href", "").strip()
        if not href or href in seen:
            continue
        seen.add(href)

        # Extract episode number from href: /one-piece-episode-42 → 42
        num_match = re.search(r"episode-(\d+)", href)
        if not num_match:
            continue

        ep_num = int(num_match.group(1))
        ep_id = href.strip("/").split("/")[-1]

        episodes.append(
            Episode(
                number=ep_num,
                episodeId=ep_id,
                url=f"{BASE_URL}{href}" if not href.startswith("http") else href,
            )
        )

    # Sort by episode number
    episodes.sort(key=lambda e: e.number)

    # Get title
    title_tag = soup.find("h1")
    title = title_tag.text.strip() if title_tag else anime_id

    return {
        "id": anime_id,
        "title": title,
        "totalEpisodes": len(episodes),
        "episodes": episodes,
    }


@app.get("/api/stream/{anime_id}/{episode}", tags=["Streaming"])
async def get_stream(anime_id: str, episode: int):
    """
    Get streaming sources for a specific episode.
    Returns the best m3u8 URL and all available server sources.
    """
    episode_slug = f"{anime_id}-episode-{episode}"
    soup = await fetch_page(f"/{episode_slug}")

    # Extract all server embed URLs from data-video attributes
    server_links = soup.select("a[data-video]")
    if not server_links:
        raise HTTPException(
            status_code=404,
            detail=f"No streaming servers found for {episode_slug}",
        )

    # Categorize servers by type (sub/dub/raw)
    sources: list[StreamSource] = []
    type_sections = soup.select(".server-type, .anime_muti_link ul")

    # Build sources list with type detection
    current_type = "raw"
    for link in server_links:
        embed_url = link.get("data-video", "").strip()
        name = link.text.strip().replace("Choose this server", "").strip()

        # Detect type from parent section
        parent = link.find_parent(class_="server-type") or link.find_parent("div")
        if parent:
            parent_text = parent.get_text(strip=True).lower()
            if "sub" in parent_text:
                current_type = "sub"
            elif "dub" in parent_text:
                current_type = "dub"

        if embed_url:
            sources.append(
                StreamSource(name=name or "Unknown", url=embed_url, type=current_type)
            )

    # Try to extract m3u8 from the preferred servers (HD-1, HD-2 first)
    # Prioritize vibeplayer.site as it gives direct m3u8
    priority_order = ["vibeplayer", "gogocdn", "vidstream", "sbplay"]
    sorted_sources = sorted(
        sources,
        key=lambda s: next(
            (i for i, p in enumerate(priority_order) if p in s.url.lower()), 99
        ),
    )

    # Extract m3u8 from the best available source (try up to 3)
    m3u8_url = None
    referer = f"{BASE_URL}/{episode_slug}"

    # Try sources in parallel for speed
    async def try_extract(source: StreamSource) -> str | None:
        return await extract_m3u8_from_embed(source.url, referer)

    tasks = [try_extract(s) for s in sorted_sources[:4]]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, str) and result:
            m3u8_url = result
            break

    return StreamResponse(
        episode=episode,
        m3u8=m3u8_url,
        referer=referer,
        sources=sources,
    )


# ─── Error Handlers ──────────────────────────────────────────

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": True, "message": str(exc.detail)},
    )


@app.exception_handler(502)
async def bad_gateway_handler(request, exc):
    return JSONResponse(
        status_code=502,
        content={"error": True, "message": str(exc.detail)},
    )


# ─── Entry Point ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=3030)
