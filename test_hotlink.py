import asyncio
import httpx

async def test_hotlink():
    url = "https://cdn.readonepiece.com/file/mangap/2/11089000/1.jpeg?t=1691353344"
    
    # Test without referer
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        print(f"No Referer Status: {r.status_code}")
        
    # Test with referer
    async with httpx.AsyncClient(timeout=10, headers={"Referer": "https://ww10.readonepiece.com/"}) as client:
        r2 = await client.get(url)
        print(f"With Referer Status: {r2.status_code}")

if __name__ == "__main__":
    asyncio.run(test_hotlink())
