import asyncio
import httpx

async def test_mangasee():
    headers = {"User-Agent": "Mozilla/5.0"}
    urls = [
        "https://mangasee123.com/read-online/One-Piece-chapter-112.html",
        "https://mangasee123.com/read-online/One-Piece-chapter-1089.html",
        "https://mangasee123.com/read-online/One-Piece-chapter-1111.html",
        "https://tcb-scans.com/manga/one-piece/chapter-1111",
        "https://tcbscans.com/manga/one-piece/chapter-1111",
    ]
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=10) as client:
        for url in urls:
            try:
                r = await client.get(url)
                print(f"Status: {r.status_code} - {url}")
            except Exception as e:
                print(f"Error: {e} - {url}")

if __name__ == "__main__":
    asyncio.run(test_mangasee())
