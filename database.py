import os
import logging
from supabase import create_client, Client

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://hxltadimmoelznmgxoig.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh4bHRhZGltbW9lbHpubWd4b2lnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NjgwMjE2OCwiZXhwIjoyMDkyMzc4MTY4fQ.WEEK-od4_P7PUgtNknTTa_NCq51pV72pw4fsRc7x3wk")

_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def get_user(telegram_id: int) -> dict | None:
    try:
        res = get_db().table("registered_users").select("*").eq("telegram_id", telegram_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"get_user({telegram_id}): {e}")
        return None


def create_user(telegram_id: int, name: str, nick: str, gender: str,
                style: str, schedule_type: str) -> dict | None:
    try:
        res = get_db().table("registered_users").insert({
            "telegram_id": telegram_id,
            "name": name,
            "nick": nick,
            "gender": gender,
            "style": style,
            "schedule_type": schedule_type,
        }).execute()
        logger.info(f"create_user({telegram_id}): data={res.data}")
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"create_user({telegram_id}) FAILED: {type(e).__name__}: {e}", exc_info=True)
        return None


def increment_meh(telegram_id: int) -> int:
    """Increment meh counter. Returns new count. Pauses user at 9."""
    try:
        user = get_user(telegram_id)
        if not user:
            return 0
        new_count = user["meh_count"] + 1
        update_data: dict = {"meh_count": new_count}
        if new_count >= 9:
            update_data["paused"] = True
        get_db().table("registered_users").update(update_data).eq("telegram_id", telegram_id).execute()
        return new_count
    except Exception as e:
        logger.error(f"increment_meh({telegram_id}): {e}")
        return 0


def resume_user(telegram_id: int) -> bool:
    try:
        get_db().table("registered_users").update(
            {"meh_count": 0, "paused": False}
        ).eq("telegram_id", telegram_id).execute()
        return True
    except Exception as e:
        logger.error(f"resume_user({telegram_id}): {e}")
        return False


def get_all_registered_users() -> list[dict]:
    try:
        res = get_db().table("registered_users").select("*").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"get_all_registered_users: {e}")
        return []
