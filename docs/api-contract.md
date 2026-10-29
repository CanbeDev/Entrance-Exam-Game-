# Frontend API contract

Source commit: e5a31990c440c4a1106bac093597656738e0a8ac. Prepared offline on 2026-10-29. OpenAPI 3.1.0; 14 schema paths / 14 schema operations. Canonical export: [openapi.json](openapi.json).

This is a contract of the committed backend, supplemented by the actual route, service, repository and model code.
No server was started, no lifespan ran, no Phase 4 context was installed, no application settings were loaded,
and no MongoDB client or network connection was created. Runtime response examples below are synthetic documentation
fixtures generated with the existing pure backend models/engine and the committed country dataset; they are not production records.
Example passwords/tokens/IDs are nonfunctional placeholders. Never use them as credentials.
The examples describe separately authorized future operation, not an instruction to enable gates or call production now.

Hosting clarification (user-approved architecture, 2026-10-29): React/Vite will
run on Vercel with same-origin `/api/*` reverse proxying to the existing Render
FastAPI service. The proxy strips `/api`; route paths in this contract remain
backend paths. Frontend `/api/auth/login` therefore targets backend `/auth/login`.
Use relative `/api/` URLs for all browser API calls. The Vercel hostname is not yet
assigned/approved. Local proxy configuration is implemented in `frontend/`;
deployed Vercel/browser verification remains pending.
Trust only the eventual approved Vercel HTTPS origin, with no `/api` suffix, when
Stage E activation is separately authorized. Cookie/Origin/CSRF forwarding and
the minimal acceptance procedure are in [Stage E activation](STAGE_E_AUTH_ACTIVATION.md).
Current authorized settings remain origins `[]` and both write gates disabled.

OpenAPI is deliberately exported without hand edits. It does not declare runtime cookie security, Origin/CSRF checks,
most error codes, or several response shapes. In particular, its stock 422 HTTPValidationError schema is overridden on
Phase 4 paths by the actual detail.code handler. Read this document together with the JSON export.

## 1. Exact offline OpenAPI generation command

Run the following complete PowerShell command from the repository root. It verifies the backend matches committed HEAD, uses the project interpreter with bytecode writes disabled, blocks clients/DNS/sockets/.env loading, and writes only docs/openapi.json.

```powershell
$exportOpenApi = @'
import importlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

root = Path.cwd()
result = subprocess.run(
    ["git", "diff", "--quiet", "HEAD", "--", "backend/app", "backend/requirements.txt"],
    cwd=root, capture_output=True, check=False)
if result.returncode != 0:
    raise SystemExit("STOP: backend differs from committed HEAD or cannot be verified")
sys.path.insert(0, str(root / "backend"))

def blocked(*args, **kwargs):
    raise RuntimeError("OFFLINE_EXPORT_FORBIDS_CONFIGURATION_CLIENT_AND_NETWORK")

with patch("pymongo.MongoClient", side_effect=blocked) as mongo, \
     patch("pymongo.synchronous.mongo_client.MongoClient", side_effect=blocked) as sync_mongo, \
     patch("socket.socket.connect", side_effect=blocked) as sockets, \
     patch("socket.create_connection", side_effect=blocked) as connections, \
     patch("socket.getaddrinfo", side_effect=blocked) as addresses, \
     patch("dns.resolver.resolve", side_effect=blocked) as dns, \
     patch("dotenv.load_dotenv", side_effect=blocked) as dotenv:
    main = importlib.import_module("app.main")
    app = main.create_app(settings_loader=blocked, client_factory=blocked)
    for candidate in (main.app, app):
        assert candidate.state.phase4 is None
        assert candidate.state.mongo_client is None
        assert candidate.state.game_reader is None
        assert candidate.state.phase4_readiness == "not_started"
    schema = app.openapi()
    assert "app.database" not in sys.modules
    assert "test_database" not in sys.modules
    for guard in (mongo, sync_mongo, sockets, connections, addresses, dns, dotenv):
        guard.assert_not_called()
    target = root / "docs" / "openapi.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"openapi": schema["openapi"], "paths": len(schema["paths"]),
                      "operations": sum(method in {"get","post","put","patch","delete","head","options","trace"}
                                        for item in schema["paths"].values() for method in item),
                      "phase4_context": None, "mongo_clients_created": 0, "network_calls": 0}))
    for route in app.routes:
        print(json.dumps({"type": type(route).__name__, "path": getattr(route, "path", None),
                          "methods": sorted(getattr(route, "methods", []) or []),
                          "include_in_schema": getattr(route, "include_in_schema", None)}))
'@
$exportOpenApi | & '.\backend\.venv\Scripts\python.exe' -B -
```

The export leaves app.state.phase4, mongo_client and game_reader as None and phase4_readiness as not_started. Do not enter lifespan, use TestClient, import app.database, or import backend/test_database.py for schema export.

## 2. Gate, header and authorization conventions

A = PHASE4_AUTH_WRITES_ENABLED; G = PHASE4_GAMEPLAY_WRITES_ENABLED. Both default to false.
The last user-reported deployment has both false; the current live values are UNVERIFIED by this offline task.
When ordinary lifespan installs a context with A=false, every Phase 4 POST returns 503 authentication_disabled before
Origin/body/session checks. With no context at all (as in the export-only app), those POSTs return 503 phase4_disabled.
With A=true and G=false, game mutations remain unavailable, although prerequisite authorization can fail first.
Authenticated GETs are also A-dependent: absent/malformed cookies yield 401 first; syntactically valid cookies encounter the
closed A gate before database authorization. Public game/events reads do not require authentication or either write gate.

O = exactly one Origin header matching the configured trusted origins. C = X-CSRF-Token from GET /auth/csrf,
required on authenticated POSTs only. I = Idempotency-Key, 1-128 ASCII letters/digits/underscore/hyphen.
J = Content-Type: application/json. Cookie = browser-managed secure session cookie; never set a Cookie header manually in frontend JavaScript.
All Phase 4 POSTs require J except logout with an empty body. The default body cap is 16,384 actual streamed bytes (16 KiB),
not merely Content-Length. It applies to Phase 4 POSTs, not every route. Limits are configurable; live overrides are UNVERIFIED.

