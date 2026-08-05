from telethon import events

from engine.pipeline import process_message


# ======================================================
# GEMTOOLS TELEGRAM CHANNEL
# ======================================================

GEMTOOLS_CHAT_ID = -1001998961899


def register_handlers(client):

    @client.on(events.NewMessage)
    async def new_message_handler(event):

        # Ignore every other Telegram chat
        if event.chat_id != GEMTOOLS_CHAT_ID:
            return

        print("\n" + "=" * 70)
        print("💎 NEW GEMTOOLS SIGNAL")
        print("=" * 70)

        print(event.raw_text)

        print("=" * 70)

        try:

            process_message(event.raw_text)

        except Exception as e:

            print("❌ Pipeline Error:", e)