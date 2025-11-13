# Email Parser

Automated email parser that monitors Gmail for job application responses and updates a Google Sheets spreadsheet with classification results (Approved/Declined/Needs Review).

## Features

- 🔍 **Automatic Email Monitoring**: Continuously monitors Gmail for new messages
- 🏢 **Company Matching**: Matches emails to companies from your spreadsheet
- 🤖 **Smart Classification**: Classifies responses as Approved, Declined, or Needs Review
- 📊 **Google Sheets Integration**: Automatically updates your tracking spreadsheet
- 🔄 **Incremental Processing**: Uses pointer-based tracking to avoid reprocessing emails
- 🚀 **Production Ready**: Supports Redis for persistent state, health checks, and graceful shutdown
- 📝 **Multi-language Support**: Handles English, Russian, and Ukrainian emails

## Architecture

### High-Level Overview

```
┌─────────────┐
│ Gmail API   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│           Email Parser Pipeline                 │
│  ┌──────────────────────────────────────────┐  │
│  │ 1. Fetch Companies (Google Sheets)       │  │
│  │ 2. Collect New Messages (Gmail)          │  │
│  │ 3. Extract Content (HTML/Text parsing)   │  │
│  │ 4. Filter by Company (Text matching)     │  │
│  │ 5. Classify (Phrase matching)            │  │
│  │ 6. Update Sheets (Write results)         │  │
│  └──────────────────────────────────────────┘  │
└──────┬──────────────────────────────────────┬──┘
       │                                      │
       ▼                                      ▼
┌─────────────┐                    ┌──────────────┐
│   Redis     │                    │ Google Sheets│
│  (State)    │                    │     API      │
└─────────────┘                    └──────────────┘
```

### Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Application Layer                       │
├─────────────────────────────────────────────────────────────┤
│  CLI (cli.py)                                               │
│    ├── run (sync/async)                                     │
│    ├── service (scheduler)                                  │
│    └── test                                                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      Service Layer                           │
├─────────────────────────────────────────────────────────────┤
│  Service (service.py / service_async.py)                    │
│    ├── Scheduler (scheduler.py)                             │
│    └── Health Check (health.py)                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      Pipeline Layer                          │
├─────────────────────────────────────────────────────────────┤
│  Pipeline (run.py / run_async.py)                           │
│    ├── Fetch Companies                                      │
│    ├── Collect Messages                                     │
│    ├── Extract Content                                      │
│    ├── Filter by Company                                    │
│    ├── Classify                                             │
│    └── Update Sheets                                        │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ Gmail Client │   │ Sheets Client│   │   Storage    │
│ (sync/async) │   │ (sync/async) │   │ (Redis/Mem)  │
└──────────────┘   └──────────────┘   └──────────────┘
```

### Data Flow

```
1. Configuration (config.py)
   └─> Loads .env, initializes clients, sets up storage

2. Gmail API (gmail/client.py)
   └─> Fetches messages, extracts content, manages pointer

3. Filtering (utils/filters.py)
   └─> Matches emails to companies, classifies by phrases

4. Sheets API (sheets/client.py, sheets/writer.py)
   └─> Reads companies, writes classification results

5. Storage (storage/redis_kv.py, storage/local_state.py)
   └─> Persists Gmail pointer for incremental processing
```

### Pipeline Stages

1. **Fetch Companies**: Reads pending companies from Google Sheets
2. **Collect Messages**: Fetches new Gmail messages since last processed pointer
3. **Extract Content**: Parses email bodies and extracts relevant text
4. **Company Matching**: Filters emails that mention tracked companies
5. **Classification**: Classifies emails using phrase matching (approve/decline/review)
6. **Update Sheets**: Writes results back to Google Sheets

## Requirements

- Python 3.11+
- Google Cloud Project with Gmail and Sheets API enabled
- OAuth 2.0 credentials

## Installation

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up Google OAuth**:
   - Create OAuth 2.0 credentials (Desktop app) in Google Cloud Console
   - Download `client_secret.json` to `credentials/` directory
   - Run: `python scripts/bootstrap_oauth.py`
   - This creates `token_gmail.json` and `token_sheets.json`

3. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

   Required variables:
   - `GOOGLE_SHEET_ID`: Your spreadsheet ID
   - `GOOGLE_SHEETS_TOKEN`: Path to Sheets token (default: `./credentials/token_sheets.json`)
   - `GOOGLE_GMAIL_TOKEN`: Path to Gmail token (default: `./credentials/token_gmail.json`)

## Usage

**Run once**:
```bash
python -m src.cli run
```

**Run with scheduler** (continuous):
```bash
# Set SCHEDULER_ENABLED=true in .env
python -m src.cli service
```

**Async mode**:
```bash
python -m src.cli run --async
python -m src.cli service --async
```

**Docker**:
```bash
docker-compose up -d
```

## Configuration

Key environment variables (see `.env.example` for full list):

- `SCHEDULER_ENABLED`: Enable periodic execution (default: `false`)
- `SCHEDULER_INTERVAL`: Seconds between runs (default: `300`)
- `USE_REDIS`: Use Redis for persistent state (default: `false`)
- `HEALTH_CHECK_ENABLED`: Enable health check endpoint (default: `true`)
- `HEALTH_CHECK_PORT`: Health check port (default: `8080`)
- `GMAIL_QUERY`: Gmail search query (default: `-in:spam -in:trash`)

## Google Sheets Format

Your spreadsheet should have:
- **Column A**: Company name
- **Column B**: Review flag (auto-filled)
- **Column C**: Status (auto-filled: "Approved" or "Declined")

## Development

**Run tests**:
```bash
pytest
pytest tests/unit/          # Unit tests only
pytest --cov=src/app        # With coverage
```

**Project structure**:
- `src/app/pipeline/` - Main pipeline logic (sync & async)
- `src/app/gmail/` - Gmail API clients
- `src/app/sheets/` - Google Sheets clients
- `src/app/utils/` - Utilities (filters, patterns, validation)
- `tests/` - Unit and integration tests

## Troubleshooting

**Token expired**: Run `python scripts/bootstrap_oauth.py` to re-authorize

**No messages processed**: Check `GMAIL_QUERY` in `.env` or verify pointer isn't stuck

**Redis connection failed**: Falls back to in-memory storage if Redis unavailable
