# Frontend UI refresh release record

6 November 2026 · Geopolitics · UCT INF4001N 2027

The cumulative frontend refresh is frozen for a local Git commit on `ui-redesign`.
This record does not authorize a production deployment. Remote push is held at
the owner's explicit request pending Vercel/Render deployment-setting verification.
The baseline is `f990946660ce6de4055643829bc95753bc0c2a82`; the final commit can be
identified from Git history without embedding a self-referential commit hash here.

## Included work

- Compact responsive header/navigation, sound/status controls and accessible focus.
- Current-turn HUD, prominent atlas, country inspection and direct gameplay anchors.
- Always-visible confirmed battle results and original saved rival reasoning.
- Battle/Chronicle layout, complete ordered dice and exact numerical soldier labels.
- Concise recovery presentation with original confirmation/retry protections.
- Cream/forest editorial landing, accurate atlas, labelled static interface preview,
  Four Orders, spectator entry, strategy icons, slogan and attributed epigraph.
- One outlined header login action; Begin campaign selects the original registration
  form and header Log in selects login mode without submitting or replacing it.
- Sound-popup fit, rounded presentation, keyboard access and preference preservation.

## Verification and its limits

The isolated Git-content candidate passes **411 frontend tests**, with zero
failures, cancellations or skips. TypeScript and the production build pass.
Offline compatibility verifies 43 OpenAPI components. Integrity checks verify
470 geographic paths, all 195 countries, seven map fallbacks, 17 aliases,
181 supported capitals and 18 runtime sound files/mappings/hashes.

Fresh local browser checks pass **142 landing/header assertions**, **131 gameplay
assertions** and **104 sound-popup assertions**, with zero failures. They cover
login/registration entry, mobile Menu, spectator input, gameplay HUD, confirmed
battles, original saved reasoning, Chronicle, recovery and sound settings at
1440px, 768px, 375px and native 200% Chrome page zoom. They use isolated profiles,
loopback fixtures and blocked external requests. They do not submit real
credentials or gameplay.

The initial Windows archive export converted LF files to CRLF and failed six
tests plus contract/map/reference checks. That failed artifact was retained and
was not counted as a pass. The corrected export disables line-ending conversion
for that archive command only and verifies protected files against exact Git
blob bytes. No contract, generated data, SVG, source checksum or assertion was
changed to clear the failure. The Git-faithful candidate passes the checks above.

The existing Vite chunk-size warning remains. Other browsers, manual screen-reader
operation, audible sound quality, production web-font rendering, real login,
registration, spectator access and connected gameplay were not newly verified.
Original sound-source distribution rights retain the qualifications in
[audio provenance](AUDIO_ASSETS.md); runtime hash checks do not establish rights.

## Protection and packaging

The release delta excludes backend code, API client/contracts, game controller,
sound playback engine, geometry/data, private original audio, environment files,
temporary screenshots, caches and historical local audit documents. The approved
static campaign-preview image is explicitly labelled an offline demonstration.
Development fixture changes are isolated from the production import graph.

The optimized backend `005a1e7` remains in its separately deployed branch. This UI
commit neither merges that branch nor changes backend files. Any future merge
must retain that backend optimization and the existing frontend recovery fix;
the two branches have different histories and must not overwrite one another.

The local `/auth/me` proxy refusal is consistent with the documented loopback
backend target at `127.0.0.1:8000` having no listener. No production database was
connected and no proxy, authentication or environment setting was changed.

## Release gate

Before a separately authorized push, verify the current Vercel Production Branch,
custom production mappings and Render deploy branch/Auto Deploy settings. A Ready
redeploy attached to the public domain does not establish automatic branch behavior.
Do not push, merge, promote or deploy on the strength of local fixture checks.
The owner will review the commit and deployment risk separately.
