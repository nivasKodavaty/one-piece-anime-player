import asyncio
import httpx

async def test_urls():
    ch = "1089"
    urls = [
        f"https://ww10.readonepiece.com/chapter/one-piece-chapter-{ch}/",
        f"https://mangasee123.com/read-online/One-Piece-chapter-{ch}.html",
        f"https://mangaplus.shueisha.co.jp/viewer/{ch}", # MangaPlus uses unique IDs, won't work
        f"https://w14.mangafreak.net/Read1_One_Piece_{ch}"
    ]
    
    headers = {"User-Agent": "Mozilla/5.0"}
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=10) as client:
        for url in urls:
            try:
                r = await client.get(url)
                print(f"{url} -> Status: {r.status_code}")
                if r.status_code == 200:
                    if "Chapter" in r.text or "chapter" in r.text.lower() or "One Piece" in r.text:
                        print(f"  [SUCCESS] {url} works predictably!")
            except Exception as e:
                print(f"{url} -> Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_urls())
