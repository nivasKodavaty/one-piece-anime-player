from main import app, lifespan
from urllib.parse import unquote
import httpx
from bs4 import BeautifulSoup
import base64
import asyncio

async def build_static_test():
    print("Building static HTML test file...")
    transport = httpx.ASGITransport(app=app)
    async with lifespan(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            
            for chapter in ["112", "1111"]:
                print(f"\n--- Testing Chapter {chapter} ---")
                r = await client.get(f"/manga/{chapter}")
                html = r.text
                
                soup = BeautifulSoup(html, "lxml")
                images = soup.find_all("img", class_="manga-page")
                print(f"Found {len(images)} images in HTML.")
                
                # Process the first 3 images to save time and memory
                for img in images[:3]:
                    proxy_url = img.get("src")
                    print(f"Fetching proxy image: {proxy_url}")
                    
                    # Request the proxy image from our own FastAPI app
                    img_r = await client.get(proxy_url)
                    
                    if img_r.status_code == 200:
                        img_data = base64.b64encode(img_r.content).decode()
                        img["src"] = f"data:image/jpeg;base64,{img_data}"
                        print("Injected base64 image data.")
                    else:
                        print(f"Failed to fetch image: {img_r.status_code}")
                        
                # Remove remaining images
                for img in images[3:]:
                    img.decompose()
                    
                filename = f"manga_test_local_{chapter}.html"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(str(soup))
                print(f"Saved to {filename}")

if __name__ == "__main__":
    asyncio.run(build_static_test())
