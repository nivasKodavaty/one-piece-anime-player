import asyncio
import httpx
from bs4 import BeautifulSoup
import re

async def test_sources():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    }
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15) as client:
        # Test 1: TCB Scans
        try:
            print("Testing TCB Scans...")
            r = await client.get("https://tcbscans.me/")
            soup = BeautifulSoup(r.text, "lxml")
            links = soup.find_all("a", href=re.compile(r"chapter"))
            print(f"TCB Scans status: {r.status_code}, Found {len(links)} chapter links.")
            if links:
                print("Example link:", links[0]['href'])
        except Exception as e:
            print("TCB Scans error:", e)

        # Test 2: MangaDex API (Official/reliable)
        try:
            print("\nTesting MangaDex API...")
            # Search for One Piece
            r = await client.get("https://api.mangadex.org/manga?title=One Piece")
            data = r.json()
            if data['data']:
                manga_id = data['data'][0]['id']
                print(f"MangaDex One Piece ID: {manga_id}")
                
                # Get chapters
                r2 = await client.get(f"https://api.mangadex.org/manga/{manga_id}/feed?translatedLanguage[]=en&order[chapter]=desc&limit=1")
                ch_data = r2.json()
                if ch_data['data']:
                    ch_id = ch_data['data'][0]['id']
                    ch_num = ch_data['data'][0]['attributes']['chapter']
                    print(f"MangaDex Latest Chapter: {ch_num} (ID: {ch_id})")
            else:
                print("MangaDex: One Piece not found")
        except Exception as e:
            print("MangaDex error:", e)

if __name__ == "__main__":
    asyncio.run(test_sources())
