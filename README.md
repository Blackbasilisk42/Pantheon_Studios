# Local Hub services

The social metrics backend and content webmaster are local development tools.
They are not a production API for the public GitHub Pages site.

## Local server and metrics

1. Create and activate the root virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Put valid credentials and IDs in the ignored `.env` file. `.env.example`
   lists the supported names. YouTube requires a Data API key and channel ID;
   Discord requires a bot token and guild ID (the guild must expose its
   preview/presence data); Meta requires a Graph API access token with permission
   to read the configured Page's follower count and the Page ID.
3. Start the server and visit `http://127.0.0.1:5000/`:

   ```powershell
   python hub_server.py
   ```

The server binds only to `127.0.0.1`. `/api/metrics` returns a fixed JSON shape
containing only numeric counts or `null`; provider failures are logged without
logging credentials and produce HTTP 502. Missing credentials leave that
provider disconnected. Keep `.env` private and rotate any credential that was
ever committed or shared.

The server also runs the Webmaster's dossier and news routines in a background
scheduler. It generates a dossier and runs a news crawl at startup, refreshes
news every three hours, and regenerates the dossier daily. The threaded Flask
server remains available while those jobs run.

`POST /api/execute` accepts a JSON `command` and routes recognized requests to
the dossier generator, news crawler, site health check, or latest-edit rollback.
For example:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/execute `
  -ContentType "application/json" `
  -Body '{"command":"Check for broken elements"}'
```

The endpoint dispatches only these known routines; it does not interpret
requests as Python or shell commands. `/api/health` runs the local-reference
check directly. Before Webmaster output files are changed, the previous file
version is copied to `backups/` and the action, UTC timestamp, target, and
snapshot path are appended to `edit_log.jsonl`. A rollback restores the target
of the latest logged write and itself creates an audited snapshot.

The browser JavaScript is built from the readable `js/command-center.js` source:

```powershell
npm install
npm run obfuscate
```

Obfuscation is only a readability barrier. Browser users can still inspect
requests and local routes; never put secrets in client-side code. The local
backend does not add metrics to the remotely hosted static site.

## Human-reviewed update staging

The dossier generator reads its layout reference from `dossier.html` and uses
native Python data injection; it does not require Ollama or a local web server.
Run:

```powershell
.\.venv\Scripts\python.exe ai_webmaster.py
```

The script stages Kaige's dossier to `staged_updates/kaige_dossier.html` and a
timestamped payload receipt to `staged_updates/kaige_receipt.txt`. It also runs
the news crawler immediately, writes `staged_updates/news_bulletin.html`,
appends to `staged_updates/crawler_receipt.txt`, and repeats news scraping every
three hours. If the source is unreachable, it stages an explicit
`SOURCE UNAVAILABLE` status and records the failure rather than inventing news.
It never edits `index.html`; review and merge staged content manually.
