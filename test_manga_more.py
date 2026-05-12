import asyncio
import httpx

async def test_manga_sites():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    urls = [
        "https://ww10.readonepiece.com/chapter/one-piece-chapter-112/",
        "https://ww10.readonepiece.com/chapter/one-piece-chapter-1089/",
        "https://mangapill.com/chapters/2-10112000/one-piece-chapter-112",
        "https://mangapill.com/chapters/2-11089000/one-piece-chapter-1089",
        "https://tcbscans.com/manga/one-piece/chapter-112",
        "https://www.mangaread.org/manga/one-piece/chapter-112/",
    ]
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=10) as client:
        for url in urls:
            try:
                r = await client.get(url)
                print(f"Status: {r.status_code} - {url}")
            except Exception as e:
                print(f"Error: {e} - {url}")

if __name__ == "__main__":
    asyncio.run(test_manga_sites())
