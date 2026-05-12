import asyncio
import httpx
from bs4 import BeautifulSoup

async def test_mangapill():
    url = "https://mangapill.com/chapters/2-11089000/one-piece-chapter-1089"
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15) as client:
        r = await client.get(url)
        print(f"Status: {r.status_code}")
        soup = BeautifulSoup(r.text, "lxml")
        images = []
        for img in soup.find_all("img"):
            src = img.get("data-src") or img.get("src", "")
            if "cdn" in src or "mangapill" in src or "pic" in src:
                if not "logo" in src.lower() and not "icon" in src.lower():
                    images.append(src)
        print(f"Found {len(images)} potential manga images.")
        if images:
            img_url = images[0]
            print(f"First image: {img_url}")
            # Test hotlinking
            r2 = await client.get(img_url, headers={"Referer": "https://mangapill.com/"})
            print(f"With Referer: {r2.status_code}")
            r3 = await client.get(img_url)
            print(f"No Referer: {r3.status_code}")

if __name__ == "__main__":
    asyncio.run(test_mangapill())
