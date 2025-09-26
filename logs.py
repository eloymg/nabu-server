import asyncio

from aioesphomeapi import APIClient, LogLevel


async def main():
    api = APIClient(address="192.168.0.24", port=6053, password="")

    # Connect to the ESPHome device
    await api.connect(login=True)

    def a(state):
        print(state)

    # Subscribe to Home Assistant states
    api.subscribe_logs(a, LogLevel.LOG_LEVEL_DEBUG)

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Disconnecting...")
        await api.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
