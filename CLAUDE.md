# Motivational Telegram Bot — Technical Reference

## What This Is
A personal motivational Telegram bot that sends scheduled messages to a group of friends experiencing burnout. Three daily phases: morning wake-up, daytime focus, evening reflection. Admin controls via Telegram commands.

---

## Infrastructure
| Component   | Service                        | Notes                                       |
|-------------|--------------------------------|---------------------------------------------|
| Server      | Railway                        | Auto-deploy from GitHub `main` branch       |
| Repository  | GitHub (PsparkerM/mybotfororgia) | Push to main = deploy                     |
| Database    | None (MVP)                     | Users + schedule hardcoded in config.py     |
| Scheduler   | APScheduler (MemoryJobStore)   | Jobs recreated from config on every startup |

> Supabase (PostgreSQL) is planned for Phase 2 (Admin Panel) when dynamic schedule editing is needed.

---

## Tech Stack
- **Language**: Python 3.11+
- **Telegram**: python-telegram-bot v20.7 (async, polling mode)
- **Scheduler**: APScheduler 3.10.4 with `AsyncIOScheduler` + `CronTrigger`
- **Timezone**: Europe/Moscow (UTC+3), managed via `pytz`
- **Deployment**: Railway + Nixpacks (auto-detects Python, installs requirements.txt)

---

## Project Structure
```
├── main.py              # Entry point: init bot + scheduler + start polling
├── config.py            # BOT_TOKEN, ADMIN_ID, USERS dict, SCHEDULE dict
├── scheduler.py         # APScheduler instance + job setup + send_scheduled_message()
├── handlers.py          # /start, /status, /sendnow, /broadcast (admin_only decorator)
├── messages/
│   ├── __init__.py
│   └── pools.py         # MORNING[], DAY[], EVENING[] message lists + MESSAGES dict
├── requirements.txt
├── Procfile             # worker: python main.py
├── railway.toml         # Railway build + deploy config
├── .env.example         # Template for local dev
└── .gitignore
```

---

## How to Add a Friend
1. Friend opens bot → sends /start → sees their ID in the reply
2. Add their ID to `config.py`:
```python
USERS = {
    123456789: "Артём",
}
SCHEDULE = {
    123456789: {
        "morning": "07:00",
        "day":     "13:00",
        "evening": "21:00",
    },
}
```
3. `git push origin main` → Railway auto-deploys

---

## Environment Variables
```bash
BOT_TOKEN=8257083630:AAEpcdfFKVqw33_1BM3U0eowsE__FkSROEw
ADMIN_ID=6135518022
TZ=Europe/Moscow
```
Set on Railway dashboard → Variables tab. Never commit `.env` to git.

---

## Admin Commands (only for ADMIN_ID=6135518022)
| Command | Description |
|---------|-------------|
| `/status` | Список всех джобов и время следующей отправки |
| `/sendnow morning\|day\|evening` | Немедленно отправить фазу всем пользователям |
| `/broadcast <текст>` | Отправить произвольный текст всем пользователям |

---

## Railway Deploy Config
```toml
# railway.toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "python main.py"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

---

## Local Development
```bash
git clone https://github.com/PsparkerM/mybotfororgia.git
cd mybotfororgia
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in BOT_TOKEN
python main.py
```

---

## Critical Rule
Schedule is law. Every job must have: exact time, specific `telegram_id`, specific message content. `misfire_grace_time=120` ensures messages missed during Railway restart are still delivered within 2 minutes.

## Phase Roadmap
1. **Phase 1 (current — MVP)**: Hardcoded users + schedule, static message pools, polling
2. **Phase 2**: Supabase + Telegram inline admin panel (dynamic schedule management)
3. **Phase 3**: Anthropic Claude API — dynamic message generation + "Help" button
