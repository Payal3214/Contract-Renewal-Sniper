# 🎯 Contract Renewal Sniper

An AI-assisted agent that reads vendor/SaaS contracts (PDF, DOCX, TXT), extracts the
clauses that actually matter — **renewal date, auto-renewal language, cancellation
notice window, and price** — and turns them into a risk-sorted action list so nothing
silently auto-renews on you again.

## What it does

- **Upload** any number of vendor contracts (PDF/DOCX/TXT).
- **Extracts** automatically:
  - Contract start / end (renewal) date
  - Whether it auto-renews
  - Required cancellation notice period (e.g. "60 days' written notice")
  - The computed **cancel-by deadline** (end date − notice period — the date that
    actually matters, not the renewal date itself)
  - Price and billing period, including renewal price-increase clauses when present
- **Scores risk** — CRITICAL / HIGH / MEDIUM / LOW / PAST — based on how many days
  are left until the cancellation deadline.
- **Dashboard** — a sorted action list, filterable by risk level, with CSV export.
- **Persists** everything locally in SQLite (`contracts.db`) so it survives reruns.

Two extraction modes:
1. **Regex/heuristic engine** (default) — fast, free, fully local, no API key needed.
2. **Claude-powered extraction** (optional) — paste an Anthropic API key in the sidebar
   for more accurate parsing of messy, inconsistently-worded contracts. Automatically
   falls back to the regex engine if the call fails.

## Project structure

```
contract-renewal-sniper/
├── app.py              # Streamlit UI (dashboard, upload, detail, settings)
├── extractor.py         # Regex + optional Claude clause extraction
├── risk_engine.py        # Turns extracted fields into a risk level
├── models.py             # Contract dataclass
├── db.py                 # SQLite persistence
├── file_readers.py       # PDF / DOCX / TXT -> plain text
├── sample_data/           # Two demo contracts (one HIGH, one CRITICAL risk)
├── requirements.txt
└── .streamlit/secrets.toml.example
```

## Run locally

```bash
git clone <your-repo-url>
cd contract-renewal-sniper
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`). Click **Load sample
contracts** on the Upload page to see it working immediately, no files needed.

## Deploy to Streamlit Community Cloud (free)

1. Push this folder to a **public or private GitHub repo**.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Pick your repo, branch, and set the main file path to `app.py`.
4. (Optional) In **Advanced settings → Secrets**, paste:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
5. Click **Deploy**. You'll get a public `*.streamlit.app` URL.

> Note: Streamlit Community Cloud's filesystem is ephemeral — `contracts.db` resets on
> redeploy/restart. That's fine for a demo/MVP. For production, swap the few functions
> in `db.py` for a hosted database (Postgres/Supabase/Turso all work with minimal changes).

## Using Claude-powered extraction

The regex engine handles well-structured contracts (like the two samples) out of the
box. For real-world contracts with inconsistent wording, paste an Anthropic API key
into the sidebar and check **"Use Claude for extraction"** — it sends the contract
text to Claude with a strict JSON-only prompt (see `extractor.py::LLM_SYSTEM_PROMPT`)
and parses the structured result. Get a key at
[console.anthropic.com](https://console.anthropic.com).

## Known limitations (MVP)

- Regex extraction works best on contracts with explicit "X days' written notice" and
  "$X per year" phrasing — very unusual wording may need the Claude mode.
- Vendor name detection is a best-effort guess (looks for "between X and Y" clauses,
  falls back to the filename).
- No email/Slack alerting yet — the dashboard is the alert surface for now. A natural
  next step is a scheduled job (e.g. GitHub Actions cron) that re-checks deadlines
  daily and pushes to Slack/email when a contract crosses into CRITICAL.
- Single-user, local SQLite — no auth/multi-tenant support yet.

## Roadmap ideas

- [ ] Email/Slack alerts when a contract crosses into HIGH/CRITICAL
- [ ] Multi-user accounts + shared team dashboard
- [ ] OCR fallback for scanned PDF contracts
- [ ] Bulk re-extraction / re-scan button
- [ ] Contract renewal history & spend-over-time charts

## License

MIT — do whatever you want with it.
