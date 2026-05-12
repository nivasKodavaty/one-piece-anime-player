import asyncio
import httpx
from bs4 import BeautifulSoup

async def test_colored():
    # Expected URL format for colored chapters
    url = "https://ww10.readonepiece.com/chapter/one-piece-digital-colored-comics-chapter-112/"
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15) as client:
        r = await client.get(url)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "lxml")
            images = []
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if "cdn" in src or "mangap" in src or "pic" in src:
                    if "logo" not in src.lower() and "icon" not in src.lower():
                        images.append(src)
            print(f"Found {len(images)} potential colored manga images.")
            if images:
                print("First 3:", images[:3])

if __name__ == "__main__":
    asyncio.run(test_colored())
