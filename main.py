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
import base64
from typing import Optional
from urllib.parse import urljoin, urlparse, quote
from contextlib import asynccontextmanager

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse, HTMLResponse, RedirectResponse
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

@app.get("/", tags=["UI"], response_class=HTMLResponse)
async def root():
    """Web UI for easy playback — works on all browsers via HLS.js."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>One Piece Player</title>
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <!-- HLS.js for Android/Chrome/Firefox HLS support -->
    <script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.11/dist/hls.min.js"></script>
    <style>
        :root {
            --bg: #0d0d0d;
            --surface: #1a1a1a;
            --primary: #e50914;
            --primary-dark: #b80710;
            --text: #ffffff;
            --text-secondary: #999;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 1rem;
        }
        .card {
            background: var(--surface);
            border-radius: 20px;
            padding: 2.5rem 2rem;
            width: 100%;
            max-width: 420px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.6);
            text-align: center;
        }
        .logo { font-size: 3rem; margin-bottom: 0.5rem; }
        h1 { font-size: 1.7rem; margin-bottom: 0.3rem; }
        .subtitle { color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 2rem; }
        input[type=number] {
            width: 100%;
            background: #252525;
            border: 2px solid #333;
            color: white;
            font-size: 1.3rem;
            padding: 0.9rem 1rem;
            border-radius: 12px;
            text-align: center;
            outline: none;
            transition: border-color 0.2s;
            margin-bottom: 1rem;
        }
        input[type=number]:focus { border-color: var(--primary); }
        .btn {
            width: 100%;
            background: var(--primary);
            color: white;
            border: none;
            padding: 1rem;
            font-size: 1.1rem;
            font-weight: 700;
            border-radius: 12px;
            cursor: pointer;
            transition: background 0.2s, transform 0.1s;
            margin-bottom: 0.75rem;
        }
        .btn:active { transform: scale(0.97); background: var(--primary-dark); }
        .btn:disabled { opacity: 0.5; cursor: default; }
        .btn-secondary {
            background: #2a2a2a;
            border: 2px solid #333;
            color: var(--text-secondary);
            font-size: 0.95rem;
        }
        .btn-secondary:hover { border-color: var(--primary); color: white; }
        .loader { display:none; margin-top:1rem; color:var(--text-secondary); font-size:0.85rem; }
        .error { display:none; margin-top:1rem; color:#ff4a4a; font-size:0.9rem; }
        /* Video player overlay */
        #playerOverlay {
            display: none;
            position: fixed;
            inset: 0;
            background: #000;
            z-index: 999;
            flex-direction: column;
        }
        #playerOverlay.active { display: flex; }
        #videoEl {
            width: 100%;
            flex: 1;
            background: #000;
            outline: none;
        }
        .player-bar {
            background: #111;
            padding: 0.75rem 1rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        .close-btn {
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 8px;
            padding: 0.5rem 1rem;
            font-size: 0.9rem;
            font-weight: 700;
            cursor: pointer;
        }
        .now-playing { color: var(--text-secondary); font-size: 0.85rem; }
    </style>
</head>
<body>
    <div class="card">
        <div class="logo">🏴‍☠️</div>
        <h1>One Piece</h1>
        <p class="subtitle">Enter episode number to stream</p>
        <input type="number" id="epInput" placeholder="e.g. 1089" inputmode="numeric" min="1">
        <button class="btn" id="playBtn" onclick="playEpisode()">▶ Play Episode</button>
        <button class="btn btn-secondary" onclick="location.href='/movies'">🎬 Watch Movies</button>
        <div class="loader" id="loader">⏳ Fetching stream… this may take a few seconds</div>
        <div class="error" id="errorMsg"></div>
    </div>

    <!-- Full-screen player overlay -->
    <div id="playerOverlay">
        <video id="videoEl" controls playsinline autoplay></video>
        <div class="player-bar">
            <button class="close-btn" onclick="closePlayer()">✕ Close</button>
            <span class="now-playing" id="nowPlaying"></span>
        </div>
    </div>

    <script>
        document.getElementById('epInput').addEventListener('keypress', e => {
            if (e.key === 'Enter') { e.preventDefault(); playEpisode(); }
        });

        async function playEpisode() {
            const ep = document.getElementById('epInput').value;
            if (!ep || ep < 1) { showError('Please enter a valid episode number.'); return; }
            setLoading(true);
            try {
                const res = await fetch('/api/stream/one-piece/' + ep);
                const data = await res.json();
                if (!res.ok || data.error) throw new Error(data.message || 'Failed to find stream.');
                if (!data.m3u8) throw new Error('No video stream found for this episode.');
                const referer = data.referer || '';
                const proxyUrl = '/api/proxy/m3u8?url=' + encodeURIComponent(data.m3u8) + '&referer=' + encodeURIComponent(referer);
                launchPlayer(proxyUrl, 'Episode ' + ep);
            } catch(err) {
                showError(err.message);
            } finally {
                setLoading(false);
            }
        }

        function launchPlayer(proxyUrl, label) {
            const overlay = document.getElementById('playerOverlay');
            const video = document.getElementById('videoEl');
            document.getElementById('nowPlaying').textContent = label;
            overlay.classList.add('active');

            // Destroy any existing HLS instance
            if (window._hls) { window._hls.destroy(); window._hls = null; }

            // Safari supports HLS natively; other browsers need HLS.js
            if (video.canPlayType('application/vnd.apple.mpegurl')) {
                video.src = proxyUrl;
                video.play().catch(() => {});
            } else if (Hls.isSupported()) {
                const hls = new Hls({ enableWorker: true });
                hls.loadSource(proxyUrl);
                hls.attachMedia(video);
                hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
                hls.on(Hls.Events.ERROR, (e, d) => {
                    if (d.fatal) showError('Stream error: ' + d.details);
                });
                window._hls = hls;
            } else {
                showError('Your browser does not support HLS video.');
            }
        }

        function closePlayer() {
            const video = document.getElementById('videoEl');
            video.pause();
            video.src = '';
            if (window._hls) { window._hls.destroy(); window._hls = null; }
            document.getElementById('playerOverlay').classList.remove('active');
        }

        function setLoading(on) {
            document.getElementById('playBtn').disabled = on;
            document.getElementById('playBtn').style.opacity = on ? '0.5' : '1';
            document.getElementById('loader').style.display = on ? 'block' : 'none';
            document.getElementById('errorMsg').style.display = 'none';
        }

        function showError(msg) {
            const el = document.getElementById('errorMsg');
            el.textContent = '❌ ' + msg;
            el.style.display = 'block';
        }
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


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


@app.get("/play/{episode}", tags=["Streaming"])
async def play_redirect(episode: int, request: Request):
    """
    Instantly redirects to the proxied stream.
    Perfect for a 1-step iOS Shortcut: "Open URL: https://api.com/play/1089"
    """
    try:
        data = await get_stream("one-piece", episode)
        if not data.m3u8:
            raise HTTPException(status_code=404, detail="No m3u8 stream found.")
            
        referer = data.referer or ""
        base_url = str(request.base_url)
        # Build the proxy URL manually with fully absolute path for AirPlay support
        proxy_url = f"{base_url}api/proxy/m3u8?url={quote(data.m3u8)}&referer={quote(referer)}"
        return RedirectResponse(url=proxy_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/movies", tags=["UI"], response_class=HTMLResponse)
async def movies_page():
    """Movie search & watch page – works on all browsers via HLS.js."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Movie Player</title>
    <meta name="apple-mobile-web-app-capable" content="yes">
    <script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.11/dist/hls.min.js"></script>
    <style>
        :root {
            --bg: #0d0d0d; --surface: #1a1a1a; --card: #222;
            --primary: #e50914; --primary-dark: #b80710;
            --text: #fff; --text-secondary: #999;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: var(--bg); color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            min-height: 100vh; display: flex; flex-direction: column;
            align-items: center; padding: 1.5rem 1rem;
        }
        header {
            width: 100%; max-width: 520px;
            display: flex; align-items: center; gap: 0.75rem;
            margin-bottom: 1.5rem;
        }
        .back-btn {
            background: #252525; border: none; color: var(--text-secondary);
            border-radius: 8px; padding: 0.5rem 0.8rem;
            font-size: 1rem; cursor: pointer;
        }
        header h1 { font-size: 1.4rem; }
        .search-row {
            width: 100%; max-width: 520px;
            display: flex; gap: 0.5rem; margin-bottom: 1.5rem;
        }
        .search-row input {
            flex: 1; background: #1e1e1e; border: 2px solid #333;
            color: white; font-size: 1rem; padding: 0.8rem 1rem;
            border-radius: 12px; outline: none; transition: border-color 0.2s;
        }
        .search-row input:focus { border-color: var(--primary); }
        .search-row button {
            background: var(--primary); color: white; border: none;
            border-radius: 12px; padding: 0.8rem 1.2rem;
            font-size: 1rem; font-weight: 700; cursor: pointer;
            transition: background 0.2s, transform 0.1s; white-space: nowrap;
        }
        .search-row button:active { transform: scale(0.97); background: var(--primary-dark); }
        .search-row button:disabled { opacity: 0.5; }
        #status { color: var(--text-secondary); font-size: 0.85rem; margin-bottom: 1rem; min-height: 1.2em; }
        #status.error { color: #ff4a4a; }
        #results { width: 100%; max-width: 520px; display: flex; flex-direction: column; gap: 0.75rem; }
        .result-card {
            background: var(--card); border-radius: 14px;
            padding: 1rem; display: flex; align-items: center; gap: 1rem;
            cursor: pointer; border: 2px solid transparent;
            transition: border-color 0.2s, background 0.2s;
        }
        .result-card:hover, .result-card:active { border-color: var(--primary); background: #2a2a2a; }
        .result-thumb {
            width: 56px; height: 80px; border-radius: 8px;
            object-fit: cover; background: #333; flex-shrink: 0;
        }
        .result-info { text-align: left; }
        .result-title { font-weight: 600; font-size: 0.95rem; margin-bottom: 0.25rem; }
        .result-meta { color: var(--text-secondary); font-size: 0.8rem; }
        .watch-btn {
            margin-left: auto; background: var(--primary); color: white;
            border: none; border-radius: 8px; padding: 0.5rem 0.9rem;
            font-size: 0.85rem; font-weight: 700; cursor: pointer; flex-shrink: 0;
        }
        /* Player overlay */
        #playerOverlay {
            display: none; position: fixed; inset: 0;
            background: #000; z-index: 999; flex-direction: column;
        }
        #playerOverlay.active { display: flex; }
        #videoEl { width: 100%; flex: 1; background: #000; outline: none; }
        .player-bar {
            background: #111; padding: 0.75rem 1rem;
            display: flex; align-items: center; gap: 0.75rem;
        }
        .close-btn {
            background: var(--primary); color: white; border: none;
            border-radius: 8px; padding: 0.5rem 1rem;
            font-size: 0.9rem; font-weight: 700; cursor: pointer;
        }
        .now-playing { color: var(--text-secondary); font-size: 0.85rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    </style>
</head>
<body>
    <header>
        <button class="back-btn" onclick="location.href='/'">← Back</button>
        <h1>🎬 Movie Player</h1>
    </header>

    <div class="search-row">
        <input type="text" id="queryInput" placeholder="Search any movie…" autocomplete="off">
        <button id="searchBtn" onclick="doSearch()">Search</button>
    </div>
    <div id="status"></div>
    <div id="results"></div>

    <!-- Full-screen player overlay -->
    <div id="playerOverlay">
        <video id="videoEl" controls playsinline autoplay></video>
        <div class="player-bar">
            <button class="close-btn" onclick="closePlayer()">✕ Close</button>
            <span class="now-playing" id="nowPlaying"></span>
        </div>
    </div>

    <script>
        document.getElementById('queryInput').addEventListener('keypress', e => {
            if (e.key === 'Enter') { e.preventDefault(); doSearch(); }
        });

        async function doSearch() {
            const q = document.getElementById('queryInput').value.trim();
            if (!q) return;
            setStatus('Searching…');
            document.getElementById('results').innerHTML = '';
            document.getElementById('searchBtn').disabled = true;
            try {
                const res = await fetch('/api/movie/search?keyword=' + encodeURIComponent(q));
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Search failed');
                if (!data.length) { setStatus('No results found.'); return; }
                setStatus(data.length + ' result(s) found — tap to watch');
                renderResults(data);
            } catch(err) {
                setStatus('❌ ' + err.message, true);
            } finally {
                document.getElementById('searchBtn').disabled = false;
            }
        }

        function renderResults(items) {
            const container = document.getElementById('results');
            container.innerHTML = '';
            items.forEach(item => {
                const card = document.createElement('div');
                card.className = 'result-card';
                card.innerHTML = `
                    <img class="result-thumb" src="${item.image || ''}" onerror="this.style.display='none'" alt="">
                    <div class="result-info">
                        <div class="result-title">${item.title}</div>
                        <div class="result-meta">${item.released || ''}</div>
                    </div>
                    <button class="watch-btn" onclick="watchMovie('${encodeId(item.id)}', '${escHtml(item.title)}')">▶ Watch</button>
                `;
                container.appendChild(card);
            });
        }

        function encodeId(id) { return encodeURIComponent(id); }
        function escHtml(s) { return s.replace(/'/g, "&#39;").replace(/"/g, "&quot;"); }

        async function watchMovie(movieId, title) {
            setStatus('⏳ Fetching stream…');
            try {
                const res = await fetch('/api/movie/stream/' + movieId);
                const data = await res.json();
                if (!res.ok || data.error) throw new Error(data.detail || data.message || 'Stream not found');
                if (!data.m3u8) throw new Error('No video stream found for this movie.');
                const referer = data.referer || '';
                const proxyUrl = '/api/proxy/m3u8?url=' + encodeURIComponent(data.m3u8) + '&referer=' + encodeURIComponent(referer);
                launchPlayer(proxyUrl, decodeURIComponent(title));
                setStatus('');
            } catch(err) {
                setStatus('❌ ' + err.message, true);
            }
        }

        function launchPlayer(proxyUrl, label) {
            const overlay = document.getElementById('playerOverlay');
            const video = document.getElementById('videoEl');
            document.getElementById('nowPlaying').textContent = label;
            overlay.classList.add('active');
            if (window._hls) { window._hls.destroy(); window._hls = null; }
            if (video.canPlayType('application/vnd.apple.mpegurl')) {
                video.src = proxyUrl;
                video.play().catch(() => {});
            } else if (Hls.isSupported()) {
                const hls = new Hls({ enableWorker: true });
                hls.loadSource(proxyUrl);
                hls.attachMedia(video);
                hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
                hls.on(Hls.Events.ERROR, (e, d) => { if (d.fatal) setStatus('❌ Stream error: ' + d.details, true); });
                window._hls = hls;
            } else {
                setStatus('❌ Your browser does not support HLS video.', true);
            }
        }

        function closePlayer() {
            const video = document.getElementById('videoEl');
            video.pause(); video.src = '';
            if (window._hls) { window._hls.destroy(); window._hls = null; }
            document.getElementById('playerOverlay').classList.remove('active');
        }

        function setStatus(msg, isError = false) {
            const el = document.getElementById('status');
            el.textContent = msg;
            el.className = isError ? 'error' : '';
        }
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/api/movie/search", tags=["Movies"])
async def search_movies(keyword: str = Query(..., min_length=1)):
    """Search for any movie by name using Gogoanime."""
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


@app.get("/api/movie/stream/{movie_id}", tags=["Movies"])
async def get_movie_stream(movie_id: str):
    """
    Get the stream for a movie (or any anime/movie slug).
    For movies, episode 1 is used as the single episode.
    """
    # Try as a single movie (episode 1), then try the slug directly as episode page
    episode_slug = f"{movie_id}-episode-1"
    soup = await fetch_page(f"/{episode_slug}")

    server_links = soup.select("a[data-video]")
    if not server_links:
        # Maybe it has no -episode-1 suffix (some movies are single page)
        soup = await fetch_page(f"/{movie_id}")
        server_links = soup.select("a[data-video]")
        if not server_links:
            raise HTTPException(status_code=404, detail=f"No streaming servers found for {movie_id}")

    sources: list[StreamSource] = []
    current_type = "raw"
    for link in server_links:
        embed_url = link.get("data-video", "").strip()
        name = link.text.strip().replace("Choose this server", "").strip()
        parent = link.find_parent(class_="server-type") or link.find_parent("div")
        if parent:
            parent_text = parent.get_text(strip=True).lower()
            if "sub" in parent_text:
                current_type = "sub"
            elif "dub" in parent_text:
                current_type = "dub"
        if embed_url:
            sources.append(StreamSource(name=name or "Unknown", url=embed_url, type=current_type))

    priority_order = ["vibeplayer", "gogocdn", "vidstream", "sbplay"]
    sorted_sources = sorted(
        sources,
        key=lambda s: next((i for i, p in enumerate(priority_order) if p in s.url.lower()), 99),
    )

    referer = f"{BASE_URL}/{episode_slug}"
    m3u8_url = None

    async def try_extract(source: StreamSource) -> str | None:
        return await extract_m3u8_from_embed(source.url, referer)

    tasks = [try_extract(s) for s in sorted_sources[:4]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, str) and result:
            m3u8_url = result
            break

    return StreamResponse(episode=1, m3u8=m3u8_url, referer=referer, sources=sources)


@app.get("/manga/{chapter}", tags=["Manga"], response_class=HTMLResponse)
async def read_manga(chapter: str):
    """
    Ad-free native manga reader.
    Scrapes images from readonepiece.com and serves them via our image proxy.
    Automatically tries colored manga first, and falls back to B&W if not available.
    """
    client = get_client()
    try:
        # Try colored version first
        colored_url = f"https://ww10.readonepiece.com/chapter/one-piece-digital-colored-comics-chapter-{chapter}/"
        resp = await client.get(colored_url)
        is_colored = True
        
        if resp.status_code != 200:
            # Fallback to Black-and-White version
            bw_url = f"https://ww10.readonepiece.com/chapter/one-piece-chapter-{chapter}/"
            resp = await client.get(bw_url)
            is_colored = False
            
            if resp.status_code != 200:
                raise HTTPException(status_code=404, detail="Chapter not found on source.")
                
        soup = BeautifulSoup(resp.text, "lxml")
        images = []
        for img in soup.find_all("img"):
            src = img.get("src", "").strip()
            if "cdn" in src or "mangap" in src or "pic" in src:
                if "logo" not in src.lower() and "icon" not in src.lower():
                    images.append(src)
        
        if not images:
            raise HTTPException(status_code=404, detail="No manga images found on page.")
            
        version_badge = "🎨 Colored" if is_colored else "📖 Standard B&W"
            
        # Build HTML
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            <title>One Piece - Chapter {chapter}</title>
            <style>
                body {{
                    background-color: #000;
                    color: white;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                }}
                .manga-page {{
                    width: 100%;
                    max-width: 800px;
                    display: block;
                    margin: 0 auto;
                }}
                .header, .footer {{
                    padding: 20px;
                    text-align: center;
                    background: #111;
                    width: 100%;
                    box-sizing: border-box;
                }}
                .header h2 {{ margin: 0; font-size: 1.5rem; color: #e50914; }}
                .header p {{ margin: 0; margin-top: 5px; color: #aaa; font-size: 0.9rem; }}
                .footer p {{ margin: 0; color: #888; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>One Piece - Chapter {chapter}</h2>
                <p>{version_badge}</p>
            </div>
        """
        
        for img_url in images:
            # Proxy the image to bypass hotlinking restrictions
            proxy_url = f"/api/proxy/image?url={quote(img_url)}&referer={quote('https://ww10.readonepiece.com/')}"
            html_content += f'<img class="manga-page" src="{proxy_url}" loading="lazy" alt="Manga Page">\n'
            
        html_content += f"""
            <div class="footer">
                <p>End of Chapter {chapter}</p>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── M3U8 & Image Proxies ────────────────────────────────────

@app.get("/api/proxy/image", tags=["Proxy"])
async def proxy_image(url: str, referer: str = ""):
    """Proxy image bytes to bypass hotlinking protection."""
    client = get_client()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if referer:
        headers["Referer"] = referer
    
    try:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "image/jpeg"),
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=86400"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Image fetch failed: {e}")

def _encode_url(url: str) -> str:
    """Base64-encode a URL for safe use in path segments."""
    return base64.urlsafe_b64encode(url.encode()).decode()


def _decode_url(encoded: str) -> str:
    """Decode a base64-encoded URL."""
    # Add padding if needed
    padded = encoded + "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(padded).decode()


@app.get("/api/proxy/m3u8", tags=["Proxy"])
async def proxy_m3u8(request: Request, url: str, referer: str = ""):
    """
    Smart proxy: serves m3u8 playlists (rewriting URLs) and binary
    segments (.ts) with the correct Referer header so VLC can play.
    """
    client = get_client()
    headers = {**HEADERS}
    if referer:
        headers["Referer"] = referer
        headers["Origin"] = f"{urlparse(referer).scheme}://{urlparse(referer).netloc}"

    try:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Proxy fetch failed: {e}")

    content_type = resp.headers.get("content-type", "")

    # Determine if this is an m3u8 playlist or a binary segment.
    # Check content-type first, then peek at the first bytes for #EXTM3U.
    # Avoid decoding large binary payloads.
    if "mpegurl" in content_type or url.endswith(".m3u8"):
        is_playlist = True
    elif len(resp.content) < 500_000 and resp.content[:7] == b"#EXTM3U":
        is_playlist = True
    else:
        is_playlist = False

    if is_playlist:
        # Rewrite relative/absolute URLs in the playlist so
        # sub-playlists and .ts segments also go through this proxy
        content = resp.text
        lines = content.split("\n")
        rewritten = []
        base_url = str(request.base_url)
        
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                # This is a URL line (segment or sub-playlist)
                absolute = urljoin(url, stripped)
                proxy_url = f"{base_url}api/proxy/m3u8?url={quote(absolute)}"
                if referer:
                    proxy_url += f"&referer={quote(referer)}"
                rewritten.append(proxy_url)
            else:
                rewritten.append(line)
        content = "\n".join(rewritten)

        return Response(
            content=content,
            media_type="application/vnd.apple.mpegurl",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache",
            },
        )
    else:
        # Binary segment (e.g. .ts video data) — return raw bytes
        return Response(
            content=resp.content,
            media_type=content_type or "video/mp2t",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=3600",
            },
        )


@app.get("/api/proxy/ts", tags=["Proxy"])
async def proxy_ts_segment(url: str, referer: str = ""):
    """
    Proxy a .ts video segment with the correct Referer header.
    Returns the raw binary data.
    """
    client = get_client()
    headers = {**HEADERS}
    if referer:
        headers["Referer"] = referer
        headers["Origin"] = f"{urlparse(referer).scheme}://{urlparse(referer).netloc}"

    try:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Segment proxy failed: {e}")

    return Response(
        content=resp.content,
        media_type=resp.headers.get("content-type", "video/mp2t"),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",
        },
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
