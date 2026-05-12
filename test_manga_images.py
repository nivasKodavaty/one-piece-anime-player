import asyncio
import httpx

async def test_mangadex_images():
    ch_id = "fe45defe-7ebb-4d60-ad21-b362c981a665"
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://api.mangadex.org/at-home/server/{ch_id}")
        data = r.json()
        print("MangaDex Chapter Data Keys:", data.keys())
        if 'baseUrl' in data and 'chapter' in data:
            base_url = data['baseUrl']
            hash = data['chapter']['hash']
            data_arr = data['chapter']['data']
            print(f"Base URL: {base_url}")
            print(f"Hash: {hash}")
            print(f"First image: {data_arr[0]}")
            print(f"Total images: {len(data_arr)}")
            print(f"Full URL example: {base_url}/data/{hash}/{data_arr[0]}")
        else:
            print("Failed to get image data:", data)

if __name__ == "__main__":
    asyncio.run(test_mangadex_images())
