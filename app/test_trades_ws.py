import asyncio
import websockets
import json

async def main():
    uri = "ws://127.0.0.1:8000/ws/trades"
    print(f"Connecting to {uri} ...")
    async with websockets.connect(uri) as ws:
        print("Connected! Waiting for live trade updates...\n")
        try:
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                print("💥 Trade executed:")
                print(json.dumps(data, indent=2))
        except KeyboardInterrupt:
            print("\nClosed manually.")

if __name__ == "__main__":
    asyncio.run(main())
