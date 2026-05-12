import asyncio
import httpx
from bs4 import BeautifulSoup
import json

async def test_scrape():
    url = "https://ww10.readonepiece.com/chapter/one-piece-chapter-1089/"
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15) as client:
        r = await client.get(url)
        print(f"Status: {r.status_code}")
        soup = BeautifulSoup(r.text, "lxml")
        images = []
        # Inspect possible image containers
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "mangaclash" in src or "readonepiece" in src or "pages" in src or "cdn" in src or "pic" in src:
                if not "logo" in src.lower():
                    images.append(src)
        print(f"Found {len(images)} potential manga images.")
        if images:
            print("First 3:", images[:3])

if __name__ == "__main__":
    asyncio.run(test_scrape())
