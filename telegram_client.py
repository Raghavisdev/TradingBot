from telethon import TelegramClient

from config import API_ID, API_HASH, SESSION_NAME

client = TelegramClient(
    SESSION_NAME,
    API_ID,
    API_HASH
)


async def connect_to_telegram():

    print("🚀 Starting Telegram Client...")

    await client.connect()

    print("✅ Connected to Telegram Server")

    authorized = await client.is_user_authorized()

    print("Authorized:", authorized)

    if not authorized:

        print("📱 Logging in...")

        await client.start()

    me = await client.get_me()

    print("================================")
    print("Logged in as:", me.first_name)
    print("Username    :", me.username)
    print("ID          :", me.id)
    print("================================")

    return client