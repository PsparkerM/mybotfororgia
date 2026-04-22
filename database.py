import os
import logging
import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://hxltadimmoelznmgxoig.supabase.co")
_DEFAULT_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh4bHRhZGltbW9lbHpubWd4b2lnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NjgwMjE2OCwiZXhwIjoyMDkyMzc4MTY4fQ"
    ".WEEK-od4_P7PUgtNknTTa_NCq51pV72pw4fsRc7x3wk"
)


def _headers() -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", _DEFAULT_KEY)
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _table_url(table: str = "registered_users") -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def get_user(telegram_id: int) -> dict | None:
    try:
        r = httpx.get(
            _table_url(),
            params={"telegram_id": f"eq.{telegram_id}", "select": "*"},
            headers=_headers(),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None
    except Exception as e:
        logger.error(f"get_user({telegram_id}): {type(e).__name__}: {e}", exc_info=True)
        return None


def create_user(telegram_id: int, name: str, nick: str, gender: str,
                style: str, schedule_type: str) -> dict | None:
    try:
        r = httpx.post(
            _table_url(),
            json={
                "telegram_id": telegram_id,
                "name": name,
                "nick": nick,
                "gender": gender,
                "style": style,
                "schedule_type": schedule_type,
            },
            headers=_headers(),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        logger.info(f"create_user({telegram_id}): OK, data={data}")
        return data[0] if data else None
    except Exception as e:
        logger.error(f"create_user({telegram_id}): {type(e).__name__}: {e}", exc_info=True)
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
        r = httpx.patch(
            _table_url(),
            params={"telegram_id": f"eq.{telegram_id}"},
            json=update_data,
            headers=_headers(),
            timeout=10,
        )
        r.raise_for_status()
        return new_count
    except Exception as e:
        logger.error(f"increment_meh({telegram_id}): {type(e).__name__}: {e}", exc_info=True)
        return 0


def resume_user(telegram_id: int) -> bool:
    try:
        r = httpx.patch(
            _table_url(),
            params={"telegram_id": f"eq.{telegram_id}"},
            json={"meh_count": 0, "paused": False},
            headers=_headers(),
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"resume_user({telegram_id}): {type(e).__name__}: {e}", exc_info=True)
        return False


def get_all_registered_users() -> list[dict]:
    try:
        r = httpx.get(
            _table_url(),
            params={"select": "*"},
            headers=_headers(),
            timeout=10,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        logger.error(f"get_all_registered_users: {type(e).__name__}: {e}", exc_info=True)
        return []


# ── Monitored group chats ──────────────────────────────────────────────────────

def get_monitored_chats() -> list[dict]:
    """Returns list of dicts with chat_id and target_user_id (None = respond to everyone)."""
    try:
        r = httpx.get(
            _table_url("monitored_chats"),
            params={"select": "chat_id,target_user_id,description"},
            headers=_headers(),
            timeout=10,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        logger.error(f"get_monitored_chats: {type(e).__name__}: {e}", exc_info=True)
        return []


def add_monitored_chat(chat_id: int, description: str = "", target_user_id: int | None = None) -> bool:
    try:
        payload: dict = {"chat_id": chat_id, "description": description}
        if target_user_id is not None:
            payload["target_user_id"] = target_user_id
        headers = _headers()
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        r = httpx.post(
            _table_url("monitored_chats"),
            json=payload,
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        logger.info(f"add_monitored_chat({chat_id}, target={target_user_id}): OK")
        return True
    except Exception as e:
        logger.error(f"add_monitored_chat({chat_id}): {type(e).__name__}: {e}", exc_info=True)
        return False


def remove_monitored_chat(chat_id: int) -> bool:
    try:
        r = httpx.delete(
            _table_url("monitored_chats"),
            params={"chat_id": f"eq.{chat_id}"},
            headers=_headers(),
            timeout=10,
        )
        r.raise_for_status()
        logger.info(f"remove_monitored_chat({chat_id}): OK")
        return True
    except Exception as e:
        logger.error(f"remove_monitored_chat({chat_id}): {type(e).__name__}: {e}", exc_info=True)
        return False
