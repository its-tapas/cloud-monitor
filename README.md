# cloud-monitor

A high-quality technical assistance bot for niche subreddits like **r/AWS**, **r/gcpcloud**, and **r/developersIndia**.

The bot uses Google Gemini to scan for complex cloud architecture queries and alerts the developer to provide expert, human-vetted solutions. This ensures Redditors get accurate, professional advice on AWS/GCP and Python development, reducing misinformation in technical threads.

---

## How It Works

```
Reddit (PRAW)          Gemini LLM              Developer
────────────           ──────────              ─────────
r/AWS         ──┐
r/gcpcloud    ──┼──► Keyword Filter ──► Complexity ──► Draft ──► Email / Telegram ──► Review
r/developersIndia ──┘    (local)         Analysis        Gen       Notification       & Post
```

1. **Intelligent Monitoring** – `RedditMonitor` polls configured subreddits every N minutes (default: 5) using [PRAW](https://praw.readthedocs.io/). Posts are pre-filtered by a local keyword list covering 70+ AWS, GCP, and Python terms.

2. **Contextual Analysis** – `LLMAnalyzer` sends pre-filtered posts to **Google Gemini** for deeper evaluation. Gemini returns a structured JSON verdict with a complexity score (1–10), technical tags, and a plain-English summary. Posts scoring ≥ 7 are classified as **High-Value Technical Gaps**.

3. **Draft Generation** – `DraftGenerator` asks Gemini to produce a detailed, production-grade Reddit reply grounded in official documentation patterns, with code examples and common pitfall warnings.

4. **Developer Notification** – `Notifier` delivers the draft via **email (SMTP)** and/or a **Telegram bot**, so the developer can review, fact-check, and post the refined answer.

---

## Project Structure

```
cloud-monitor/
├── src/
│   ├── config.py           # Environment-variable configuration
│   ├── reddit_monitor.py   # PRAW-based subreddit monitoring
│   ├── llm_analyzer.py     # Gemini analysis (High-Value detection)
│   ├── draft_generator.py  # Expert draft generation
│   └── notifier.py         # Email + Telegram notifications
├── tests/
│   ├── test_config.py
│   ├── test_reddit_monitor.py
│   ├── test_llm_analyzer.py
│   ├── test_draft_generator.py
│   └── test_notifier.py
├── main.py                 # Entry point
├── requirements.txt
├── .env.example            # Configuration template
└── README.md
```

---

## Setup

### Prerequisites

- Python 3.11+
- A [Reddit application](https://www.reddit.com/prefs/apps) (type: *script*, read-only)
- A [Google Gemini API key](https://aistudio.google.com/apikey)
- An SMTP account (e.g. Gmail with an App Password) **and/or** a Telegram bot

### 1. Clone & install dependencies

```bash
git clone https://github.com/its-tapas/cloud-monitor.git
cd cloud-monitor
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

Required variables:

| Variable | Description |
|---|---|
| `REDDIT_CLIENT_ID` | Reddit app client ID |
| `REDDIT_CLIENT_SECRET` | Reddit app client secret |
| `GEMINI_API_KEY` | Google Gemini API key |

At least one notification channel must be configured (see `.env.example`).

### 3. Run

```bash
python main.py
```

The bot will log its activity to stdout and send notifications whenever a High-Value post is detected.

---

## Running Tests

```bash
pip install -r requirements.txt
pytest -v
```

---

## Configuration Reference

All settings are controlled via environment variables (see `.env.example`).

| Variable | Default | Description |
|---|---|---|
| `REDDIT_SUBREDDITS` | `aws+gcpcloud+developersIndia` | `+`-separated list of subreddits |
| `REDDIT_POST_LIMIT` | `25` | Posts fetched per cycle |
| `REDDIT_POLL_INTERVAL_SECONDS` | `300` | Seconds between poll cycles |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Gemini model name |
| `GEMINI_ANALYSIS_TEMPERATURE` | `0.2` | Analysis determinism (lower = stricter) |
| `GEMINI_DRAFT_TEMPERATURE` | `0.7` | Draft creativity |
| `GEMINI_MAX_OUTPUT_TOKENS` | `2048` | Max tokens in generated draft |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## Notification Channels

### Email (Gmail example)

1. Enable 2-FA on your Google account.
2. Generate an [App Password](https://myaccount.google.com/apppasswords).
3. Set `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, and your credentials.

### Telegram

1. Message [@BotFather](https://t.me/BotFather) to create a bot and get the token.
2. Send a message to your bot and visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your `chat_id`.
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

---

## Architecture Decision Notes

- **Keyword pre-filter** reduces expensive Gemini API calls by ~80% for typical subreddit traffic.
- **Low analysis temperature (0.2)** keeps the High-Value classification consistent across repeated runs.
- **Human-in-the-loop** design: the bot never posts to Reddit autonomously – it only notifies the developer with a draft for review.
- **Idempotent seen-set** prevents duplicate notifications for the same post across cycles.
