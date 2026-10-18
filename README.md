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
three hours. It never edits `index.html`; review and merge staged content
manually.
