import asyncio
import websockets
import json

async def main():
    uri = "ws://127.0.0.1:8000/ws/book/PROD1"
    print(f"Connecting to {uri} ...")
    async with websockets.connect(uri) as ws:
        print("Connected! Listening for 5 seconds of snapshots...\n")
        for _ in range(5):
            msg = await ws.recv()
            data = json.loads(msg)
            print(json.dumps(data, indent=2))
        print("\nClosing connection...")

if __name__ == "__main__":
    asyncio.run(main())
