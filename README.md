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
3. Optionally set `API_KEY`, `API_BASE_URL`, and `API_MODEL` in `.env` to
   enable conversational site questions. The defaults use Google AI Studio's
   OpenAI-compatible endpoint; Groq can be selected by setting its
   OpenAI-compatible base URL and model.
4. Start the server and visit `http://127.0.0.1:5000/`:

   ```powershell
   python server.py
   ```

The server binds only to `127.0.0.1`. `/api/metrics` returns a fixed JSON shape
containing only numeric counts or `null`; provider failures are logged without
logging credentials and produce HTTP 502. Missing credentials leave that
provider disconnected. Keep `.env` private and rotate any credential that was
ever committed or shared.

The persistent Flask service also runs the Webmaster's dossier and news
routines in a background scheduler. It generates a dossier and runs a news
crawl at startup, refreshes news every three hours, and regenerates the dossier
daily. The threaded server remains available while those jobs run.

`POST /api/execute` accepts a JSON `command` and routes recognized requests to
the dossier generator, news crawler, deterministic official-source formatter,
site health check, or latest-edit rollback.
For example:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/execute `
  -ContentType "application/json" `
  -Body '{"command":"Check for broken elements"}'
```

The endpoint dispatches exact maintenance commands locally and does not
interpret requests as Python or shell commands. An "official source" staging
command scrapes the allowlisted publisher, uses its first heading and text
as-is, and does not call an external text-generation service. Open-ended
questions use local TF-IDF retrieval over site pages, project Markdown, and
site logs before calling the configured OpenAI-compatible API. The model can
request navigation only to targets in the local site map; the console presents
that target as a link. `/api/health` runs the local-reference check directly.
Before Webmaster output files are changed, the previous file version is copied
to `backups/` under a timestamped filename. Actions, UTC timestamps, targets,
and snapshot paths are stored in `edit_log.json`; existing `edit_log.jsonl`
history is retained and imported when the JSON log is first written. A
rollback restores or removes the target of the latest logged write and itself
creates an audited snapshot.
The Command Center, show hub, dossier pages, and character builder include the
assistant widget for submitting requests. The local-only backend must be
running; access the interactive panel at `http://127.0.0.1:5000/command-center.html`.
On pages covered by the existing maintenance or sign-in overlays, the widget
remains behind the overlay until that page is unlocked.

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
native Python data injection; it does not require a text-generation service or
local server.
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
