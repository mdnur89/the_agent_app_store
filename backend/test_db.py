import asyncio
from db.client import db
from db.users.crud import get_or_create_user

async def main():
    await db.connect()
    try:
        user = await get_or_create_user("12345", "TestUser")
        print("Success:", user)
    except Exception as e:
        print("Error:", repr(e))
    finally:
        await db.disconnect()

asyncio.run(main())
