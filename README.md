# SuperChat - Phase 1

A responsive single chat page for Flights, Shopping and Cinema, served by FastAPI.
Search, compare, manage a cart and make **mock** reservations against the five official
JSON files. Part 3 adds the frontend, browser session ownership, retry protection,
outage routing and Render configuration. Nothing has been pushed or deployed.

## Run locally

From this directory in PowerShell, using Python 3.12+:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# First setup only: do not overwrite an existing configured .env.
Copy-Item .env.example .env
```

Set `GEMINI_API_KEY` privately in `.env`. Retain the existing `.env` if already
configured. Never commit or share it. Start with this single command:

```powershell
.\.venv\Scripts\python.exe -m app.serve
```

Open **http://127.0.0.1:8000/**. API docs: http://127.0.0.1:8000/docs.
The launcher reads `HOST` (default `0.0.0.0`) and `PORT` (default `8000`) from the
environment or `.env`. Run **one worker** because sessions and seat inventory are in memory.
No frontend build or Node server is required.

For a predictable demonstration without any Gemini calls:

```powershell
$env:SUPERCHAT_ROUTING_MODE = "offline"
.\.venv\Scripts\python.exe -m app.serve
```

Remove that override with `Remove-Item Env:SUPERCHAT_ROUTING_MODE` before returning
to `.env` configuration. For Python development only, use
`.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`; reloading resets server state.

## Try the chat

Use the welcome prompts or type this conversation:

1. `Find flights from Baku to Istanbul on Friday, cheapest first.`
2. `Only direct.`
3. `Show wireless headphones under 100 AZN.`
4. `Add two of the first one.`
5. `What movies are playing tonight?`
6. `Back to flights.`
7. `Show my cart.`

The page displays structured cards, showtimes, comparison tables, cart totals and
mock confirmations. Select two comparison checkboxes; choose a quantity before
adding items or reserving. Sold-out actions are disabled. Mixed example:
`Find a flight from Baku to Istanbul on Friday and a backpack under 100 AZN.`

The competition reference is **2026-11-02**, not the host clock: tonight = November 2,
Friday = November 6, Saturday = November 7; next Friday = November 13.

## Gemini and graceful failures

| Setting | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | unset | Server-side credential only |
| `GEMINI_MODEL` | `gemini-flash-latest` | Configurable model alias |
| `SUPERCHAT_ROUTING_MODE` | `auto` | `auto`, `offline`, or `strict` |
| `GEMINI_TIMEOUT_MS` | `30000` | Routing call timeout |
| `GEMINI_RESPONSE_TIMEOUT_MS` | `4000` | Response plan timeout |
| `COOKIE_SECURE` | `false` | Set `true` on HTTPS hosting |

`auto` attempts Gemini structured routing. Provider errors (including 503/504),
timeouts or invalid structured output switch to a conservative local router and
open a 60-second circuit breaker. The next request after that interval can try Gemini
again. SDK retries are disabled to avoid compounded delays. Without a key, `auto`
uses local routing immediately. `offline` makes no model calls. `strict` returns
503 for provider/key failures and 502 for invalid model output, useful for diagnostics.

The local router supports common English searches, known catalogue terms, explicit
IDs, common relative dates, simple follow-ups and clearly separated mixed requests.
Cart/reservation mutations use a restricted grammar and explicit quantities.
Unknown qualifiers or selections cause clarification. It is a limited outage path,
not a replacement for Gemini's broader understanding. The page labels local replies.
Neither router invents prices, inventory or confirmation IDs.

Gemini also selects a constrained response phrasing plan. Python inserts every fact
from deterministic results. A response-plan failure uses grounded templates without
losing a successful operation; local routing skips this second call. Existing English,
Azerbaijani and Russian response templates remain; the UI and structured cards are
English. Broad multilingual routing and a translated interface are outside this part.

Investigation retained the configured alias rather than guessing another model.
Google documents [model versions](https://ai.google.dev/gemini-api/docs/models) and
the [Flash latest alias](https://developers.googleblog.com/en/continuing-to-bring-you-our-latest-models-with-an-improved-gemini-2-5-flash-and-flash-lite-release/).
The previous live smoke test returned 503/504; successful live classification is
**not** claimed. See the [routing log](docs/routing_test_log.md).

## Persistence, isolation and retries

An unguessable HttpOnly, SameSite=Lax cookie identifies the browser. The server binds
each session to that identity: knowing a session UUID alone cannot retrieve or continue
another browser's session. `/api/client` supplies an opaque storage namespace;
clearing the cookie gives the UI a different namespace. This is anonymous browser
isolation, not accounts or separation between people sharing a browser profile.

Session IDs, structured history and unconfirmed requests persist in localStorage;
the active conversation is stored per tab in sessionStorage. Refresh fetches server
history. After a backend restart, saved history remains readable and ended sessions
are archived rather than silently replayed. New conversations have separate carts
and domain state. Clearing browser history does not cancel mock reservations.

Each UI submission carries a UUID `request_id`. Identical retries from that browser
return the original committed result during the server process lifetime. Reusing an
ID with another payload is HTTP 409. Concurrent retries commit once. Interrupted
requests remain visible with a safe retry action; mutations are not automatically
replayed. A deliberately new reservation request is a new operation.

## API contract

| Endpoint | Result |
|---|---|
| `GET /` | Chat page |
| `GET /health` | `{"status":"ok"}` when official data loads; 503 otherwise |
| `GET /api/client` | Storage namespace, routing mode, reference date |
| `POST /api/chat` | Routing, operation results, grounded message and state |
| `GET /api/session/{session_id}` | Owned session snapshot and structured history |

Example body: `{"message":"Show laptops","session_id":null,"request_id":"<UUID>"}`.
Session and request IDs are optional for direct callers. Preserve cookies across calls;
initialize them with `GET /api/client` before submitting retryable requests. Only
requests with `request_id` receive deduplication. The frontend supplies it automatically.

`routing` includes category, domains, typed intents, language and source (`gemini`
or `local`). Categories: flights, shopping, cinema, mixed, follow_up, ambiguous,
out_of_scope. `results` entries include domain, operation, status, code, data and
missing fields. Render these directly; do not infer booking success from prose.
Totals are decimal strings in AZN. Confirmations have unique `MOCK-...` IDs,
`mock: true` and `paid: false`.

Invalid bodies return 422; absent/unowned sessions return 404. Expected domain errors
and clarifications return 200 with result status. Each mixed-domain outcome may
independently succeed or require clarification. Health checks data, not Gemini.
Provider error details, stack traces and credentials are never returned to the page.

## Architecture and domain functionality

- `records.py` validates actual official schemas. `repositories.py` provides five
  read-only repositories behind `Repository[T]`: `list_all`, `get_by_id`, `query`.
  Future sources can implement this interface. Official data is never rewritten.
- `routing.py` uses Google Gen AI structured output and Pydantic validation;
  `fallback.py` provides outage routing. `dates.py` fixes the competition clock.
- `domains/` contains deterministic services. Flights support origin/destination/date,
  price/stops/departure/airline filtering and sorting, details, comparisons and one-way
  reservations. Shopping supports text/category/brand/colour/price/stock queries,
  comparisons and cart operations with decimal totals. Cinema supports genre/rating/
  language/date, locations/showtimes/prices/availability and ticket reservations.
- `state.py` keeps separate parameters, ordered shortlists, selections, pending actions,
  carts and reservations, plus shared history and last active domain. Mixed requests
  clear the implicit active domain to avoid guessing the next target. Returning to a
  domain preserves context. New searches do not delete carts/reservations.
- `chat.py` coordinates transactions and a shared seat ledger that prevents overbooking
  across sessions in one process. Carts do not reserve global stock. `responses.py`
  renders grounded messages. `main.py` adds browser ownership and retry handling.
- `static/` is buildless HTML/CSS/JavaScript. DOM text APIs render user/model content;
  there are no external assets, scripts or browser-held Gemini credentials.

## Tests and deliverables

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/evaluate_routing.py
```

