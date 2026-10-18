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

Install/run Ollama locally and pull the model named by `OLLAMA_MODEL` in `.env`
(defaults to `llama3.1`). Then run:

```powershell
.\.venv\Scripts\python.exe webmaster.py
```

The crawler only accepts HTTPS URLs on the official `dbxv2.bn-ent.net` host and
uses Ollama at `127.0.0.1:11434`. Each successful run writes a sanitized HTML
block and a plain-text receipt under `staged_updates/`. It never edits
`index.html`; review and merge staged content manually.