Evidence: [backend/app/api/dependencies.py:16](../backend/app/api/dependencies.py#L16), [backend/app/api/dependencies.py:76](../backend/app/api/dependencies.py#L76), [backend/app/services/auth_service.py:64](../backend/app/services/auth_service.py#L64), [backend/app/security/config.py:6](../backend/app/security/config.py#L6).

### Complete route inventory

Success and code-derived error statuses are listed below, including middleware/service errors that OpenAPI omits.
They are not a record of live HTTP tests. Generic framework failures can produce 500; unknown paths produce 404 and unsupported
methods normally 405. Trailing-slash redirects can produce 307. The backend defines no custom detail.code for these framework responses.

| Method | Path | Auth | Origin | CSRF | Other required headers | Gate / closed-gate behavior | Success; errors |
|---|---|---|---|---|---|---|---|
| GET | / | anonymous | no | no | none | none | 200 |
| GET | /health | anonymous | no | no | none | none; needs owned runtime client | 200; 503 |
| GET | /countries | anonymous | no | no | none | none; local catalog | 200; handled validation failure 503 |
| GET | /games/{game_id} | anonymous | no | no | none | none; needs runtime game_reader | 200; 404, 503; 422 declared by OpenAPI |
| POST | /auth/register | anonymous | O | no | J | A | 201; 400, 403, 409, 413, 415, 422, 429, 503 |
| POST | /auth/login | anonymous | O | no | J | A | 200; 400, 401, 403, 413, 415, 422, 429, 503 |
| GET | /auth/me | session | no | no | Cookie | A; authenticated reads touch session | 200; 401, 503 |
| GET | /auth/csrf | session | no | no | Cookie | A; authenticated reads touch session | 200; 401, 503 |
| POST | /auth/logout | session | O | C | Cookie; J only if body nonempty | A | 204; 400, 401, 403, 413, 415, 503 |
| GET | /me/games | session (own list) | no | no | Cookie | A; authenticated reads touch session | 200; 401, 422, 503 |
| POST | /games | session (creates ownership) | O | C | Cookie, J, I | A + G | 201; 400, 401, 403, 409, 413, 415, 422, 429, 503 |
| POST | /games/{game_id}/actions | owner session | O | C | Cookie, J | A + G | 200; 400, 401, 403, 404, 409, 413, 415, 422, 429, 503 |
| POST | /games/{game_id}/npc-steps | owner session | O | C | Cookie, J | A + G | 200; 400, 401, 403, 404, 409, 413, 415, 422, 429, 503 |
| GET | /games/{game_id}/events | anonymous | no | no | none | none; needs installed context/store | 200; 404, 422, 503 |
| GET, HEAD | /openapi.json | anonymous | no | no | none | none; framework, excluded from schema paths | 200 |
| GET, HEAD | /docs | anonymous | no | no | none | none; framework, excluded from schema paths | 200 |
| GET, HEAD | /docs/oauth2-redirect | anonymous | no | no | none | none; Swagger helper, not application OAuth login | 200 |
| GET, HEAD | /redoc | anonymous | no | no | none | none; framework, excluded from schema paths | 200 |
| OPTIONS | middleware preflight (no dedicated route) | anonymous | trusted Origin + Access-Control-Request-Method | no | Access-Control-Request-Headers when applicable | installed context and trusted Origin; not a write gate | 200/400 CORS text; otherwise normal routing, commonly 405 |

The 14 OpenAPI paths contain GET/POST only. The four documentation paths also support HEAD. HEAD is not automatically
declared for the application API routes. OPTIONS is middleware behavior, not an additional OpenAPI endpoint.
Trusted CORS preflights can be answered even when A/G are closed; preflight success does not grant write access.
Unknown/missing/duplicate/untrusted Origins do not receive credentialed CORS permission.

Route evidence: [backend/app/main.py:37](../backend/app/main.py#L37), [backend/app/api/auth.py:6](../backend/app/api/auth.py#L6), [backend/app/api/games.py:12](../backend/app/api/games.py#L12), [backend/app/api/countries.py:16](../backend/app/api/countries.py#L16).

## 3. Per-route bodies and realistic examples

All successful examples assume the necessary runtime dependencies/gates are deliberately available.
They are offline fixtures, not evidence of an active deployment. The human skip and NPC examples form a compatible branch:
revision 0 human -> revision 1 NPC -> revision 2 after one NPC action. Other action examples are independent valid payload shapes;
their legal phases and ownership prerequisites must still hold.

### GET /

Path/query/OpenAPI-declared header parameters: none.

Request body: none; do not send JSON.

Successful response: 200 application/json; fixed object containing message:string.

```json
{
  "message": "Geopolitics Game API is running"
}
```

### GET /health

Path/query/OpenAPI-declared header parameters: none.

Request body: none; do not send JSON.

Successful response: 200 application/json; status:string and database:string. This pings only; it does not expose Phase 4 readiness, gates or transaction privileges.

```json
{
  "status": "healthy",
  "database": "connected"
}
```

503 legacy example:

```json
{
  "detail": "MongoDB Atlas connection failed"
}
```

### GET /countries

Path/query/OpenAPI-declared header parameters: none.

Request body: none; do not send JSON.

Successful response: 200 application/json; population_snapshot plus the complete countries array. The committed catalog currently contains 195 eligible countries. There is no pagination, search parameter or per-country GET endpoint.

<details>
<summary>GET /countries response</summary>

```json
{
  "population_snapshot": {
    "dataset_id": "worldometer-2026-2026-10-19",
    "source_url": "https://www.worldometers.info/world-population/population-by-country/",
    "population_year": 2026,
    "retrieved_on": "2026-10-19",
    "source_sha256": "97fc89a45fd4a8a1219ce56033acdb18b2edf4a110e2416ba4677288cc5237d4"
  },
  "countries": [
    {
      "id": "afghanistan",
      "name": "Afghanistan",
      "population": 45047069,
      "base_soldier_value": 4
    },
    {
      "id": "albania",
      "name": "Albania",
      "population": 2751025,
      "base_soldier_value": 1
    },
    {
      "id": "algeria",
      "name": "Algeria",
      "population": 48028334,
      "base_soldier_value": 4
    },
    {
      "id": "andorra",
      "name": "Andorra",
      "population": 83753,
      "base_soldier_value": 1
    },
    {
      "id": "angola",
      "name": "Angola",
      "population": 40215179,
      "base_soldier_value": 4
    },
    {
      "id": "antigua-and-barbuda",
      "name": "Antigua and Barbuda",
      "population": 94626,
      "base_soldier_value": 1
    },
    {
      "id": "argentina",
      "name": "Argentina",
      "population": 46003734,
      "base_soldier_value": 4
    },
    {
      "id": "armenia",
      "name": "Armenia",
      "population": 2930915,
      "base_soldier_value": 1
    },
    {
      "id": "australia",
      "name": "Australia",
      "population": 27227096,
      "base_soldier_value": 4
    },
    {
      "id": "austria",
      "name": "Austria",
      "population": 9107266,
      "base_soldier_value": 2
    },
    {
      "id": "azerbaijan",
      "name": "Azerbaijan",
      "population": 10454855,
      "base_soldier_value": 3
    },
    {
      "id": "bahamas",
      "name": "Bahamas",
      "population": 404628,
      "base_soldier_value": 1
    },
    {
      "id": "bahrain",
      "name": "Bahrain",
      "population": 1675572,
      "base_soldier_value": 1
    },
    {
      "id": "bangladesh",
      "name": "Bangladesh",
      "population": 177818044,
      "base_soldier_value": 9
    },
    {
      "id": "barbados",
      "name": "Barbados",
      "population": 282724,
      "base_soldier_value": 1
    },
    {
      "id": "belarus",
      "name": "Belarus",
      "population": 8937018,
      "base_soldier_value": 2
    },
    {
      "id": "belgium",
      "name": "Belgium",
      "population": 11774642,
      "base_soldier_value": 3
    },
    {
      "id": "belize",
      "name": "Belize",
      "population": 428644,
      "base_soldier_value": 1
    },
    {
      "id": "benin",
      "name": "Benin",
      "population": 15170419,
      "base_soldier_value": 3
    },
    {
      "id": "bhutan",
      "name": "Bhutan",
      "population": 802214,
      "base_soldier_value": 1
    },
    {
      "id": "bolivia",
      "name": "Bolivia",
      "population": 12749291,
      "base_soldier_value": 3
    },
    {
      "id": "bosnia-and-herzegovina",
      "name": "Bosnia and Herzegovina",
      "population": 3114242,
      "base_soldier_value": 1
    },
    {
      "id": "botswana",
      "name": "Botswana",
      "population": 2603388,
      "base_soldier_value": 1
    },
    {
      "id": "brazil",
      "name": "Brazil",
      "population": 213562666,
      "base_soldier_value": 9
    },
    {
      "id": "brunei-darussalam",
      "name": "Brunei",
      "population": 469775,
      "base_soldier_value": 1
    },
    {
      "id": "bulgaria",
      "name": "Bulgaria",
      "population": 6667659,
      "base_soldier_value": 2
    },
    {
      "id": "burkina-faso",
      "name": "Burkina Faso",
      "population": 24601700,
      "base_soldier_value": 3
    },
    {
      "id": "burundi",
      "name": "Burundi",
      "population": 14729157,
      "base_soldier_value": 3
    },
    {
      "id": "cabo-verde",
      "name": "Cabo Verde",
      "population": 529630,
      "base_soldier_value": 1
    },
    {
      "id": "cambodia",
      "name": "Cambodia",
      "population": 18051219,
      "base_soldier_value": 3
    },
    {
      "id": "cameroon",
      "name": "Cameroon",
      "population": 30640817,
      "base_soldier_value": 4
    },
    {
      "id": "canada",
      "name": "Canada",
      "population": 40467728,
      "base_soldier_value": 4
    },
    {
      "id": "central-african-republic",
      "name": "Central African Republic",
      "population": 5698984,
      "base_soldier_value": 2
    },
    {
      "id": "chad",
      "name": "Chad",
      "population": 21560380,
      "base_soldier_value": 3
    },
    {
      "id": "chile",
      "name": "Chile",
      "population": 19945850,
      "base_soldier_value": 3
    },
    {
      "id": "china",
      "name": "China",
      "population": 1412914089,
      "base_soldier_value": 9
    },
    {
      "id": "colombia",
      "name": "Colombia",
      "population": 53936226,
      "base_soldier_value": 5
    },
    {
      "id": "comoros",
      "name": "Comoros",
      "population": 899010,
      "base_soldier_value": 1
    },
    {
      "id": "congo",
      "name": "Congo",
      "population": 6637785,
      "base_soldier_value": 2
    },
    {
      "id": "costa-rica",
      "name": "Costa Rica",
      "population": 5174789,
      "base_soldier_value": 2
    },
    {
      "id": "cote-d-ivoire",
      "name": "Côte d'Ivoire",
      "population": 33494346,
      "base_soldier_value": 4
    },
    {
      "id": "croatia",
      "name": "Croatia",
      "population": 3822345,
      "base_soldier_value": 1
    },
    {
      "id": "cuba",
      "name": "Cuba",
      "population": 10892659,
      "base_soldier_value": 3
    },
    {
      "id": "cyprus",
      "name": "Cyprus",
      "population": 1382334,
      "base_soldier_value": 1
    },
    {
      "id": "czechia",
      "name": "Czech Republic (Czechia)",
      "population": 10527781,
      "base_soldier_value": 3
    },
    {
      "id": "democratic-republic-of-the-congo",
      "name": "DR Congo",
      "population": 116452162,
      "base_soldier_value": 7
    },
    {
      "id": "denmark",
      "name": "Denmark",
      "population": 6023520,
      "base_soldier_value": 2
    },
    {
      "id": "djibouti",
      "name": "Djibouti",
      "population": 1199459,
      "base_soldier_value": 1
    },
    {
      "id": "dominica",
      "name": "Dominica",
      "population": 65511,
      "base_soldier_value": 1
    },
    {
      "id": "dominican-republic",
      "name": "Dominican Republic",
      "population": 11609500,
      "base_soldier_value": 3
    },
    {
      "id": "ecuador",
      "name": "Ecuador",
      "population": 18444506,
      "base_soldier_value": 3
    },
    {
      "id": "egypt",
      "name": "Egypt",
      "population": 120101175,
      "base_soldier_value": 7
    },
    {
      "id": "el-salvador",
      "name": "El Salvador",
      "population": 6391253,
      "base_soldier_value": 2
    },
    {
      "id": "equatorial-guinea",
      "name": "Equatorial Guinea",
      "population": 1984468,
      "base_soldier_value": 1
    },
    {
      "id": "eritrea",
      "name": "Eritrea",
      "population": 3682669,
      "base_soldier_value": 1
    },
    {
      "id": "estonia",
      "name": "Estonia",
      "population": 1331062,
      "base_soldier_value": 1
    },
    {
      "id": "ethiopia",
      "name": "Ethiopia",
      "population": 138902185,
      "base_soldier_value": 8
    },
    {
      "id": "fiji",
      "name": "Fiji",
      "population": 937282,
      "base_soldier_value": 1
    },
    {
      "id": "finland",
      "name": "Finland",
      "population": 5621739,
      "base_soldier_value": 2
    },
    {
      "id": "france",
      "name": "France",
      "population": 66746401,
      "base_soldier_value": 5
    },
    {
      "id": "gabon",
      "name": "Gabon",
      "population": 2647399,
      "base_soldier_value": 1
    },
    {
      "id": "gambia",
      "name": "Gambia",
      "population": 2884079,
      "base_soldier_value": 1
    },
    {
      "id": "georgia",
      "name": "Georgia",
      "population": 3804642,
      "base_soldier_value": 1
    },
    {
      "id": "germany",
      "name": "Germany",
      "population": 83644258,
      "base_soldier_value": 6
    },
    {
      "id": "ghana",
      "name": "Ghana",
      "population": 35697557,
      "base_soldier_value": 4
    },
    {
      "id": "greece",
      "name": "Greece",
      "population": 9897115,
      "base_soldier_value": 2
    },
    {
      "id": "grenada",
      "name": "Grenada",
      "population": 117362,
      "base_soldier_value": 1
    },
    {
      "id": "guatemala",
      "name": "Guatemala",
      "population": 18967978,
      "base_soldier_value": 3
    },
    {
      "id": "guinea",
      "name": "Guinea",
      "population": 15441993,
      "base_soldier_value": 3
    },
    {
      "id": "guinea-bissau",
      "name": "Guinea-Bissau",
      "population": 2297808,
      "base_soldier_value": 1
    },
    {
      "id": "guyana",
      "name": "Guyana",
      "population": 840890,
      "base_soldier_value": 1
    },
    {
      "id": "haiti",
      "name": "Haiti",
      "population": 12037506,
      "base_soldier_value": 3
    },
    {
      "id": "holy-see",
      "name": "Holy See",
      "population": 506,
      "base_soldier_value": 1
    },
    {
      "id": "honduras",
      "name": "Honduras",
      "population": 11184760,
      "base_soldier_value": 3
    },
    {
      "id": "hungary",
      "name": "Hungary",
      "population": 9585818,
      "base_soldier_value": 2
    },
    {
      "id": "iceland",
      "name": "Iceland",
      "population": 402329,
      "base_soldier_value": 1
    },
    {
      "id": "india",
      "name": "India",
      "population": 1476625576,
      "base_soldier_value": 9
    },
    {
      "id": "indonesia",
      "name": "Indonesia",
      "population": 287886782,
      "base_soldier_value": 9
    },
    {
      "id": "iran",
      "name": "Iran",
      "population": 93168497,
      "base_soldier_value": 6
    },
    {
      "id": "iraq",
      "name": "Iraq",
      "population": 48007437,
      "base_soldier_value": 4
    },
    {
      "id": "ireland",
      "name": "Ireland",
      "population": 5356950,
      "base_soldier_value": 2
    },
    {
      "id": "israel",
      "name": "Israel",
      "population": 9647689,
      "base_soldier_value": 2
    },
    {
      "id": "italy",
      "name": "Italy",
      "population": 58926166,
      "base_soldier_value": 5
    },
    {
      "id": "jamaica",
      "name": "Jamaica",
      "population": 2833403,
      "base_soldier_value": 1
    },
    {
      "id": "japan",
      "name": "Japan",
      "population": 122427731,
      "base_soldier_value": 7
    },
    {
      "id": "jordan",
      "name": "Jordan",
      "population": 11589532,
      "base_soldier_value": 3
    },
    {
      "id": "kazakhstan",
      "name": "Kazakhstan",
      "population": 21083626,
      "base_soldier_value": 3
    },
    {
      "id": "kenya",
      "name": "Kenya",
      "population": 58636412,
      "base_soldier_value": 5
    },
    {
      "id": "kiribati",
      "name": "Kiribati",
      "population": 138445,
      "base_soldier_value": 1
    },
    {
      "id": "kuwait",
      "name": "Kuwait",
      "population": 5102773,
      "base_soldier_value": 2
    },
    {
      "id": "kyrgyzstan",
      "name": "Kyrgyzstan",
      "population": 7400465,
      "base_soldier_value": 2
    },
    {
      "id": "laos",
      "name": "Laos",
      "population": 7974017,
      "base_soldier_value": 2
    },
    {
      "id": "latvia",
      "name": "Latvia",
      "population": 1835935,
      "base_soldier_value": 1
    },
    {
      "id": "lebanon",
      "name": "Lebanon",
      "population": 5897467,
      "base_soldier_value": 2
    },
    {
      "id": "lesotho",
      "name": "Lesotho",
      "population": 2389336,
      "base_soldier_value": 1
    },
    {
      "id": "liberia",
      "name": "Liberia",
      "population": 5853949,
      "base_soldier_value": 2
    },
    {
      "id": "libya",
      "name": "Libya",
      "population": 7539851,
      "base_soldier_value": 2
    },
    {
      "id": "liechtenstein",
      "name": "Liechtenstein",
      "population": 40368,
      "base_soldier_value": 1
    },
    {
      "id": "lithuania",
      "name": "Lithuania",
      "population": 2797338,
      "base_soldier_value": 1
    },
    {
      "id": "luxembourg",
      "name": "Luxembourg",
      "population": 687448,
      "base_soldier_value": 1
    },
    {
      "id": "madagascar",
      "name": "Madagascar",
      "population": 33522052,
      "base_soldier_value": 4
    },
    {
      "id": "malawi",
      "name": "Malawi",
      "population": 22785535,
      "base_soldier_value": 3
    },
    {
      "id": "malaysia",
      "name": "Malaysia",
      "population": 36385115,
      "base_soldier_value": 4
    },
    {
      "id": "maldives",
      "name": "Maldives",
      "population": 531517,
      "base_soldier_value": 1
    },
    {
      "id": "mali",
      "name": "Mali",
      "population": 25932275,
      "base_soldier_value": 4
    },
    {
      "id": "malta",
      "name": "Malta",
      "population": 549011,
      "base_soldier_value": 1
    },
    {
      "id": "marshall-islands",
      "name": "Marshall Islands",
      "population": 35075,
      "base_soldier_value": 1
    },
    {
      "id": "mauritania",
      "name": "Mauritania",
      "population": 5461319,
      "base_soldier_value": 2
    },
    {
      "id": "mauritius",
      "name": "Mauritius",
      "population": 1265059,
      "base_soldier_value": 1
    },
    {
      "id": "mexico",
      "name": "Mexico",
      "population": 132997658,
      "base_soldier_value": 8
    },
    {
      "id": "micronesia",
      "name": "Micronesia",
      "population": 114183,
      "base_soldier_value": 1
    },
    {
      "id": "moldova",
      "name": "Moldova",
      "population": 2961253,
      "base_soldier_value": 1
    },
    {
      "id": "monaco",
      "name": "Monaco",
      "population": 38087,
      "base_soldier_value": 1
    },
    {
      "id": "mongolia",
      "name": "Mongolia",
      "population": 3556798,
      "base_soldier_value": 1
    },
    {
      "id": "montenegro",
      "name": "Montenegro",
      "population": 626233,
      "base_soldier_value": 1
    },
    {
      "id": "morocco",
      "name": "Morocco",
      "population": 38762441,
      "base_soldier_value": 4
    },
    {
      "id": "mozambique",
      "name": "Mozambique",
      "population": 36639851,
      "base_soldier_value": 4
    },
    {
      "id": "myanmar",
      "name": "Myanmar",
      "population": 55184819,
      "base_soldier_value": 5
    },
    {
      "id": "namibia",
      "name": "Namibia",
      "population": 3153246,
      "base_soldier_value": 1
    },
    {
      "id": "nauru",
      "name": "Nauru",
      "population": 12101,
      "base_soldier_value": 1
    },
    {
      "id": "nepal",
      "name": "Nepal",
      "population": 29629410,
      "base_soldier_value": 4
    },
    {
      "id": "netherlands",
      "name": "Netherlands",
      "population": 18448775,
      "base_soldier_value": 3
    },
    {
      "id": "new-zealand",
      "name": "New Zealand",
      "population": 5287479,
      "base_soldier_value": 2
    },
    {
      "id": "nicaragua",
      "name": "Nicaragua",
      "population": 7097329,
      "base_soldier_value": 2
    },
    {
      "id": "niger",
      "name": "Niger",
      "population": 28814878,
      "base_soldier_value": 4
    },
    {
      "id": "nigeria",
      "name": "Nigeria",
      "population": 242431832,
      "base_soldier_value": 9
    },
    {
      "id": "north-korea",
      "name": "North Korea",
      "population": 26633691,
      "base_soldier_value": 4
    },
    {
      "id": "north-macedonia",
      "name": "North Macedonia",
      "population": 1804063,
      "base_soldier_value": 1
    },
    {
      "id": "norway",
      "name": "Norway",
      "population": 5652989,
      "base_soldier_value": 2
    },
    {
      "id": "oman",
      "name": "Oman",
      "population": 5671458,
      "base_soldier_value": 2
    },
    {
      "id": "pakistan",
      "name": "Pakistan",
      "population": 259299791,
      "base_soldier_value": 9
    },
    {
      "id": "palau",
      "name": "Palau",
      "population": 17614,
      "base_soldier_value": 1
    },
    {
      "id": "panama",
      "name": "Panama",
      "population": 4625718,
      "base_soldier_value": 1
    },
    {
      "id": "papua-new-guinea",
      "name": "Papua New Guinea",
      "population": 10947848,
      "base_soldier_value": 3
    },
    {
      "id": "paraguay",
      "name": "Paraguay",
      "population": 7095279,
      "base_soldier_value": 2
    },
    {
      "id": "peru",
      "name": "Peru",
      "population": 34922148,
      "base_soldier_value": 4
    },
    {
      "id": "philippines",
      "name": "Philippines",
      "population": 117724471,
      "base_soldier_value": 7
    },
    {
      "id": "poland",
      "name": "Poland",
      "population": 37843188,
      "base_soldier_value": 4
    },
    {
      "id": "portugal",
      "name": "Portugal",
      "population": 10395362,
      "base_soldier_value": 3
    },
    {
      "id": "qatar",
      "name": "Qatar",
      "population": 3173559,
      "base_soldier_value": 1
    },
    {
      "id": "romania",
      "name": "Romania",
      "population": 18800605,
      "base_soldier_value": 3
    },
    {
      "id": "russia",
      "name": "Russia",
      "population": 143394458,
      "base_soldier_value": 8
    },
    {
      "id": "rwanda",
      "name": "Rwanda",
      "population": 14889693,
      "base_soldier_value": 3
    },
    {
      "id": "saint-kitts-and-nevis",
      "name": "Saint Kitts & Nevis",
      "population": 46992,
      "base_soldier_value": 1
    },
    {
      "id": "saint-lucia",
      "name": "Saint Lucia",
      "population": 180488,
      "base_soldier_value": 1
    },
    {
      "id": "saint-vincent-and-the-grenadines",
      "name": "St. Vincent & Grenadines",
      "population": 99245,
      "base_soldier_value": 1
    },
    {
      "id": "samoa",
      "name": "Samoa",
      "population": 220528,
      "base_soldier_value": 1
    },
    {
      "id": "san-marino",
      "name": "San Marino",
      "population": 33605,
      "base_soldier_value": 1
    },
    {
      "id": "sao-tome-and-principe",
      "name": "Sao Tome & Principe",
      "population": 244994,
      "base_soldier_value": 1
    },
    {
      "id": "saudi-arabia",
      "name": "Saudi Arabia",
      "population": 35165787,
      "base_soldier_value": 4
    },
    {
      "id": "senegal",
      "name": "Senegal",
      "population": 19366548,
      "base_soldier_value": 3
    },
    {
      "id": "serbia",
      "name": "Serbia",
      "population": 6641964,
      "base_soldier_value": 2
    },
    {
      "id": "seychelles",
      "name": "Seychelles",
      "population": 134959,
      "base_soldier_value": 1
    },
    {
      "id": "sierra-leone",
      "name": "Sierra Leone",
      "population": 8996745,
      "base_soldier_value": 2
    },
    {
      "id": "singapore",
      "name": "Singapore",
      "population": 5905748,
      "base_soldier_value": 2
    },
    {
      "id": "slovakia",
      "name": "Slovakia",
      "population": 5451342,
      "base_soldier_value": 2
    },
    {
      "id": "slovenia",
      "name": "Slovenia",
      "population": 2114573,
      "base_soldier_value": 1
    },
    {
      "id": "solomon-islands",
      "name": "Solomon Islands",
      "population": 858288,
      "base_soldier_value": 1
    },
    {
      "id": "somalia",
      "name": "Somalia",
      "population": 20305907,
      "base_soldier_value": 3
    },
    {
      "id": "south-africa",
      "name": "South Africa",
      "population": 65453084,
      "base_soldier_value": 5
    },
    {
      "id": "south-korea",
      "name": "South Korea",
      "population": 51600388,
      "base_soldier_value": 5
    },
    {
      "id": "south-sudan",
      "name": "South Sudan",
      "population": 12436037,
      "base_soldier_value": 3
    },
    {
      "id": "spain",
      "name": "Spain",
      "population": 47850793,
      "base_soldier_value": 4
    },
    {
      "id": "sri-lanka",
      "name": "Sri Lanka",
      "population": 23348315,
      "base_soldier_value": 3
    },
    {
      "id": "state-of-palestine",
      "name": "State of Palestine",
      "population": 5692790,
      "base_soldier_value": 2
    },
    {
      "id": "sudan",
      "name": "Sudan",
      "population": 53282719,
      "base_soldier_value": 5
    },
    {
      "id": "suriname",
      "name": "Suriname",
      "population": 645256,
      "base_soldier_value": 1
    },
    {
      "id": "swaziland",
      "name": "Eswatini",
      "population": 1269859,
      "base_soldier_value": 1
    },
    {
      "id": "sweden",
      "name": "Sweden",
      "population": 10701047,
      "base_soldier_value": 3
    },
    {
      "id": "switzerland",
      "name": "Switzerland",
      "population": 9007798,
      "base_soldier_value": 2
    },
    {
      "id": "syria",
      "name": "Syria",
      "population": 26472497,
      "base_soldier_value": 4
    },
    {
      "id": "tajikistan",
      "name": "Tajikistan",
      "population": 10978599,
      "base_soldier_value": 3
    },
    {
      "id": "tanzania",
      "name": "Tanzania",
      "population": 72563780,
      "base_soldier_value": 5
    },
    {
      "id": "thailand",
      "name": "Thailand",
      "population": 71559614,
      "base_soldier_value": 5
    },
    {
      "id": "timor-leste",
      "name": "Timor-Leste",
      "population": 1436923,
      "base_soldier_value": 1
    },
    {
      "id": "togo",
      "name": "Togo",
      "population": 9930918,
      "base_soldier_value": 2
    },
    {
      "id": "tonga",
      "name": "Tonga",
      "population": 103291,
      "base_soldier_value": 1
    },
    {
      "id": "trinidad-and-tobago",
      "name": "Trinidad and Tobago",
      "population": 1513268,
      "base_soldier_value": 1
    },
    {
      "id": "tunisia",
      "name": "Tunisia",
      "population": 12415138,
      "base_soldier_value": 3
    },
    {
      "id": "turkey",
      "name": "Turkey",
      "population": 87926082,
      "base_soldier_value": 6
    },
    {
      "id": "turkmenistan",
      "name": "Turkmenistan",
      "population": 7736632,
      "base_soldier_value": 2
    },
    {
      "id": "tuvalu",
      "name": "Tuvalu",
      "population": 9362,
      "base_soldier_value": 1
    },
    {
      "id": "uganda",
      "name": "Uganda",
      "population": 52761469,
      "base_soldier_value": 5
    },
    {
      "id": "uk",
      "name": "United Kingdom",
      "population": 69931528,
      "base_soldier_value": 5
    },
    {
      "id": "ukraine",
      "name": "Ukraine",
      "population": 39535849,
      "base_soldier_value": 4
    },
    {
      "id": "united-arab-emirates",
      "name": "United Arab Emirates",
      "population": 11574682,
      "base_soldier_value": 3
    },
    {
      "id": "uruguay",
      "name": "Uruguay",
      "population": 3382537,
      "base_soldier_value": 1
    },
    {
      "id": "us",
      "name": "United States",
      "population": 349035494,
      "base_soldier_value": 9
    },
    {
      "id": "uzbekistan",
      "name": "Uzbekistan",
      "population": 37724223,
      "base_soldier_value": 4
    },
    {
      "id": "vanuatu",
      "name": "Vanuatu",
      "population": 342564,
      "base_soldier_value": 1
    },
    {
      "id": "venezuela",
      "name": "Venezuela",
      "population": 28633711,
      "base_soldier_value": 4
    },
    {
      "id": "vietnam",
      "name": "Vietnam",
      "population": 102177431,
      "base_soldier_value": 7
    },
    {
      "id": "yemen",
      "name": "Yemen",
      "population": 42961653,
      "base_soldier_value": 4
    },
    {
      "id": "zambia",
      "name": "Zambia",
      "population": 22521915,
      "base_soldier_value": 3
    },
    {
      "id": "zimbabwe",
      "name": "Zimbabwe",
      "population": 17273580,
      "base_soldier_value": 3
    }
  ]
}
```

</details>

Catalog item fields: id:string (nonempty lowercase slug, letters/digits/hyphens), name:string (nonempty),
population:positive strict integer, base_soldier_value:integer 1-9. There is no owner_id or current soldiers field in catalog items.
population_snapshot contains dataset_id:string, source_url:HTTPS string, population_year:integer >=1900,
retrieved_on:YYYY-MM-DD string, source_sha256:64 lowercase hexadecimal characters.
Catalog provenance is the committed snapshot; this task did not fetch Worldometer or verify current online populations.

Evidence: [backend/app/api/countries.py:17](../backend/app/api/countries.py#L17), [backend/app/models/country.py:6](../backend/app/models/country.py#L6), [backend/app/models/country.py:14](../backend/app/models/country.py#L14).

### POST /auth/register

Path/query/OpenAPI-declared header parameters: none.

Request body: JSON as shown below.

```json
{
  "username": "student_demo",
  "password": "<YOUR_PRIVATE_PASSPHRASE>"
}
```

Successful response: 201 UserPublic: id:string, username:string. Registration does not log in or set the session cookie.

```json
{
  "id": "650000000000000000000002",
  "username": "student_demo"
}
```

Username: 3-32 ASCII letters/digits/underscore, no whitespace trimming; uniqueness and login are case-insensitive.
Credentials OpenAPI uses password length 1-128 because login shares that model. Registration additionally applies NFC normalization,
15-128 characters, no NUL, no repeated-single-character password, no username-equivalent password, and a local common-password blocklist.
Passwords are not trimmed. These examples contain only a placeholder, not a usable supplied credential.
Unknown credential fields are forbidden.

Evidence: [backend/app/models/auth.py:9](../backend/app/models/auth.py#L9), [backend/app/security/passwords.py:22](../backend/app/security/passwords.py#L22), [backend/app/services/auth_service.py:30](../backend/app/services/auth_service.py#L30).

### POST /auth/login

Path/query/OpenAPI-declared header parameters: none.

Request body: JSON as shown below.

```json
{
  "username": "student_demo",
  "password": "<YOUR_PRIVATE_PASSPHRASE>"
}
```

Successful response: 200 application/json; user:UserPublic and expires_at:date-time. Also sets the secure HttpOnly cookie. No raw token or CSRF token appears in this JSON.

```json
{
  "user": {
    "id": "650000000000000000000002",
    "username": "student_demo"
  },
  "expires_at": "2026-10-30T00:00:00Z"
}
```

Login accepts the shared Credentials password length 1-128 and NFC-normalizes without trimming.
Do not reject an existing login solely because its password is shorter than the new-registration policy.
Unknown usernames, bad passwords and disabled accounts use generic 401 invalid_credentials.

### GET /auth/me

Path/query/OpenAPI-declared header parameters: none.

Request body: none; do not send JSON.

Successful response: 200 UserPublic, derived from the current session.

```json
{
  "id": "650000000000000000000002",
  "username": "student_demo"
}
```

### GET /auth/csrf

Path/query/OpenAPI-declared header parameters: none.

Request body: none; do not send JSON.

Successful response: 200 application/json; csrf_token:string. The shown x characters are a synthetic placeholder, not a real token.

```json
{
  "csrf_token": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

### POST /auth/logout

Path/query/OpenAPI-declared header parameters: none.

Request body: none; do not send JSON.

Successful response: 204 with no body; revokes and clears the current cookie.

No response body.

Send an empty body. The route declares no request model. If a nonempty body is sent, the middleware requires application/json
but does not use a logout payload; do not rely on arbitrary body validation. Origin, session and CSRF are still mandatory.

### GET /me/games

| Parameter | Location | Required | Type | Limits/default |
|---|---|---|---|---|
| `status` | query | false | string / null | enum=["waiting", "active", "completed"]; - |
| `query` | query | false | string | maxLength=100; default="" |
| `cursor` | query | false | string / null | pattern="^[0-9a-fA-F]{24}$"; - |
| `limit` | query | false | integer | minimum=1; maximum=100; default=20 |

Request body: none; do not send JSON.

Successful response: 200 PublicGameList with games:PublicGameSummary[] and next_cursor:string|null. Summaries are not full boards.

```json
{
  "games": [
    {
      "_id": "650000000000000000000001",
      "game_name": "Frontend contract demo",
      "status": "active",
      "round": 1,
      "current_turn": 0,
      "phase": "deciding",
      "revision": 0,
      "winner": null,
      "created_at": "2026-10-29T12:00:00Z",
      "updated_at": "2026-10-29T12:00:00Z"
    }
  ],
  "next_cursor": null
}
```

Search query is a literal, case-insensitive game-name substring (escaped before MongoDB regex use), not a client-supplied regex.
Results are owner-scoped, sorted by descending ObjectId. Pass next_cursor as cursor for the next page; null means no more rows.
There is no global anonymous game-list endpoint.

Evidence: [backend/app/repositories/security_repository.py:250](../backend/app/repositories/security_repository.py#L250).

### POST /games

| Parameter | Location | Required | Type | Limits/default |
|---|---|---|---|---|
| `Idempotency-Key` | header | true | string | minLength=1; maxLength=128; pattern="^[a-zA-Z0-9_-]+$" |

Request body: JSON as shown below.

```json
{
  "game_name": "Frontend contract demo",
  "starting_country_id": "india"
}
```

Successful response: 201 PublicGame including _id. Requires Idempotency-Key, Origin, X-CSRF-Token, Content-Type and the session cookie. Always keep the same Idempotency-Key and identical body for an uncertain retry.

<details>
<summary>POST /games response</summary>

```json
{
  "_id": "650000000000000000000001",
  "game_name": "Frontend contract demo",
  "status": "active",
  "round": 1,
  "current_turn": 0,
  "countries": [
    {
      "id": "india",
      "name": "India",
      "population": 1476625576,
      "owner_id": "human",
      "base_soldier_value": 9,
      "soldiers": 9
    },
    {
      "id": "burundi",
      "name": "Burundi",
      "population": 14729157,
      "owner_id": "npc-1",
      "base_soldier_value": 3,
      "soldiers": 3
    },
    {
      "id": "somalia",
      "name": "Somalia",
      "population": 20305907,
      "owner_id": "npc-2",
      "base_soldier_value": 3,
      "soldiers": 3
    },
    {
      "id": "turkmenistan",
      "name": "Turkmenistan",
      "population": 7736632,
      "owner_id": "npc-3",
      "base_soldier_value": 2,
      "soldiers": 2
    },
    {
      "id": "zimbabwe",
      "name": "Zimbabwe",
      "population": 17273580,
      "owner_id": "npc-4",
      "base_soldier_value": 3,
      "soldiers": 3
    },
    {
      "id": "swaziland",
      "name": "Eswatini",
      "population": 1269859,
      "owner_id": "npc-5",
      "base_soldier_value": 1,
      "soldiers": 1
    },
    {
      "id": "peru",
      "name": "Peru",
      "population": 34922148,
      "owner_id": "npc-6",
      "base_soldier_value": 4,
      "soldiers": 4
    },
    {
      "id": "germany",
      "name": "Germany",
      "population": 83644258,
      "owner_id": "npc-7",
      "base_soldier_value": 6,
      "soldiers": 6
    },
    {
      "id": "guinea-bissau",
      "name": "Guinea-Bissau",
      "population": 2297808,
      "owner_id": "npc-8",
      "base_soldier_value": 1,
      "soldiers": 1
    },
    {
      "id": "vanuatu",
      "name": "Vanuatu",
      "population": 342564,
      "owner_id": "npc-9",
      "base_soldier_value": 1,
      "soldiers": 1
    }
  ],
  "players": [
    {
      "id": "human",
      "kind": "human",
      "starting_country_id": "india"
    },
    {
      "id": "npc-1",
      "kind": "npc",
      "starting_country_id": "burundi"
    },
    {
      "id": "npc-2",
      "kind": "npc",
      "starting_country_id": "somalia"
    },
    {
      "id": "npc-3",
      "kind": "npc",
      "starting_country_id": "turkmenistan"
    },
    {
      "id": "npc-4",
      "kind": "npc",
      "starting_country_id": "zimbabwe"
    },
    {
      "id": "npc-5",
      "kind": "npc",
      "starting_country_id": "swaziland"
    },
    {
      "id": "npc-6",
      "kind": "npc",
      "starting_country_id": "peru"
    },
    {
      "id": "npc-7",
      "kind": "npc",
      "starting_country_id": "germany"
    },
    {
      "id": "npc-8",
      "kind": "npc",
      "starting_country_id": "guinea-bissau"
    },
    {
      "id": "npc-9",
      "kind": "npc",
      "starting_country_id": "vanuatu"
    }
  ],
  "winner": null,
  "created_at": "2026-10-29T12:00:00Z",
  "schema_version": 3,
  "turn_order": [
    "human",
    "npc-7",
    "npc-8",
    "npc-6",
    "npc-2",
    "npc-3",
    "npc-5",
    "npc-1",
    "npc-9",
    "npc-4"
  ],
  "population_snapshot": {
    "dataset_id": "worldometer-2026-2026-10-19",
    "source_url": "https://www.worldometers.info/world-population/population-by-country/",
    "population_year": 2026,
    "retrieved_on": "2026-10-19",
    "source_sha256": "97fc89a45fd4a8a1219ce56033acdb18b2edf4a110e2416ba4677288cc5237d4"
  },
  "updated_at": "2026-10-29T12:00:00Z",
  "revision": 0,
  "turn_sequence": 0,
  "phase": "deciding",
  "pending_reinforcements": 0,
  "attack_used": false,
  "battle": null
}
```

</details>

GameSetupRequest strips leading/trailing whitespace from its string fields; game_name is 1-100 characters after processing,
starting_country_id is nonempty and must be an actual eligible catalog ID. Extra fields are forbidden.
The server chooses the other nine countries, game-local participants, ownership, populations and soldiers.
Matching owner/key/payload retries return the existing game without resetting it; changed payload with the same key returns 409 creation_id_conflict.
Returned state can already have progressed when a creation is replayed.
Source-level edge: an unknown/ineligible starting_country_id raises a catalog ValueError that is sanitized by Phase 4 middleware as
503 service_unavailable, not a dedicated 422 country code. Use catalog-provided IDs. The live response has not been exercised here.

Evidence: [backend/app/models/game.py:15](../backend/app/models/game.py#L15), [backend/app/services/authorized_game_service.py:53](../backend/app/services/authorized_game_service.py#L53), [backend/app/repositories/security_repository.py:206](../backend/app/repositories/security_repository.py#L206), [backend/app/services/country_catalog.py:49](../backend/app/services/country_catalog.py#L49).

### GET /games/{game_id}

| Parameter | Location | Required | Type | Limits/default |
|---|---|---|---|---|
| `game_id` | path | true | string | - |

Request body: none; do not send JSON.

Successful response: 200 PublicGame, a full public board, not only events. game_id should be a 24-hex ObjectId string; malformed/missing IDs resolve to legacy 404.

<details>
<summary>GET /games/{game_id} response</summary>

```json
{
  "_id": "650000000000000000000001",
  "game_name": "Frontend contract demo",
  "status": "active",
  "round": 1,
  "current_turn": 0,
  "countries": [
    {
      "id": "india",
      "name": "India",
      "population": 1476625576,
      "owner_id": "human",
      "base_soldier_value": 9,
      "soldiers": 9
    },
    {
      "id": "burundi",
      "name": "Burundi",
      "population": 14729157,
      "owner_id": "npc-1",
      "base_soldier_value": 3,
      "soldiers": 3
    },
    {
      "id": "somalia",
      "name": "Somalia",
      "population": 20305907,
      "owner_id": "npc-2",
      "base_soldier_value": 3,
      "soldiers": 3
    },
    {
      "id": "turkmenistan",
      "name": "Turkmenistan",
      "population": 7736632,
      "owner_id": "npc-3",
      "base_soldier_value": 2,
      "soldiers": 2
    },
    {
      "id": "zimbabwe",
      "name": "Zimbabwe",
      "population": 17273580,
      "owner_id": "npc-4",
      "base_soldier_value": 3,
      "soldiers": 3
    },
    {
      "id": "swaziland",
      "name": "Eswatini",
      "population": 1269859,
      "owner_id": "npc-5",
      "base_soldier_value": 1,
      "soldiers": 1
    },
    {
      "id": "peru",
      "name": "Peru",
      "population": 34922148,
      "owner_id": "npc-6",
      "base_soldier_value": 4,
      "soldiers": 4
    },
    {
      "id": "germany",
      "name": "Germany",
      "population": 83644258,
      "owner_id": "npc-7",
      "base_soldier_value": 6,
      "soldiers": 6
    },
    {
      "id": "guinea-bissau",
      "name": "Guinea-Bissau",
      "population": 2297808,
      "owner_id": "npc-8",
      "base_soldier_value": 1,
      "soldiers": 1
    },
    {
      "id": "vanuatu",
      "name": "Vanuatu",
      "population": 342564,
      "owner_id": "npc-9",
      "base_soldier_value": 1,
      "soldiers": 1
    }
  ],
  "players": [
    {
      "id": "human",
      "kind": "human",
      "starting_country_id": "india"
    },
    {
      "id": "npc-1",
      "kind": "npc",
      "starting_country_id": "burundi"
    },
    {
      "id": "npc-2",
      "kind": "npc",
      "starting_country_id": "somalia"
    },
    {
      "id": "npc-3",
      "kind": "npc",
      "starting_country_id": "turkmenistan"
    },
    {
      "id": "npc-4",
      "kind": "npc",
      "starting_country_id": "zimbabwe"
    },
    {
      "id": "npc-5",
      "kind": "npc",
      "starting_country_id": "swaziland"
    },
    {
      "id": "npc-6",
      "kind": "npc",
      "starting_country_id": "peru"
    },
    {
      "id": "npc-7",
      "kind": "npc",
      "starting_country_id": "germany"
    },
    {
      "id": "npc-8",
      "kind": "npc",
      "starting_country_id": "guinea-bissau"
    },
    {
      "id": "npc-9",
      "kind": "npc",
      "starting_country_id": "vanuatu"
    }
  ],
  "winner": null,
  "created_at": "2026-10-29T12:00:00Z",
  "schema_version": 3,
  "turn_order": [
    "human",
    "npc-7",
    "npc-8",
    "npc-6",
    "npc-2",
    "npc-3",
    "npc-5",
    "npc-1",
    "npc-9",
    "npc-4"
  ],
  "population_snapshot": {
    "dataset_id": "worldometer-2026-2026-10-19",
    "source_url": "https://www.worldometers.info/world-population/population-by-country/",
    "population_year": 2026,
    "retrieved_on": "2026-10-19",
    "source_sha256": "97fc89a45fd4a8a1219ce56033acdb18b2edf4a110e2416ba4677288cc5237d4"
  },
  "updated_at": "2026-10-29T12:00:00Z",
  "revision": 0,
  "turn_sequence": 0,
  "phase": "deciding",
  "pending_reinforcements": 0,
  "attack_used": false,
  "battle": null
}
```

</details>

This legacy route uses the public projection but does not declare a response model in OpenAPI.
Unversioned and schema-v2 records are readable without migration; fields absent from a historical document may be omitted.
Ownerless historical games remain read-only and cannot be claimed through actions.

Legacy 404/503 examples:

```json
{
  "detail": "Game not found"
}
```

```json
{
  "detail": "Saved game temporarily unavailable"
}
```

### POST /games/{game_id}/actions

| Parameter | Location | Required | Type | Limits/default |
|---|---|---|---|---|
| `game_id` | path | true | string | - |

Request body: JSON as shown below.

```json
{
  "action_id": "demo-human-skip-001",
  "expected_revision": 0,
  "action": {
    "type": "skip"
  }
}
```

Successful response: 200 PublicActionResult: state, events and optional/null npc_decision. This example skips the human turn and advances to an NPC.

<details>
<summary>POST /games/{game_id}/actions response</summary>

```json
{
  "state": {
    "game_name": "Frontend contract demo",
    "status": "active",
    "round": 1,
    "current_turn": 1,
    "countries": [
      {
        "id": "india",
        "name": "India",
        "population": 1476625576,
        "owner_id": "human",
        "base_soldier_value": 9,
        "soldiers": 9
      },
      {
        "id": "burundi",
        "name": "Burundi",
        "population": 14729157,
        "owner_id": "npc-1",
        "base_soldier_value": 3,
        "soldiers": 3
      },
      {
        "id": "somalia",
        "name": "Somalia",
        "population": 20305907,
        "owner_id": "npc-2",
        "base_soldier_value": 3,
        "soldiers": 3
      },
      {
        "id": "turkmenistan",
        "name": "Turkmenistan",
        "population": 7736632,
        "owner_id": "npc-3",
        "base_soldier_value": 2,
        "soldiers": 2
      },
      {
        "id": "zimbabwe",
        "name": "Zimbabwe",
        "population": 17273580,
        "owner_id": "npc-4",
        "base_soldier_value": 3,
        "soldiers": 3
      },
      {
        "id": "swaziland",
        "name": "Eswatini",
        "population": 1269859,
        "owner_id": "npc-5",
        "base_soldier_value": 1,
        "soldiers": 1
      },
      {
        "id": "peru",
        "name": "Peru",
        "population": 34922148,
        "owner_id": "npc-6",
        "base_soldier_value": 4,
        "soldiers": 4
      },
      {
        "id": "germany",
        "name": "Germany",
        "population": 83644258,
        "owner_id": "npc-7",
        "base_soldier_value": 6,
        "soldiers": 6
      },
      {
        "id": "guinea-bissau",
        "name": "Guinea-Bissau",
        "population": 2297808,
        "owner_id": "npc-8",
        "base_soldier_value": 1,
        "soldiers": 1
      },
      {
        "id": "vanuatu",
        "name": "Vanuatu",
        "population": 342564,
        "owner_id": "npc-9",
        "base_soldier_value": 1,
        "soldiers": 1
      }
    ],
    "players": [
      {
        "id": "human",
        "kind": "human",
        "starting_country_id": "india"
      },
      {
        "id": "npc-1",
        "kind": "npc",
        "starting_country_id": "burundi"
      },
      {
        "id": "npc-2",
        "kind": "npc",
        "starting_country_id": "somalia"
      },
      {
        "id": "npc-3",
        "kind": "npc",
        "starting_country_id": "turkmenistan"
      },
      {
        "id": "npc-4",
        "kind": "npc",
        "starting_country_id": "zimbabwe"
      },
      {
        "id": "npc-5",
        "kind": "npc",
        "starting_country_id": "swaziland"
      },
      {
        "id": "npc-6",
        "kind": "npc",
        "starting_country_id": "peru"
      },
      {
        "id": "npc-7",
        "kind": "npc",
        "starting_country_id": "germany"
      },
      {
        "id": "npc-8",
        "kind": "npc",
        "starting_country_id": "guinea-bissau"
      },
      {
        "id": "npc-9",
        "kind": "npc",
        "starting_country_id": "vanuatu"
      }
    ],
    "winner": null,
    "created_at": "2026-10-29T12:00:00Z",
    "schema_version": 3,
    "turn_order": [
      "human",
      "npc-7",
      "npc-8",
      "npc-6",
      "npc-2",
      "npc-3",
      "npc-5",
      "npc-1",
      "npc-9",
      "npc-4"
    ],
    "population_snapshot": {
      "dataset_id": "worldometer-2026-2026-10-19",
      "source_url": "https://www.worldometers.info/world-population/population-by-country/",
      "population_year": 2026,
      "retrieved_on": "2026-10-19",
      "source_sha256": "97fc89a45fd4a8a1219ce56033acdb18b2edf4a110e2416ba4677288cc5237d4"
    },
    "updated_at": "2026-10-29T12:00:01Z",
    "revision": 1,
    "turn_sequence": 1,
    "phase": "deciding",
    "pending_reinforcements": 0,
    "attack_used": false,
    "battle": null
  },
  "events": [
    {
      "type": "turn_ended",
      "actor_id": "human",
      "round": 1,
      "turn_sequence": 0,
      "source_id": null,
      "target_id": null,
      "player_id": null,
      "amount": null,
      "attacker_dice": [],
      "defender_dice": [],
      "attacker_losses": 0,
      "defender_losses": 0,
      "allocations": []
    },
    {
      "type": "turn_started",
      "actor_id": "npc-7",
      "round": 1,
      "turn_sequence": 1,
      "source_id": null,
      "target_id": null,
      "player_id": null,
      "amount": 0,
      "attacker_dice": [],
      "defender_dice": [],
      "attacker_losses": 0,
      "defender_losses": 0,
      "allocations": []
    }
  ],
  "npc_decision": null
}
```

</details>

No human player_id, actor kind, owner account, dice, state or NPC evidence can be supplied.
New human action IDs must not start with npc-; the only exception is replay of an already-existing historical human receipt.
Action response state commonly omits _id: keep the route game_id separately.
Illegal actions, wrong active participant/phase and unsupported runtime state are rejected; successful receipt replay returns its original result.

### POST /games/{game_id}/npc-steps

| Parameter | Location | Required | Type | Limits/default |
|---|---|---|---|---|
| `game_id` | path | true | string | - |

Request body: JSON as shown below.

```json
{
  "expected_revision": 1
}
```

Successful response: 200 PublicActionResult from one server-selected NPC action, not necessarily an entire turn. This request follows the human skip example.

<details>
<summary>POST /games/{game_id}/npc-steps response</summary>

```json
{
  "state": {
    "game_name": "Frontend contract demo",
    "status": "active",
    "round": 1,
    "current_turn": 1,
    "countries": [
      {
        "id": "india",
        "name": "India",
        "population": 1476625576,
        "owner_id": "human",
        "base_soldier_value": 9,
        "soldiers": 9
      },
      {
        "id": "burundi",
        "name": "Burundi",
        "population": 14729157,
        "owner_id": "npc-1",
        "base_soldier_value": 3,
        "soldiers": 3
      },
      {
        "id": "somalia",
        "name": "Somalia",
        "population": 20305907,
        "owner_id": "npc-2",
        "base_soldier_value": 3,
        "soldiers": 3
      },
      {
        "id": "turkmenistan",
        "name": "Turkmenistan",
        "population": 7736632,
        "owner_id": "npc-3",
        "base_soldier_value": 2,
        "soldiers": 2
      },
      {
        "id": "zimbabwe",
        "name": "Zimbabwe",
        "population": 17273580,
        "owner_id": "npc-4",
        "base_soldier_value": 3,
        "soldiers": 3
      },
      {
        "id": "swaziland",
        "name": "Eswatini",
        "population": 1269859,
        "owner_id": "npc-5",
        "base_soldier_value": 1,
        "soldiers": 1
      },
      {
        "id": "peru",
        "name": "Peru",
        "population": 34922148,
        "owner_id": "npc-6",
        "base_soldier_value": 4,
        "soldiers": 4
      },
      {
        "id": "germany",
        "name": "Germany",
        "population": 83644258,
        "owner_id": "npc-7",
        "base_soldier_value": 6,
        "soldiers": 6
      },
      {
        "id": "guinea-bissau",
        "name": "Guinea-Bissau",
        "population": 2297808,
        "owner_id": "npc-8",
        "base_soldier_value": 1,
        "soldiers": 1
      },
      {
        "id": "vanuatu",
        "name": "Vanuatu",
        "population": 342564,
        "owner_id": "npc-9",
        "base_soldier_value": 1,
        "soldiers": 1
      }
    ],
    "players": [
      {
        "id": "human",
        "kind": "human",
        "starting_country_id": "india"
      },
      {
        "id": "npc-1",
        "kind": "npc",
        "starting_country_id": "burundi"
      },
      {
        "id": "npc-2",
        "kind": "npc",
        "starting_country_id": "somalia"
      },
      {
        "id": "npc-3",
        "kind": "npc",
        "starting_country_id": "turkmenistan"
      },
      {
        "id": "npc-4",
        "kind": "npc",
        "starting_country_id": "zimbabwe"
      },
      {
        "id": "npc-5",
        "kind": "npc",
        "starting_country_id": "swaziland"
      },
      {
        "id": "npc-6",
        "kind": "npc",
        "starting_country_id": "peru"
      },
      {
        "id": "npc-7",
        "kind": "npc",
        "starting_country_id": "germany"
      },
      {
        "id": "npc-8",
        "kind": "npc",
        "starting_country_id": "guinea-bissau"
      },
      {
        "id": "npc-9",
        "kind": "npc",
        "starting_country_id": "vanuatu"
      }
    ],
    "winner": null,
    "created_at": "2026-10-29T12:00:00Z",
    "schema_version": 3,
    "turn_order": [
      "human",
      "npc-7",
      "npc-8",
      "npc-6",
      "npc-2",
      "npc-3",
      "npc-5",
      "npc-1",
      "npc-9",
      "npc-4"
    ],
    "population_snapshot": {
      "dataset_id": "worldometer-2026-2026-10-19",
      "source_url": "https://www.worldometers.info/world-population/population-by-country/",
      "population_year": 2026,
      "retrieved_on": "2026-10-19",
      "source_sha256": "97fc89a45fd4a8a1219ce56033acdb18b2edf4a110e2416ba4677288cc5237d4"
    },
    "updated_at": "2026-10-29T12:00:02Z",
    "revision": 2,
    "turn_sequence": 1,
    "phase": "attacking",
    "pending_reinforcements": 0,
    "attack_used": true,
    "battle": {
      "source_id": "germany",
      "target_id": "guinea-bissau"
    }
  },
  "events": [
    {
      "type": "attack_started",
      "actor_id": "npc-7",
      "round": 1,
      "turn_sequence": 1,
      "source_id": "germany",
      "target_id": "guinea-bissau",
      "player_id": null,
      "amount": null,
      "attacker_dice": [],
      "defender_dice": [],
      "attacker_losses": 0,
      "defender_losses": 0,
      "allocations": []
    }
  ],
  "npc_decision": {
    "strategy_version": "balanced-v1",
    "action": {
      "type": "start_attack",
      "source_id": "germany",
      "target_id": "guinea-bissau"
    },
    "reason": "attack",
    "explanation": "Attack against Guinea-Bissau from Germany: 5 available against 1 defender, margin 4, conquest reward 2, heuristic score 76. A capture would eliminate this opponent. The authoritative engine determines the dice; capture is not guaranteed.",
    "evaluation": {
      "actor_id": "npc-7",
      "revision": 1,
      "turn_sequence": 1,
      "round": 1,
      "countries": [
        {
          "id": "burundi",
          "name": "Burundi",
          "owner_id": "npc-1",
          "soldiers": 3,
          "base_soldier_value": 3
        },
        {
          "id": "germany",
          "name": "Germany",
          "owner_id": "npc-7",
          "soldiers": 6,
          "base_soldier_value": 6
        },
        {
          "id": "guinea-bissau",
          "name": "Guinea-Bissau",
          "owner_id": "npc-8",
          "soldiers": 1,
          "base_soldier_value": 1
        },
        {
          "id": "india",
          "name": "India",
          "owner_id": "human",
          "soldiers": 9,
          "base_soldier_value": 9
        },
        {
          "id": "peru",
          "name": "Peru",
          "owner_id": "npc-6",
          "soldiers": 4,
          "base_soldier_value": 4
        },
        {
          "id": "somalia",
          "name": "Somalia",
          "owner_id": "npc-2",
          "soldiers": 3,
          "base_soldier_value": 3
        },
        {
          "id": "swaziland",
          "name": "Eswatini",
          "owner_id": "npc-5",
          "soldiers": 1,
          "base_soldier_value": 1
        },
        {
          "id": "turkmenistan",
          "name": "Turkmenistan",
          "owner_id": "npc-3",
          "soldiers": 2,
          "base_soldier_value": 2
        },
        {
          "id": "vanuatu",
          "name": "Vanuatu",
          "owner_id": "npc-9",
          "soldiers": 1,
          "base_soldier_value": 1
        },
        {
          "id": "zimbabwe",
          "name": "Zimbabwe",
          "owner_id": "npc-4",
          "soldiers": 3,
          "base_soldier_value": 3
        }
      ],
      "participants": [
        {
          "id": "human",
          "kind": "human",
          "countries": 1,
          "soldiers": 9,
          "reinforcement_income": 2,
          "turn_distance": 9
        },
        {
          "id": "npc-1",
          "kind": "npc",
          "countries": 1,
          "soldiers": 3,
          "reinforcement_income": 2,
          "turn_distance": 6
        },
        {
          "id": "npc-2",
          "kind": "npc",
          "countries": 1,
          "soldiers": 3,
          "reinforcement_income": 2,
          "turn_distance": 3
        },
        {
          "id": "npc-3",
          "kind": "npc",
          "countries": 1,
          "soldiers": 2,
          "reinforcement_income": 2,
          "turn_distance": 4
        },
        {
          "id": "npc-4",
          "kind": "npc",
          "countries": 1,
          "soldiers": 3,
          "reinforcement_income": 2,
          "turn_distance": 8
        },
        {
          "id": "npc-5",
          "kind": "npc",
          "countries": 1,
          "soldiers": 1,
          "reinforcement_income": 2,
          "turn_distance": 5
        },
        {
          "id": "npc-6",
          "kind": "npc",
          "countries": 1,
          "soldiers": 4,
          "reinforcement_income": 2,
          "turn_distance": 2
        },
        {
          "id": "npc-7",
          "kind": "npc",
          "countries": 1,
          "soldiers": 6,
          "reinforcement_income": 2,
          "turn_distance": 0
        },
        {
          "id": "npc-8",
          "kind": "npc",
          "countries": 1,
          "soldiers": 1,
          "reinforcement_income": 2,
          "turn_distance": 1
        },
        {
          "id": "npc-9",
          "kind": "npc",
          "countries": 1,
          "soldiers": 1,
          "reinforcement_income": 2,
          "turn_distance": 7
        }
      ],
      "attacks": [
        {
          "source_id": "germany",
          "target_id": "burundi",
          "available": 5,
          "defenders": 3,
          "margin": 2,
          "reward": 2,
          "eliminates": true,
          "wins": false,
          "opponent_income": 2,
          "income_gain": 2,
          "income_denial": 2,
          "exposure_cost": 9,
          "opponent_power_bonus": 0,
          "urgency_bonus": 4,
          "score": 61,
          "acceptable": true
        },
        {
          "source_id": "germany",
          "target_id": "guinea-bissau",
          "available": 5,
          "defenders": 1,
          "margin": 4,
          "reward": 2,
          "eliminates": true,
          "wins": false,
          "opponent_income": 2,
          "income_gain": 2,
          "income_denial": 2,
          "exposure_cost": 7,
          "opponent_power_bonus": 0,
          "urgency_bonus": 9,
          "score": 76,
          "acceptable": true
        },
        {
          "source_id": "germany",
          "target_id": "india",
          "available": 5,
          "defenders": 9,
          "margin": -4,
          "reward": 4,
          "eliminates": true,
          "wins": false,
          "opponent_income": 2,
          "income_gain": 2,
          "income_denial": 2,
          "exposure_cost": 5,
          "opponent_power_bonus": 2,
          "urgency_bonus": 1,
          "score": 6,
          "acceptable": false
        },
        {
          "source_id": "germany",
          "target_id": "peru",
          "available": 5,
          "defenders": 4,
          "margin": 1,
          "reward": 2,
          "eliminates": true,
          "wins": false,
          "opponent_income": 2,
          "income_gain": 2,
          "income_denial": 2,
          "exposure_cost": 10,
          "opponent_power_bonus": 1,
          "urgency_bonus": 8,
          "score": 61,
          "acceptable": true
        },
        {
          "source_id": "germany",
          "target_id": "somalia",
          "available": 5,
          "defenders": 3,
          "margin": 2,
          "reward": 2,
          "eliminates": true,
          "wins": false,
          "opponent_income": 2,
          "income_gain": 2,
          "income_denial": 2,
          "exposure_cost": 9,
          "opponent_power_bonus": 0,
          "urgency_bonus": 7,
          "score": 64,
          "acceptable": true
        },
        {
          "source_id": "germany",
          "target_id": "swaziland",
          "available": 5,
          "defenders": 1,
          "margin": 4,
          "reward": 2,
          "eliminates": true,
          "wins": false,
          "opponent_income": 2,
          "income_gain": 2,
          "income_denial": 2,
          "exposure_cost": 7,
          "opponent_power_bonus": 0,
          "urgency_bonus": 5,
          "score": 72,
          "acceptable": true
        },
        {
          "source_id": "germany",
          "target_id": "turkmenistan",
          "available": 5,
          "defenders": 2,
          "margin": 3,
          "reward": 2,
          "eliminates": true,
          "wins": false,
          "opponent_income": 2,
          "income_gain": 2,
          "income_denial": 2,
          "exposure_cost": 8,
          "opponent_power_bonus": 0,
          "urgency_bonus": 6,
          "score": 68,
          "acceptable": true
        },
        {
          "source_id": "germany",
          "target_id": "vanuatu",
          "available": 5,
          "defenders": 1,
          "margin": 4,
          "reward": 2,
          "eliminates": true,
          "wins": false,
          "opponent_income": 2,
          "income_gain": 2,
          "income_denial": 2,
          "exposure_cost": 7,
          "opponent_power_bonus": 0,
          "urgency_bonus": 3,
          "score": 70,
          "acceptable": true
        },
        {
          "source_id": "germany",
          "target_id": "zimbabwe",
          "available": 5,
          "defenders": 3,
          "margin": 2,
          "reward": 2,
          "eliminates": true,
          "wins": false,
          "opponent_income": 2,
          "income_gain": 2,
          "income_denial": 2,
          "exposure_cost": 9,
          "opponent_power_bonus": 0,
          "urgency_bonus": 2,
          "score": 59,
          "acceptable": true
        }
      ],
      "defensive_exposure": 2,
      "concentration": 36
    },
    "projected_potential": null
  }
}
```

</details>

The server chooses the policy, action, game-local actor and deterministic NPC action ID.
Send no action_id, strategy seed, actor, dice or decision body. Retrying the same expected_revision can replay the stored NPC result.
A human turn or already-completed game is not a successful no-op: without an applicable replay, no active NPC action yields
409 invalid_game_action. A stale revision yields 409 revision_conflict.

### GET /games/{game_id}/events

| Parameter | Location | Required | Type | Limits/default |
|---|---|---|---|---|
| `game_id` | path | true | string | - |
| `after_revision` | query | false | integer | minimum=0; default=0 |
| `limit` | query | false | integer | minimum=1; maximum=100; default=20 |

Request body: none; do not send JSON.

Successful response: 200 PublicEventPage. Top-level events are committed-action entries; each entry has its own nested factual events array.

<details>
<summary>GET /games/{game_id}/events response</summary>

```json
{
  "events": [
    {
      "revision": 1,
      "action_id": "demo-human-skip-001",
      "actor": {
        "player_id": "human",
        "kind": "human"
      },
      "committed_at": "2026-10-29T12:00:01Z",
      "events": [
        {
          "type": "turn_ended",
          "actor_id": "human",
          "round": 1,
          "turn_sequence": 0,
          "source_id": null,
          "target_id": null,
          "player_id": null,
          "amount": null,
          "attacker_dice": [],
          "defender_dice": [],
          "attacker_losses": 0,
          "defender_losses": 0,
          "allocations": []
        },
        {
          "type": "turn_started",
          "actor_id": "npc-7",
          "round": 1,
          "turn_sequence": 1,
          "source_id": null,
          "target_id": null,
          "player_id": null,
          "amount": 0,
          "attacker_dice": [],
          "defender_dice": [],
          "attacker_losses": 0,
          "defender_losses": 0,
          "allocations": []
        }
      ],
      "npc_decision": null
    },
    {
      "revision": 2,
      "action_id": "npc-balanced-v1-1-1",
      "actor": {
        "player_id": "npc-7",
        "kind": "npc"
      },
      "committed_at": "2026-10-29T12:00:02Z",
      "events": [
        {
          "type": "attack_started",
          "actor_id": "npc-7",
          "round": 1,
          "turn_sequence": 1,
          "source_id": "germany",
          "target_id": "guinea-bissau",
          "player_id": null,
          "amount": null,
          "attacker_dice": [],
          "defender_dice": [],
          "attacker_losses": 0,
          "defender_losses": 0,
          "allocations": []
        }
      ],
      "npc_decision": {
        "strategy_version": "balanced-v1",
        "action": {
          "type": "start_attack",
          "source_id": "germany",
          "target_id": "guinea-bissau"
        },
        "reason": "attack",
        "explanation": "Attack against Guinea-Bissau from Germany: 5 available against 1 defender, margin 4, conquest reward 2, heuristic score 76. A capture would eliminate this opponent. The authoritative engine determines the dice; capture is not guaranteed.",
        "evaluation": {
          "actor_id": "npc-7",
          "revision": 1,
          "turn_sequence": 1,
          "round": 1,
          "countries": [
            {
              "id": "burundi",
              "name": "Burundi",
              "owner_id": "npc-1",
              "soldiers": 3,
              "base_soldier_value": 3
            },
            {
              "id": "germany",
              "name": "Germany",
              "owner_id": "npc-7",
              "soldiers": 6,
              "base_soldier_value": 6
            },
            {
              "id": "guinea-bissau",
              "name": "Guinea-Bissau",
              "owner_id": "npc-8",
              "soldiers": 1,
              "base_soldier_value": 1
            },
            {
              "id": "india",
              "name": "India",
              "owner_id": "human",
              "soldiers": 9,
              "base_soldier_value": 9
            },
            {
              "id": "peru",
              "name": "Peru",
              "owner_id": "npc-6",
              "soldiers": 4,
              "base_soldier_value": 4
            },
            {
              "id": "somalia",
              "name": "Somalia",
              "owner_id": "npc-2",
              "soldiers": 3,
              "base_soldier_value": 3
            },
            {
              "id": "swaziland",
              "name": "Eswatini",
              "owner_id": "npc-5",
              "soldiers": 1,
              "base_soldier_value": 1
            },
            {
              "id": "turkmenistan",
              "name": "Turkmenistan",
              "owner_id": "npc-3",
              "soldiers": 2,
              "base_soldier_value": 2
            },
            {
              "id": "vanuatu",
              "name": "Vanuatu",
              "owner_id": "npc-9",
              "soldiers": 1,
              "base_soldier_value": 1
            },
            {
              "id": "zimbabwe",
              "name": "Zimbabwe",
              "owner_id": "npc-4",
              "soldiers": 3,
              "base_soldier_value": 3
            }
          ],
          "participants": [
            {
              "id": "human",
              "kind": "human",
              "countries": 1,
              "soldiers": 9,
              "reinforcement_income": 2,
              "turn_distance": 9
            },
            {
              "id": "npc-1",
              "kind": "npc",
              "countries": 1,
              "soldiers": 3,
              "reinforcement_income": 2,
              "turn_distance": 6
            },
            {
              "id": "npc-2",
              "kind": "npc",
              "countries": 1,
              "soldiers": 3,
              "reinforcement_income": 2,
              "turn_distance": 3
            },
            {
              "id": "npc-3",
              "kind": "npc",
              "countries": 1,
              "soldiers": 2,
              "reinforcement_income": 2,
              "turn_distance": 4
            },
            {
              "id": "npc-4",
              "kind": "npc",
              "countries": 1,
              "soldiers": 3,
              "reinforcement_income": 2,
              "turn_distance": 8
            },
            {
              "id": "npc-5",
              "kind": "npc",
              "countries": 1,
              "soldiers": 1,
              "reinforcement_income": 2,
              "turn_distance": 5
            },
            {
              "id": "npc-6",
              "kind": "npc",
              "countries": 1,
              "soldiers": 4,
              "reinforcement_income": 2,
              "turn_distance": 2
            },
            {
              "id": "npc-7",
              "kind": "npc",
              "countries": 1,
              "soldiers": 6,
              "reinforcement_income": 2,
              "turn_distance": 0
            },
            {
              "id": "npc-8",
              "kind": "npc",
              "countries": 1,
              "soldiers": 1,
              "reinforcement_income": 2,
              "turn_distance": 1
            },
            {
              "id": "npc-9",
              "kind": "npc",
              "countries": 1,
              "soldiers": 1,
              "reinforcement_income": 2,
              "turn_distance": 7
            }
          ],
          "attacks": [
            {
              "source_id": "germany",
              "target_id": "burundi",
              "available": 5,
              "defenders": 3,
              "margin": 2,
              "reward": 2,
              "eliminates": true,
              "wins": false,
              "opponent_income": 2,
              "income_gain": 2,
              "income_denial": 2,
              "exposure_cost": 9,
              "opponent_power_bonus": 0,
              "urgency_bonus": 4,
              "score": 61,
              "acceptable": true
            },
            {
              "source_id": "germany",
              "target_id": "guinea-bissau",
              "available": 5,
              "defenders": 1,
              "margin": 4,
              "reward": 2,
              "eliminates": true,
              "wins": false,
              "opponent_income": 2,
              "income_gain": 2,
              "income_denial": 2,
              "exposure_cost": 7,
              "opponent_power_bonus": 0,
              "urgency_bonus": 9,
              "score": 76,
              "acceptable": true
            },
            {
              "source_id": "germany",
              "target_id": "india",
              "available": 5,
              "defenders": 9,
              "margin": -4,
              "reward": 4,
              "eliminates": true,
              "wins": false,
              "opponent_income": 2,
              "income_gain": 2,
              "income_denial": 2,
              "exposure_cost": 5,
              "opponent_power_bonus": 2,
              "urgency_bonus": 1,
              "score": 6,
              "acceptable": false
            },
            {
              "source_id": "germany",
              "target_id": "peru",
              "available": 5,
              "defenders": 4,
              "margin": 1,
              "reward": 2,
              "eliminates": true,
              "wins": false,
              "opponent_income": 2,
              "income_gain": 2,
              "income_denial": 2,
              "exposure_cost": 10,
              "opponent_power_bonus": 1,
              "urgency_bonus": 8,
              "score": 61,
              "acceptable": true
            },
            {
              "source_id": "germany",
              "target_id": "somalia",
              "available": 5,
              "defenders": 3,
              "margin": 2,
              "reward": 2,
              "eliminates": true,
              "wins": false,
              "opponent_income": 2,
              "income_gain": 2,
              "income_denial": 2,
              "exposure_cost": 9,
              "opponent_power_bonus": 0,
              "urgency_bonus": 7,
              "score": 64,
              "acceptable": true
            },
            {
              "source_id": "germany",
              "target_id": "swaziland",
              "available": 5,
              "defenders": 1,
              "margin": 4,
              "reward": 2,
              "eliminates": true,
              "wins": false,
              "opponent_income": 2,
              "income_gain": 2,
              "income_denial": 2,
              "exposure_cost": 7,
              "opponent_power_bonus": 0,
              "urgency_bonus": 5,
              "score": 72,
              "acceptable": true
            },
            {
              "source_id": "germany",
              "target_id": "turkmenistan",
              "available": 5,
              "defenders": 2,
              "margin": 3,
              "reward": 2,
              "eliminates": true,
              "wins": false,
              "opponent_income": 2,
              "income_gain": 2,
              "income_denial": 2,
              "exposure_cost": 8,
              "opponent_power_bonus": 0,
              "urgency_bonus": 6,
              "score": 68,
              "acceptable": true
            },
            {
              "source_id": "germany",
              "target_id": "vanuatu",
              "available": 5,
              "defenders": 1,
              "margin": 4,
              "reward": 2,
              "eliminates": true,
              "wins": false,
              "opponent_income": 2,
              "income_gain": 2,
              "income_denial": 2,
              "exposure_cost": 7,
              "opponent_power_bonus": 0,
              "urgency_bonus": 3,
              "score": 70,
              "acceptable": true
            },
            {
              "source_id": "germany",
              "target_id": "zimbabwe",
              "available": 5,
              "defenders": 3,
              "margin": 2,
              "reward": 2,
              "eliminates": true,
              "wins": false,
              "opponent_income": 2,
              "income_gain": 2,
              "income_denial": 2,
              "exposure_cost": 9,
              "opponent_power_bonus": 0,
              "urgency_bonus": 2,
              "score": 59,
              "acceptable": true
            }
          ],
          "defensive_exposure": 2,
          "concentration": 36
        },
        "projected_potential": null
      }
    }
  ],
  "after_revision": 0,
  "next_after_revision": 2,
  "has_more": false
}
```

</details>

Page keys: events, after_revision, next_after_revision, has_more.
Each entry includes revision, action_id, actor:{player_id,kind}, committed_at, events and optional/null npc_decision.
Pages contain revisions greater than after_revision, ordered ascending; use next_after_revision until has_more=false.
Historical receipts may omit NPC evidence. Empty pages keep the cursor unchanged. This endpoint does not return a full state per entry.

Empty-page response example:

```json
{
  "events": [],
  "after_revision": 2,
  "next_after_revision": 2,
  "has_more": false
}
```

### Framework documentation routes and OPTIONS

GET /openapi.json returns the complete JSON in [openapi.json](openapi.json), with no request body.
GET /docs and GET /redoc return framework-generated text/html documentation, not JSON. GET /docs/oauth2-redirect returns
Swagger's text/html redirect helper; no OAuth authorization-code or bearer-token login is implemented by that helper.
HEAD on these four routes has the corresponding headers and an empty body. There is no JSON request/response example for HTML or HEAD.
Their exact HTML is framework-generated; external documentation asset/CDN availability is UNVERIFIED offline.

Representative HTML response excerpt (not the complete generated document):

```html
<!DOCTYPE html>
<html><head><title>Geopolitics Game API - Swagger UI</title></head><body>...</body></html>
```

With an installed context and trusted Origin, a preflight includes Origin, Access-Control-Request-Method, and optionally
Access-Control-Request-Headers. Allowed methods are GET/POST; allowed custom headers are Content-Type, X-CSRF-Token and Idempotency-Key.
A valid preflight returns text/plain OK (200). Disallowed requested method/headers can return text/plain 400.
Without trusted-Origin handling, ordinary routing applies, commonly 405. No context is installed during this export, so no live CORS behavior was tested.

## 4. Full public game-state shape

### PublicGame

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `_id` | string / null | no | -; - |
| `attack_used` | boolean / null | no | -; - |
| `battle` | PublicBattle / null | no | -; - |
| `countries` | array<PublicCountry> | no | default=[] |
| `created_at` | string / null | no | format="date-time"; - |
| `current_turn` | integer / null | no | -; - |
| `game_name` | string | yes | - |
| `pending_reinforcements` | integer / null | no | -; - |
| `phase` | string / null | no | enum=["allocating", "deciding", "attacking", "post_attack", "finished"]; - |
| `players` | array<PublicParticipant> | no | default=[] |
| `population_snapshot` | PublicPopulationSnapshot / null | no | -; - |
| `revision` | integer / null | no | -; - |
| `round` | integer / null | no | -; - |
| `schema_version` | integer / null | no | enum=[2, 3]; - |
| `status` | string | no | enum=["waiting", "active", "completed"]; default="waiting" |
| `turn_order` | array<string> / null | no | -; - |
| `turn_sequence` | integer / null | no | -; - |
| `updated_at` | string / null | no | format="date-time"; - |
| `winner` | string / null | no | -; - |

### PublicCountry

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `base_soldier_value` | integer | yes | minimum=1.0; maximum=9.0 |
| `id` | string | yes | - |
| `name` | string | yes | - |
| `owner_id` | string | yes | - |
| `population` | integer | yes | exclusiveMinimum=0.0 |
| `soldiers` | integer | yes | minimum=1.0 |

### PublicParticipant

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `id` | string | yes | - |
| `kind` | string | yes | enum=["human", "npc"] |
| `starting_country_id` | string | yes | - |

### PublicPopulationSnapshot

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `dataset_id` | string | yes | - |
| `population_year` | integer | yes | - |
| `retrieved_on` | string | yes | format="date" |
| `source_sha256` | string | yes | - |
| `source_url` | string | yes | - |

### PublicBattle

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `source_id` | string | yes | - |
| `target_id` | string | yes | - |

### PublicGameSummary

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `_id` | string | yes | - |
| `created_at` | string / null | no | format="date-time"; - |
| `current_turn` | integer / null | no | -; - |
| `game_name` | string | yes | - |
| `phase` | string / null | no | enum=["allocating", "deciding", "attacking", "post_attack", "finished"]; - |
| `revision` | integer / null | no | -; - |
| `round` | integer / null | no | -; - |
| `status` | string | yes | enum=["waiting", "active", "completed"] |
| `updated_at` | string / null | no | format="date-time"; - |
| `winner` | string / null | no | -; - |

### PublicGameList

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `games` | array<PublicGameSummary> | yes | - |
| `next_cursor` | string / null | yes | -; - |

For a new playable game, server runtime invariants require exactly ten distinct countries, ten participants and a ten-member turn_order,
one human and nine NPCs. PublicGame is intentionally more permissive for historical reads: only game_name is required by its public schema;
optional/default fields can be omitted by exclude_unset. Do not manufacture a playable state for a legacy waiting game.
current_turn is an index into turn_order, not players. The active participant is turn_order[current_turn]; look that ID up in players
to find kind=human or kind=npc. An eliminated participant can remain in players but owns no countries and receives no turn.
winner and country.owner_id are game-local participant IDs, never MongoDB account IDs.

_id is a JSON string on saved-game/creation responses; an action result's state is a RuntimeGame projection and usually omits it.
Keep game identity in the URL/query key separately. Round numbers start at 1; revisions start at 0 and successful new actions advance by 1.
phase is allocating, deciding, attacking, post_attack or finished; status is active/completed for runtime games, with waiting also supported on legacy public reads.
pending_reinforcements is the remaining allocation budget, attack_used is the per-turn attack flag, battle identifies the locked pair.
A completed winner owns all ten countries.
Runtime/action timestamps normalize to UTC milliseconds. Saved-game public projection can preserve naive-UTC BSON datetime serialization
without a Z suffix; the public model itself does not normalize it. Do not infer local timezone from an offset-less legacy timestamp.
Exact current deployed payload timestamps are UNVERIFIED offline.

Evidence: [backend/app/models/runtime_game.py:43](../backend/app/models/runtime_game.py#L43), [backend/app/services/public_game_service.py:13](../backend/app/services/public_game_service.py#L13), [backend/app/engine/state_adapter.py:8](../backend/app/engine/state_adapter.py#L8).

The complete 10-country example appears in both POST /games and GET /games/{game_id} above.
Public models recursively discard unknown fields. Hidden from public game/event/decision responses:
access (owner_user_id, human_player_id, access version and bound_at); creation key/fingerprint; account records, password hashes and
authorization revisions; session credentials/hashes/CSRF; internal receipt _id/fingerprint; NPC state_digest, tie_breaker/seed and tie_break_used.
Population provenance, actor.player_id, command action_id, strategy_version, factual events and public decision evaluation are intentionally visible.
There is no public is_owner/can_act field. Determine owner UI membership through the authenticated owner-scoped list; the server remains authoritative.

Evidence: [backend/app/models/game_api.py:12](../backend/app/models/game_api.py#L12), [backend/app/services/public_game_service.py:27](../backend/app/services/public_game_service.py#L27), [backend/app/models/game_access.py:8](../backend/app/models/game_access.py#L8).

Legacy read-only example (not a production record):

```json
{
  "_id": "650000000000000000000003",
  "game_name": "Historical waiting example",
  "status": "waiting",
  "countries": [],
  "players": [],
  "winner": null,
  "created_at": "2026-10-29T12:00:00Z"
}
```

## 5. Exact actions and combat events

### ActionCommand

Unknown input properties are forbidden by this component.

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `action` | Allocate / Transfer / StartAttack / Roll / StopAttack / Skip / EndTurn | yes | -; -; -; -; -; -; - |
| `action_id` | string | yes | minLength=1; maxLength=128; pattern="^[a-zA-Z0-9_-]+$" |
| `expected_revision` | integer | yes | minimum=0.0 |

### Allocation

Unknown input properties are forbidden by this component.

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `amount` | integer | yes | exclusiveMinimum=0.0 |
| `country_id` | string | yes | minLength=1; maxLength=128 |

### Allocate

Unknown input properties are forbidden by this component.

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `allocations` | array<Allocation> | yes | minItems=1; maxItems=10 |
| `type` | string | no | const="allocate"; default="allocate" |

### Transfer

Unknown input properties are forbidden by this component.

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `amount` | integer | yes | exclusiveMinimum=0.0 |
| `source_id` | string | yes | minLength=1; maxLength=128 |
| `target_id` | string | yes | minLength=1; maxLength=128 |
| `type` | string | no | const="transfer"; default="transfer" |

### StartAttack

Unknown input properties are forbidden by this component.

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `source_id` | string | yes | minLength=1; maxLength=128 |
| `target_id` | string | yes | minLength=1; maxLength=128 |
| `type` | string | no | const="start_attack"; default="start_attack" |

### Roll

Unknown input properties are forbidden by this component.

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `type` | string | no | const="roll"; default="roll" |

### StopAttack

Unknown input properties are forbidden by this component.

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `type` | string | no | const="stop_attack"; default="stop_attack" |

### Skip

Unknown input properties are forbidden by this component.

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `type` | string | no | const="skip"; default="skip" |

### EndTurn

Unknown input properties are forbidden by this component.

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `type` | string | no | const="end_turn"; default="end_turn" |

### NpcStepRequest

Unknown input properties are forbidden by this component.

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `expected_revision` | integer | yes | minimum=0.0 |

ActionCommand.action is a discriminated union on type. Always send type explicitly, even though individual Python action classes have defaults.
Exact types are start_attack, roll, stop_attack, transfer, allocate, skip, end_turn. There are no attack, reinforce, end-turn or fast_forward aliases.
action_id is 1-128 ASCII letters/digits/underscore/hyphen, unique per game's receipt key; expected_revision is a strict nonnegative JSON integer.
JSON strings, booleans and fractional numbers are not valid revisions or positive action amounts. Extra command/action fields are forbidden.
Country identifiers in actions are nonempty, at most 128 characters; transfer amount is a strict positive integer.
Allocation has 1-10 distinct country entries, each with a strict positive integer amount. Allocate the complete server-provided budget
to owned countries; the engine validates ownership and the exact sum.

| Action type | Legal phase | Payload / behavior |
|---|---|---|
| start_attack | deciding | Owned source_id with >=2 soldiers; enemy target_id; locks the pair and does not roll. |
| roll | attacking | Only type; server rolls the locked battle. |
| stop_attack | attacking | Only type; stops battle and ends the turn. |
| transfer | deciding or post_attack | source_id, target_id, amount; distinct owned countries, retain >=1 at source. |
| allocate | allocating | allocations:[{country_id,amount}]; complete pending_reinforcements budget. |
| skip | deciding | Only type; ends the turn. |
| end_turn | post_attack | Only type; ends the turn after resolved attack. |

Typed start_attack request example; revision below is illustrative, not a legal phase guarantee:

```json
{
  "action_id": "demo-action-0",
  "expected_revision": 0,
  "action": {
    "type": "start_attack",
    "source_id": "india",
    "target_id": "burundi"
  }
}
```

Typed roll request example; revision below is illustrative, not a legal phase guarantee:

```json
{
  "action_id": "demo-action-1",
  "expected_revision": 1,
  "action": {
    "type": "roll"
  }
}
```

Typed stop_attack request example; revision below is illustrative, not a legal phase guarantee:

```json
{
  "action_id": "demo-action-2",
  "expected_revision": 2,
  "action": {
    "type": "stop_attack"
  }
}
```

Typed transfer request example; revision below is illustrative, not a legal phase guarantee:

```json
{
  "action_id": "demo-action-3",
  "expected_revision": 3,
  "action": {
    "type": "transfer",
    "source_id": "india",
    "target_id": "burundi",
    "amount": 2
  }
}
```

Typed allocate request example; revision below is illustrative, not a legal phase guarantee:

```json
{
  "action_id": "demo-action-4",
  "expected_revision": 4,
  "action": {
    "type": "allocate",
    "allocations": [
      {
        "country_id": "india",
        "amount": 2
      }
    ]
  }
}
```

Typed skip request example; revision below is illustrative, not a legal phase guarantee:

```json
{
  "action_id": "demo-action-5",
  "expected_revision": 5,
  "action": {
    "type": "skip"
  }
}
```

Typed end_turn request example; revision below is illustrative, not a legal phase guarantee:

```json
{
  "action_id": "demo-action-6",
  "expected_revision": 6,
  "action": {
    "type": "end_turn"
  }
}
```

There is one enemy target per turn. No geographical adjacency restriction exists. Reinforcements start in round two at
2 * owned_country_count, and eliminated participants are skipped. Conquest reward is max(2, base_soldier_value // 2).
These are server rules; the frontend displays authoritative results instead of rerunning them to decide outcomes.
Same action ID and identical submission replays its original receipt. Changed content with an existing ID causes 409 action_id_conflict;
a new action against a stale revision causes 409 revision_conflict. NPC IDs are reserved as described above.

### PublicActionResult

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `events` | array<PublicGameEvent> | yes | - |
| `npc_decision` | PublicNpcDecision / null | no | -; - |
| `state` | PublicGame | yes | - |

### PublicGameEvent

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `actor_id` | string | yes | - |
| `allocations` | array<PublicAllocation> | no | default=[] |
| `amount` | integer / null | no | -; - |
| `attacker_dice` | array<integer> | no | default=[] |
| `attacker_losses` | integer | no | default=0 |
| `defender_dice` | array<integer> | no | default=[] |
| `defender_losses` | integer | no | default=0 |
| `player_id` | string / null | no | -; - |
| `round` | integer | yes | - |
| `source_id` | string / null | no | -; - |
| `target_id` | string / null | no | -; - |
| `turn_sequence` | integer | yes | - |
| `type` | string | yes | enum=["attack_started", "dice_exchange", "conquered", "eliminated", "victory", "transferred", "allocated", "attack_stopped", "attack_failed", "turn_ended", "turn_started"] |

### PublicAllocation

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `amount` | integer | yes | - |
| `country_id` | string | yes | - |

### PublicActor

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `kind` | string | yes | enum=["human", "npc"] |
| `player_id` | string | yes | - |

### PublicCommittedAction

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `action_id` | string | yes | - |
| `actor` | PublicActor | yes | - |
| `committed_at` | string | yes | format="date-time" |
| `events` | array<PublicGameEvent> | yes | - |
| `npc_decision` | PublicNpcDecision / null | no | -; - |
| `revision` | integer | yes | - |

### PublicEventPage

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `after_revision` | integer | yes | - |
| `events` | array<PublicCommittedAction> | yes | - |
| `has_more` | boolean | yes | - |
| `next_after_revision` | integer | yes | - |

Every factual event has type, actor_id, round and turn_sequence. Depending on type it uses source_id/target_id,
player_id, amount, dice/loss arrays, or allocations; unused optional fields can be null/empty or omitted by public serialization.
Supported event types: attack_started, dice_exchange, conquered, eliminated, victory, transferred, allocated,
attack_stopped, attack_failed, turn_ended, turn_started.
dice_exchange includes parallel attacker_dice/defender_dice integer arrays and attacker_losses/defender_losses.
The engine rolls independent values 1-6, pairs by original position without sorting, uses min(source soldiers-1,target soldiers)
pairs, and leaves ties alive. A roll can also emit conquest/elimination/victory or attack_failed events.
amount is the transfer/allocation amount, conquest reward, or next-turn reinforcement budget as applicable.

A server-engine-generated dice_exchange example (fixed documentation dice, never a client-computed result):

```json
{
  "type": "dice_exchange",
  "actor_id": "human",
  "round": 1,
  "turn_sequence": 0,
  "source_id": "india",
  "target_id": "burundi",
  "player_id": null,
  "amount": null,
  "attacker_dice": [
    6,
    6,
    6
  ],
  "defender_dice": [
    1,
    1,
    1
  ],
  "attacker_losses": 0,
  "defender_losses": 3,
  "allocations": []
}
```

Evidence: [backend/app/engine/actions.py:13](../backend/app/engine/actions.py#L13), [backend/app/engine/battle.py:28](../backend/app/engine/battle.py#L28), [backend/app/services/game_action_service.py:51](../backend/app/services/game_action_service.py#L51).

## 6. NPC decisions and visible fast-forward

### PublicNpcDecision

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `action` | PublicAllocate / PublicTransfer / PublicStartAttack / PublicRoll / PublicStopAttack / PublicSkip / PublicEndTurn | yes | -; -; -; -; -; -; - |
| `evaluation` | PublicBoardEvaluation | yes | - |
| `explanation` | string | yes | - |
| `projected_potential` | [integer, integer, integer, integer, integer] / null | no | minItems=5; maxItems=5; - |
| `reason` | string | yes | enum=["allocate", "transfer", "attack", "continue", "stop", "skip", "end_turn"] |
| `strategy_version` | string | yes | - |

### PublicBoardEvaluation

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `actor_id` | string | yes | - |
| `attacks` | array<PublicAttackEvaluation> | yes | - |
| `concentration` | integer | yes | - |
| `countries` | array<PublicCountryObservation> | yes | - |
| `defensive_exposure` | integer | yes | - |
| `participants` | array<PublicParticipantObservation> | yes | - |
| `revision` | integer | yes | - |
| `round` | integer | yes | - |
| `turn_sequence` | integer | yes | - |

### PublicCountryObservation

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `base_soldier_value` | integer | yes | - |
| `id` | string | yes | - |
| `name` | string | yes | - |
| `owner_id` | string | yes | - |
| `soldiers` | integer | yes | - |

### PublicParticipantObservation

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `countries` | integer | yes | - |
| `id` | string | yes | - |
| `kind` | string | yes | enum=["human", "npc"] |
| `reinforcement_income` | integer | yes | - |
| `soldiers` | integer | yes | - |
| `turn_distance` | integer | yes | - |

### PublicAttackEvaluation

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `acceptable` | boolean | yes | - |
| `available` | integer | yes | - |
| `defenders` | integer | yes | - |
| `eliminates` | boolean | yes | - |
| `exposure_cost` | integer | yes | - |
| `income_denial` | integer | yes | - |
| `income_gain` | integer | yes | - |
| `margin` | integer | yes | - |
| `opponent_income` | integer | yes | - |
| `opponent_power_bonus` | integer | yes | - |
| `reward` | integer | yes | - |
| `score` | integer | yes | - |
| `source_id` | string | yes | - |
| `target_id` | string | yes | - |
| `urgency_bonus` | integer | yes | - |
| `wins` | boolean | yes | - |

npc_decision contains strategy_version (current policy balanced-v1), action, reason, explanation, evaluation and optional
five-integer projected_potential. Reasons are allocate, transfer, attack, continue, stop, skip or end_turn.
Evaluation observes all ten countries/participants and candidate attacks, including available/defending force, margin, reward,
elimination/victory opportunities, income gain/denial, exposure, bonuses, score and acceptable.
These are heuristic policy observations; they are not battle results or LLM-generated prose.
Private policy digests and tie-break configuration are omitted by the public model.
Historical/human results can have npc_decision null or omitted.

There is NO dedicated HTTP fast-forward endpoint and no NPC background simulation triggered by GETs.
NpcController.run_until_human is a trusted local helper, not an exposed route.
The owner frontend can implement visible fast-forward with serialized POST /games/{id}/npc-steps calls:
use the returned revision for the next request, display every committed event/decision, shorten presentation delay,
and stop on the human's turn or completed status. A single NPC action can leave the same NPC active for another action.
Pause on errors/429; never skip unshown server moves or generate NPC actions locally.
If the human has been eliminated, do not invent a human turn; remaining NPC play can continue until completed.
Spectators only poll public GET state/events and must never drive NPC POSTs.

Evidence: [backend/app/api/games.py:45](../backend/app/api/games.py#L45), [backend/app/services/npc_service.py:57](../backend/app/services/npc_service.py#L57), [backend/app/engine/npc/strategy.py:40](../backend/app/engine/npc/strategy.py#L40).

### Public NPC action variants

### PublicAllocate

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `allocations` | array<PublicAllocation> | yes | - |
| `type` | string | yes | const="allocate" |

### PublicTransfer

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `amount` | integer | yes | - |
| `source_id` | string | yes | - |
| `target_id` | string | yes | - |
| `type` | string | yes | const="transfer" |

### PublicStartAttack

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `source_id` | string | yes | - |
| `target_id` | string | yes | - |
| `type` | string | yes | const="start_attack" |

### PublicRoll

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `type` | string | yes | const="roll" |

### PublicStopAttack

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `type` | string | yes | const="stop_attack" |

### PublicSkip

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `type` | string | yes | const="skip" |

### PublicEndTurn

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `type` | string | yes | const="end_turn" |

## 7. Complete detail.code catalog and error handling

Phase 4 errors use the following JSON envelope and Cache-Control: no-store.
A 429 additionally carries the HTTP Retry-After header, not a retry_after JSON field.
Legacy saved-game/health and framework/CORS responses have different shapes, described below.

```json
{
  "detail": {
    "code": "revision_conflict"
  }
}
```

| HTTP status | detail.code | Meaning / reachability | Source |
|---|---|---|---|
| 400 | `request_body_unavailable` | Stream/body could not be read. | [backend/app/api/dependencies.py:97](../backend/app/api/dependencies.py#L97) |
| 401 | `authentication_required` | Missing/malformed/expired/idle/revoked/stale session or invalid active account. | [backend/app/repositories/security_repository.py:125](../backend/app/repositories/security_repository.py#L125) |
| 401 | `invalid_credentials` | Generic bad login, unknown/disabled user, or rejected session issuance. | [backend/app/repositories/security_repository.py:104](../backend/app/repositories/security_repository.py#L104) |
| 403 | `csrf_rejected` | Missing, wrong or over-256-character CSRF header on authenticated POST. | [backend/app/api/dependencies.py:46](../backend/app/api/dependencies.py#L46) |
| 403 | `game_access_changed` | Ownership/access binding changed during a guarded action. | [backend/app/repositories/scoped_action_repository.py:20](../backend/app/repositories/scoped_action_repository.py#L20) |
| 403 | `game_not_owned` | No valid access envelope or wrong owner; historical ownerless games cannot be claimed. | [backend/app/models/game_access.py:26](../backend/app/models/game_access.py#L26) |
| 403 | `invalid_human_binding` | Stored access does not bind to the game's human participant. | [backend/app/services/authorized_game_service.py:84](../backend/app/services/authorized_game_service.py#L84) |
| 403 | `origin_rejected` | Missing, duplicate or untrusted POST Origin. | [backend/app/api/dependencies.py:84](../backend/app/api/dependencies.py#L84) |
| 404 | `game_not_found` | Missing/invalid ObjectId for authorized/event paths. | [backend/app/repositories/security_repository.py:188](../backend/app/repositories/security_repository.py#L188) |
| 409 | `action_id_conflict` | Existing action ID has different submitted content. | [backend/app/api/dependencies.py:141](../backend/app/api/dependencies.py#L141) |
| 409 | `creation_id_conflict` | Owner's creation key is already bound to a different setup payload. | [backend/app/repositories/security_repository.py:222](../backend/app/repositories/security_repository.py#L222) |
| 409 | `invalid_game_action` | Wrong actor/phase/action, no active NPC action or other engine illegality. | [backend/app/api/dependencies.py:137](../backend/app/api/dependencies.py#L137) |
| 409 | `revision_conflict` | Stale expected revision/concurrent new action; refetch. | [backend/app/api/dependencies.py:139](../backend/app/api/dependencies.py#L139) |
| 409 | `unsupported_game` | Runtime action service cannot safely adapt the stored state. | [backend/app/api/dependencies.py:143](../backend/app/api/dependencies.py#L143) |
| 409 | `username_unavailable` | Case-insensitive registration collision. | [backend/app/repositories/security_repository.py:93](../backend/app/repositories/security_repository.py#L93) |
| 413 | `request_too_large` | Phase 4 POST streamed body exceeds configured cap. | [backend/app/api/dependencies.py:93](../backend/app/api/dependencies.py#L93) |
| 415 | `json_required` | Wrong/missing Content-Type for a nonempty-logout/normal POST body. | [backend/app/api/dependencies.py:102](../backend/app/api/dependencies.py#L102) |
| 422 | `invalid_event_cursor` | Defensive service event cursor/page validation; HTTP constraints normally reject first. | [backend/app/services/authorized_game_service.py:124](../backend/app/services/authorized_game_service.py#L124) |
| 422 | `invalid_event_page` | Defensive repository event bounds; HTTP constraints normally reject first. | [backend/app/repositories/security_repository.py:299](../backend/app/repositories/security_repository.py#L299) |
| 422 | `invalid_game_cursor` | Defensive ObjectId cursor parsing; HTTP pattern normally rejects first. | [backend/app/repositories/security_repository.py:266](../backend/app/repositories/security_repository.py#L266) |
| 422 | `invalid_game_filter` | Defensive owner-list filter/page validation; HTTP constraints normally reject first. | [backend/app/repositories/security_repository.py:254](../backend/app/repositories/security_repository.py#L254) |
| 422 | `invalid_idempotency_key` | Defensive service key validation; HTTP header constraints normally reject first. | [backend/app/services/authorized_game_service.py:57](../backend/app/services/authorized_game_service.py#L57) |
| 422 | `invalid_request` | Sanitized Phase 4 request/header/query/model validation failure. | [backend/app/api/dependencies.py:132](../backend/app/api/dependencies.py#L132) |
| 422 | `invalid_revision` | Defensive NPC revision validation; NpcStepRequest normally rejects first. | [backend/app/services/authorized_game_service.py:99](../backend/app/services/authorized_game_service.py#L99) |
| 422 | `password_blocklisted` | Registration password hits local common/repetition/username policy. | [backend/app/security/passwords.py:28](../backend/app/security/passwords.py#L28) |
| 422 | `password_policy` | Registration password fails normalized length/NUL rules; request model can reject NUL earlier. | [backend/app/security/passwords.py:25](../backend/app/security/passwords.py#L25) |
| 422 | `reserved_action_id` | New human submission uses the server-reserved npc- prefix. | [backend/app/services/authorized_game_service.py:91](../backend/app/services/authorized_game_service.py#L91) |
| 429 | `rate_limited` | Shared window exhausted; honor Retry-After. | [backend/app/services/auth_service.py:28](../backend/app/services/auth_service.py#L28) |
| 503 | `authentication_busy` | Local Argon2 concurrency slots unavailable. | [backend/app/security/passwords.py:42](../backend/app/security/passwords.py#L42) |
| 503 | `authentication_disabled` | Authentication write gate is closed; POST middleware checks it first. | [backend/app/api/dependencies.py:81](../backend/app/api/dependencies.py#L81) |
| 503 | `gameplay_writes_disabled` | Gameplay gate is closed after applicable prerequisites. | [backend/app/api/dependencies.py:148](../backend/app/api/dependencies.py#L148) |
| 503 | `persistence_unavailable` | Repository operation/transaction failed; commit outcome can be uncertain. | [backend/app/repositories/security_repository.py:56](../backend/app/repositories/security_repository.py#L56) |
| 503 | `phase4_disabled` | No installed Phase 4 context; this is the export-only app's state. | [backend/app/api/dependencies.py:34](../backend/app/api/dependencies.py#L34) |
| 503 | `security_index_verification_unavailable` | Index metadata retrieval failed. | [backend/app/repositories/phase4_indexes.py:61](../backend/app/repositories/phase4_indexes.py#L61) |
| 503 | `security_indexes_not_ready` | A required index is missing or semantically incompatible. | [backend/app/repositories/phase4_indexes.py:59](../backend/app/repositories/phase4_indexes.py#L59) |
| 503 | `service_unavailable` | Sanitized driver/model/persistence or unexpected Phase 4 failure. | [backend/app/api/dependencies.py:154](../backend/app/api/dependencies.py#L154) |

Catalog size: 36 distinct (HTTP status, detail.code) pairs found in committed runtime code, including the four dynamic engine-error mappings.

This is the full source-defined vocabulary, not a promise that every defensive code can be reached through a valid HTTP route.
Header/body/query validators can return invalid_request before a service-specific defensive guard runs.
ConfigurationError/StartupError/provisioning tool categories are startup/CLI diagnostics, not additional frontend detail.code values.
Arbitrary injected-store errors or all infrastructure failure paths cannot be exhaustively verified offline.

### Legacy and framework errors

| Source | Status | Body |
|---|---|---|
| GET /health | 503 | {"detail":"MongoDB Atlas connection failed"} |
| GET /games/{id} | 404 | {"detail":"Game not found"} |
| GET /games/{id} | 503 | {"detail":"Database temporarily unavailable"} |
| GET /games/{id} | 503 | {"detail":"Saved game temporarily unavailable"} |
| Framework routing | 404 / 405 | Usually {"detail":"Not Found"} / {"detail":"Method Not Allowed"}; no application code. |
| Phase 4 request validation | 422 | {"detail":{"code":"invalid_request"}}; stock OpenAPI detail[] is not the runtime envelope here. |
| Trusted CORS preflight | 200 / 400 | text/plain OK or a disallowed-method/header message, not JSON. |
| Unexpected framework/response-started failure | 500 / interrupted response | No guaranteed detail.code; exact transport behavior UNVERIFIED offline. |

### Rate limits and retry handling

Defaults: registration 5/IP/hour; login 30/IP/300 seconds plus 10/account/900 seconds; gameplay 120/account/game/60 seconds
(creation uses the separate create scope). Failed/repeated attempts that reach those counters also count.
AuthService returns remaining seconds in the rejected window: seconds - floor(now_timestamp) % seconds.
Gameplay returns 60 - floor(now_timestamp) % 60. The response helper sets Retry-After to retry_after or 60 if unspecified.
Windows are shared in MongoDB and are not dependent on the TTL cleanup schedule.
Client IP comes from request.client.host; the application does not directly trust arbitrary forwarded headers.
Actual Render proxy interpretation and live configured limits are UNVERIFIED here.

Frontend handling:
- 401: clear in-memory user/CSRF state and ask for login; show generic credential failures.
- 403: do not retry writes or infer permission from a visible button. Distinguish origin/CSRF configuration from owner denial; an accessible public board is not write permission.
- 409: refetch the full board and relevant events, reconcile revisions, and obtain a new user intent where appropriate. Do not blindly relabel an old action with a new ID.
- 429: pause mutation/fast-forward queues for Retry-After, then allow a bounded retry. Avoid retry storms.
- 503: distinguish disabled/operator-readiness codes from transient busy/persistence failures. A persistence failure may hide a committed action:
  retry only the identical action ID+payload, NPC expected_revision, or creation key+payload. Never create a fresh mutation identity just because the response was lost.
- 400/413/415/422: fix the request; do not retry unchanged invalid input.
For duplicate/old receipt responses, an older returned state must not rewind a newer local board: refetch the latest public state.

## 8. Exact call-order flows

These are future, explicitly authorized application flows. No such request was executed during this documentation task.
All requests use the chosen same-origin HTTPS API base. The browser supplies Origin and Cookie; the API client supplies the named
application headers. Always use credentials: include for the authenticated flow. Never put credentials/tokens in URLs or logs.

| Step | Request | Headers/body | Expected behavior |
|---|---|---|---|
| 1 | GET /countries | No body; public | Load eligible starting_country_id values. |
| 2 | POST /auth/register | O + J; {username,password} | 201 UserPublic; not logged in. |
| 3 | POST /auth/login | O + J; {username,password}; credentials include | 200 {user,expires_at}; browser stores HttpOnly cookie. |
| 4 | GET /auth/me (optional restoration check) | Browser Cookie; no body | 200 UserPublic; authenticated GET may write session fences. |
| 5 | GET /auth/csrf | Browser Cookie; no body | 200 {csrf_token}; store only in memory. |
| 6 | POST /games | O + J + C + I + browser Cookie; {game_name,starting_country_id} | 201 full game; retain _id and exact creation key/body. |
| 7 | Determine active participant | Read turn_order[current_turn] and players[].kind | Creation can select an NPC first; do not assume human. |
| 8 | POST /games/{id}/actions (human turn only) | O + J + C + Cookie; {action_id,expected_revision,action} | Replace state with result.state, display result.events; for this fixture use skip at revision 0. |
| 9 | POST /games/{id}/npc-steps (NPC turn only) | O + J + C + Cookie; {expected_revision: latest revision} | One NPC action; display decision/events. Repeat conditionally, never over a human turn. |
| 10 | GET /games/{id} and GET /games/{id}/events?after_revision=lastSeen&limit=20 | Public GETs; no CSRF; keep page cursor | Reload authoritative state and catch up committed events. |
| 11 | Reload browser / resume | GET /auth/me -> GET /auth/csrf -> GET /me/games -> GET /games/{id} -> events | Cookie persists; CSRF memory does not. Recover own games via owner-scoped pages. |
| 12 | POST /auth/logout | O + C + Cookie; empty body (J optional) | 204; cookie cleared/current session revoked; clear user/CSRF and stop owner queues. |

Use real current revisions, not the documentation's example numbers. If a human action starts a battle, continue with roll/stop
and legal turn completion before requesting NPC steps. Allocate in allocating, choose/skip in deciding, roll/stop in attacking,
transfer/end_turn in post_attack. Stop all mutation loops on completed/finished, revocation, owner denial or disabled gates.
Public reads never advance the game. Resuming must not create a replacement game or reset existing state.

### Anonymous spectator flow

1. Open the shared frontend game URL and take its game_id.
2. GET /games/{id} without a session or CSRF; render the full public board.
3. GET /games/{id}/events?after_revision=0&limit=20; page using next_after_revision while has_more.
4. Poll the public state/events for committed updates, deduplicating by revision. The event page is not itself a board snapshot.
5. Show state, dice/events and available NPC explanations. Do not call register/login, human actions or npc-steps merely to view.
6. A spectator can separately register/login to create their own game. Logged-in status alone does not confer ownership of the shared game.
No WebSocket/SSE subscription endpoint or dedicated fast-forward endpoint exists in this commit.

## 9. Sessions, cookie, CSRF, origins and hosting

Cookie: __Host-geopolitics_session; Secure; HttpOnly; SameSite=Lax; Path=/; no Domain.
Login sets Max-Age/Expires from the absolute lifetime (default 43,200 seconds / 12 hours).
Default idle expiry is 1,800 seconds / 30 minutes. Server checks expiry, idle activity, revocation, account status and auth_version
independently of MongoDB TTL deletion. Only a SHA-256 token verifier is stored; the cookie is an opaque 43-character URL-safe token,
not a JWT. Login JSON does not expose it. Do not add a Bearer Authorization scheme or invent a frontend signing secret.
A presented prior same-account session is revoked on successful login rotation; other existing sessions are not globally logged out.
Logout revokes the current session and clears its cookie.

Illustrative cookie header; placeholder is not a real credential:

```http
Set-Cookie: __Host-geopolitics_session=<opaque-session-token>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=43200
```

Obtain CSRF from GET /auth/csrf after login/restoration, keep it in memory only, and send X-CSRF-Token on authenticated mutations.
The server compares it against the current session token, rejecting missing or over-256-character supplied headers.
Do not store the cookie/CSRF in localStorage, sessionStorage, IndexedDB, URLs, analytics or console output.
JavaScript cannot read/set the HttpOnly cookie; let the browser manage it. Refresh CSRF after a new login, not by inventing a value.
Authenticated GET /auth/me, /auth/csrf and /me/games call authenticate(touch=True), which updates session/user authorization fences
transactionally. They are not operationally read-only when authentication is active; public game/catalog/events reads do not touch sessions.

Public anonymous access does not grant arbitrary third-party JavaScript CORS access; shared links should open the approved frontend origin.
The frontend deployment plan requires same-origin HTTPS unless a separately reviewed same-site arrangement is approved.
The backend itself supports exact configured trusted origins, not only same-origin. Do not assume arbitrary cross-site hosting works:
credentials: include and CORS do not override SameSite=Lax. Keep the cookie protections intact.
PHASE4_TRUSTED_ORIGINS is a JSON array, defaults to [], and must contain distinct exact origins with no wildcard, path, trailing slash,
credentials, query or fragment. Non-loopback origins require HTTPS; loopback HTTP is only a configuration allowance, not proof
that a browser will accept this secure-cookie development topology.
CORS only permits the exact trusted origin, credentials, GET/POST, and Content-Type/X-CSRF-Token/Idempotency-Key.
No expose_headers setting is configured, so separate-origin JavaScript must not assume Retry-After is exposed to fetch; same-origin requests can read it.
Auth activation with an empty trusted-origin list is rejected; gameplay requires auth. No session-signing secret variable exists.

Evidence: [backend/app/api/auth.py:15](../backend/app/api/auth.py#L15), [backend/app/security/config.py:6](../backend/app/security/config.py#L6), [backend/app/security/environment.py:70](../backend/app/security/environment.py#L70), [backend/app/main.py:16](../backend/app/main.py#L16), [backend/app/repositories/security_repository.py:118](../backend/app/repositories/security_repository.py#L118).

## 10. API gaps and UCT requirement support

| Question | Verified committed-code answer | Evidence |
|---|---|---|
| AI battle commentary endpoint or field, including GroqCloud? | NO. No commentary route/field/provider integration is present in the committed runtime API. NPC explanations are deterministic policy templates. External/uncommitted GroqCloud work is UNVERIFIED; no account/network inspection was attempted. | [backend/app/main.py:37](../backend/app/main.py#L37); [backend/app/api/games.py:19](../backend/app/api/games.py#L19); [backend/app/models/game_api.py:183](../backend/app/models/game_api.py#L183); [backend/app/models/game_api.py:174](../backend/app/models/game_api.py#L174); [backend/app/engine/npc/explanations.py:7](../backend/app/engine/npc/explanations.py#L7) |
| Country catalog endpoint? | YES: GET /countries returns population_snapshot and all eligible catalog items (id/name/population/base_soldier_value). | [backend/app/api/countries.py:17](../backend/app/api/countries.py#L17) |
| Public spectator full state or only events? | FULL STATE at GET /games/{game_id}, plus committed history at GET /games/{game_id}/events. Neither requires a session. Event pages contain no full-state snapshot. | [backend/app/main.py:66](../backend/app/main.py#L66); [backend/app/api/games.py:50](../backend/app/api/games.py#L50) |
| Delete or rename a game? | NO DELETE/PUT/PATCH route and no rename endpoint. Do not build these controls against an invented API. The brief does not explicitly require them. | [backend/app/main.py:37](../backend/app/main.py#L37); [backend/app/api/games.py:12](../backend/app/api/games.py#L12) |
| Dedicated fast-forward endpoint? | NO. One-action owner-only npc-steps supports a visible serialized frontend loop; run_until_human is not exposed over HTTP. | [backend/app/api/games.py:45](../backend/app/api/games.py#L45); [backend/app/services/npc_service.py:57](../backend/app/services/npc_service.py#L57) |
| Live shared-view transport? | No WebSocket/SSE endpoint is registered. Public GET polling is supported. Live display and visible fast-forward still require frontend work. | [backend/app/main.py:37](../backend/app/main.py#L37); [backend/app/api/games.py:51](../backend/app/api/games.py#L51) |
| What mandatory rubric feature has no API support? | Dynamic LLM/AI battle commentary (brief p.4; documented G17) is missing. Existing NPC explanations do not supply battle narration. Visual battles/always-visible soldiers/navigation/fast-forward remain UI work supported by state/events/step APIs, not proof that a new bulk endpoint is needed. | [backend/docs/REQUIREMENTS.md:21](../backend/docs/REQUIREMENTS.md#L21); [backend/app/models/game_api.py:109](../backend/app/models/game_api.py#L109); [backend/app/api/games.py:45](../backend/app/api/games.py#L45) |
| Authentication/owner-play support? | Routes/services exist but gates default closed; live browser acceptance/production application-account readiness remains UNVERIFIED here. Ownerless historical documents have no claiming endpoint. | [backend/app/services/authorized_game_service.py:37](../backend/app/services/authorized_game_service.py#L37); [backend/app/models/game_access.py:20](../backend/app/models/game_access.py#L20) |
| Operational readiness endpoint or owner-capability field? | No Phase 4 readiness endpoint and no public is_owner/can_act field. /health only pings MongoDB; startup readiness is an internal snapshot. Owner-list membership can inform UI, never replace server authorization. | [backend/app/main.py:56](../backend/app/main.py#L56); [backend/app/startup.py:26](../backend/app/startup.py#L26); [backend/app/models/game_api.py:44](../backend/app/models/game_api.py#L44) |
| Schema completeness? | Several response bodies and all cookie/Origin/CSRF/error/gate controls need this source supplement; exported OpenAPI has no securitySchemes. Its stock Phase 4 422 schema differs from the installed handler. | [backend/app/api/dependencies.py:124](../backend/app/api/dependencies.py#L124); [backend/app/api/auth.py:15](../backend/app/api/auth.py#L15) |

Offline search evidence: git grep -l -i -e groq -e groqcloud -e commentary HEAD -- backend/app backend/requirements.txt
returned no committed runtime/dependency matches. This is absence evidence for this commit, not a claim about an external GroqCloud
project or another checkout. No commentary field exists in PublicGame, PublicActionResult, PublicGameEvent, PublicCommittedAction or PublicNpcDecision.

## 11. Frontend rules

- Never compute dice outcomes, authoritative ownership, casualties, reinforcement results or NPC policy decisions in the client.
  Display the server's state/events/evidence. Client validation only improves UX; it never authorizes a move.
- Replace local game state with the server response after every successful mutation. Keep route game_id separately because action state can omit _id.
  Serialize mutations; if an old receipt response is behind the current revision, refetch rather than rewind a newer board.
- Refetch on 409. Preserve exact uncertain-retry identities and payloads; do not silently generate another action/creation ID to force a second write.
- Keep CSRF only in memory. Let the browser manage the HttpOnly cookie. Clear user/CSRF/mutation queues on logout or expired authentication.
- Never call fetch outside src/api/. Put endpoint construction, credentials, JSON/error handling, CSRF/Idempotency-Key headers and retry policy there.
  This is a frontend project rule; the Python backend does not enforce frontend source-directory boundaries.
- Do not derive account ownership from the game-local human ID. Use authenticated owner-list membership for controls and enforce server responses.
- Hide/disable controls for spectators and unsupported historical states. Public links never trigger NPC writes.
- Keep visible event/decision ordering during normal play and fast-forward; paginate/deduplicate by committed revision.
- Respect phase-specific actions and the configured rate limits; pause on 429/503 instead of issuing parallel mutations.
- Render server explanations/commentary as text. Do not inject arbitrary HTML from API strings.
- Do not put MongoDB/provider credentials, raw session values or sensitive headers into VITE_* settings, source files, browser storage or logs.
- Do not call production mutation routes until their separate activation/acceptance authorization exists.

## 12. Explicit UNVERIFIED items and verification boundary

- Current Render process environment, exact deployed runtime instance, installed Phase 4 context/readiness, application-account privileges and live write-gate values were not read.
  The source defaults and the user's previously reported closed-gate state are distinct from a fresh deployment observation.
- Browser cookie acceptance, HTTPS/proxy/client-IP behavior, CORS behavior for the eventual frontend origin and documentation CDN availability were not exercised.
- Live HTTP status/error reachability under every infrastructure failure, interrupted response or custom injected store is not exhaustively verified by static inspection.
- Any external, ignored/uncommitted or other-branch GroqCloud configuration/work is UNVERIFIED; only committed backend runtime/dependencies were searched.
- The snapshot's current online Worldometer freshness and live payload timestamp formatting were not fetched.
- No current MongoDB records, installed metadata, backups, Atlas/Render settings, provider services or network endpoints were accessed by this task.
  Prior D2 evidence is historical context and was not repeated.
No backend code/tests/environment/write flags/indexes/validators/backups were changed. Only the two requested documentation files were written.

## 13. Remaining exact OpenAPI component definitions

### Credentials

Unknown input properties are forbidden by this component.

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `password` | string | yes | minLength=1; maxLength=128; format="password"; writeOnly=true |
| `username` | string | yes | minLength=3; maxLength=32; pattern="^[a-zA-Z0-9_]+$" |

### UserPublic

Unknown input properties are forbidden by this component.

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `id` | string | yes | - |
| `username` | string | yes | - |

### GameSetupRequest

Unknown input properties are forbidden by this component.

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `game_name` | string | yes | minLength=1; maxLength=100 |
| `starting_country_id` | string | yes | minLength=1 |

### HTTPValidationError

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `detail` | array<ValidationError> | no | - |

### ValidationError

| Field | Type | Required in schema | Constraints/default |
|---|---|---|---|
| `ctx` | object | no | - |
| `input` | unspecified | no | - |
| `loc` | array<string / integer> | yes | - |
| `msg` | string | yes | - |
| `type` | string | yes | - |