Optional browser QA, with Microsoft Edge installed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/browser_smoke.py
```

The browser script starts/stops its own offline server and saves desktop/mobile
screenshots. Pytest mocks Gemini. All original 160 tests, including the 74 from Part 1,
are retained: the root assertion now checks HTML and strict-mode fixtures preserve
the original provider-error behavior. Additional tests cover Part 3.

- [Executed verification](docs/verification.md)
- [Four-page printable technical report](docs/technical_report.html)
- [Routing accuracy log](docs/routing_test_log.md)
- [Five-minute demo script](docs/demo_script.md)
- [Desktop screenshot](docs/screenshots/desktop-welcome.png)
- [Mobile screenshot](docs/screenshots/mobile-welcome.png)

## Render preparation - not deployed

`render.yaml` configures a Python web service, health path `/health`, secure cookies,
and an API key supplied separately as a hosting secret.

- Build: `pip install -r requirements.txt`
- Production start: **`python -m app.serve`**
- Equivalent: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`

The launcher follows Render's [FastAPI](https://render.com/docs/deploy-fastapi) and
[port binding](https://render.com/docs/web-services#port-binding) requirements.
Before deployment, recheck the live model/key, use exactly one instance/worker and
confirm that process-local demo storage is sufficient. No service was provisioned.

## Known limitations

Server sessions, anonymous ownership, retry records and mock inventory are in memory,
unbounded, and lost on restart. Browser history remains only in that profile; storage
restrictions may prevent persistence. Multiple workers/instances would disagree on
inventory. The shared inventory lock also covers response planning for atomic rollback,
so slow model calls can serialize turns. This is a competition demo, not durable booking
infrastructure. There are no accounts, checkout, real payments/bookings, persistent
database, Phase 2 APIs, voice or image search. Gemini semantic accuracy remains
unverified while unavailable; local routing intentionally clarifies unsupported phrasing.
