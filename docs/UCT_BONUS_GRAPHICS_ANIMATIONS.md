# UCT selected bonus - Graphics and Animations

The selected bonus is **Graphics and Animations**. Analytics was rejected and is
not implemented as a bonus. This document records existing work; it does not
claim examiner-awarded marks or introduce another gameplay feature.

## Official basis and evidence boundary

The official UCT INF4001N 2027 brief, page 5, lists adding graphics and animations
to beautify the game as a bonus idea. That page was freshly rendered and visually
inspected during Stage 8.5. The official 2027 marksheet (one page, 14 criteria)
was inspected in the preceding UI stages; no bonus weighting is inferred here.
Source files: the exact-name official brief and marksheet in the user's Downloads.

The approved Design System V1 controls the parchment/forest palette and reusable
components. Human-approved Flag Poster Option 4 controls the result composition.
Motion is presentation of authoritative state; it never rolls dice, awards
soldiers, changes turns or determines victory. Most features below were already
implemented in Stages 2-7 and are preserved by Stage 8.5.

## Implemented graphics and motion

Paths below are relative to `frontend/`.

| Feature | Implementation | Experience and graphics evidence | Isolated reproduction and tests |
| --- | --- | --- | --- |
| Inline interactive SVG atlas | `src/map/AtlasMap.tsx`, `src/map/mapData.generated.json` | 470 retained paths; 195 canonical countries, including seven verified fallback locations; no HTML/SVG injection | `human`; `tests/atlas.test.mjs`, `tests/game-board.test.mjs` |
| Ownership colours | `src/map/layout.ts` factionMap; `AtlasMap.tsx`; `src/ui/tokens.css` | Stable participant colours tint held country fragments; text and ring styles supplement colour | `human`, `conquest`; atlas and board tests |
| Soldier markers and readable country roster | `AtlasMap.tsx`, `src/map/atlas.css`, `src/ui/components.tsx` | Country markers, current-owner rings, exact accessible numbers and roster parity; large counts stay readable | `human`, `country-long`; atlas and country-info tests |
| Selected-country feedback | `AtlasMap.tsx`, `atlas.css`, `src/components/GameBoard.tsx` | Focus/selection outline and brief 180 ms emphasis; Stage 8.5 adds an informational country card, not an action | Select a token or roster row; `tests/country-info.test.mjs` |
| Attack paths | `AtlasMap.tsx`, `atlas.css` | Dashed line joins the actual battle countries; 180 ms reveal. Geography imposes no attack restriction | `attacking`; atlas and board tests |
| Animated dice | `src/components/BattleExchange.tsx`, `battle.css`, `battle-view.ts` | Approximately 650 ms saved-exchange reveal; original paired order and all dice retained, including more than three | `battle-six`, `battle-many`; use Preview one newly committed exchange; `tests/battle.test.mjs` |
| Dice-pair comparison | `BattleExchange.tsx`, `battle-view.ts` | Pip faces, pair order, tie/loss labels and committed casualty totals; no generated combat values | `battle-six`, `battle-ties`; battle tests |
| Conquest feedback | `GameBoard.tsx`, `presentation.ts`, `atlas.css` | Newly observed confirmed ownership change can emphasize the captured shape for 650 ms; historical loads do not celebrate | `human`, Preview confirmed conquest transition; `tests/presentation.test.mjs` |
| Turn transitions | `GameBoard.tsx`, `src/components/game-shell.css`, `src/ui/components.tsx` | Saved turn order and current-player emphasis, with 160 ms arrival treatment | `human`, `npc`; board/presentation tests |
| Button and valid-selection feedback | `src/ui/components.css`, `src/components/controls.css` | Restrained 140-160 ms interaction/ready-state feedback; disabled reasons, touch targets and keyboard focus remain | Choose attack source/target in `human`; `tests/action-panel.test.mjs`, `tests/ui-components.test.mjs` |
| Flag Poster result | `src/components/ResultPoster.tsx`, `result-poster.css`, `presentation.ts`, `src/flags/` | Winning home-country flag dominates; actual held-country count, winner and saved final data; live completion reveal only | `completed`, `npc-victory`, `victory-nepal`; presentation tests |
| Reduced motion | `components.css`, `atlas.css`, `battle.css`, `game-shell.css`, `controls.css`, `result-poster.css` | Removes nonessential transforms/transitions/animation; committed results and controls remain available | Browser reduced-motion emulation; battle, presentation, UI and sound tests |

The atlas's horizontal map region on narrow screens is intentional. It has a
keyboard-accessible alternative roster and all-country information selector;
document-level overflow is not required. Country cards remain inline outside the
map's scroller, horizontally aligned to the inspected anchor on wide screens.

## Reproduce without production

From the repository root:

```powershell
Set-Location frontend
node scripts/preview-components.mjs --board
```

Open **http://127.0.0.1:5175/**. The labelled fixture selector changes synthetic
states. In `human`, local attack selectors, the new country inspector and existing
presentation-transition buttons make no gameplay request. Battle fixtures expose
Preview one newly committed exchange for animation. Stop with Ctrl+C.

Automated screenshots: `node scripts/review-stage8-5.mjs` from `frontend/`.
The runner uses a separate temporary Chrome profile and loopback fixtures,
blocks nonlocal/non-GET page traffic, mutes the browser and closes its own server.
It does not attach to the existing production tab.

## Rendered evidence and limits

Stage 8.5 captured 14 states at 1440px, 768px and 375px: 42 combinations and
84 PNGs. Contact sheets and representative full-resolution details were inspected.
Artifacts: `output/ui-stage8-5/`, especially:

- [Atlas](../output/ui-stage8-5/human-1440-screen.png)
- [Committed dice](../output/ui-stage8-5/dice-768-detail.png)
- [Conquest](../output/ui-stage8-5/conquest-375-detail.png)
- [Flag Poster victory](../output/ui-stage8-5/victory-1440-detail.png)
- [NPC result](../output/ui-stage8-5/defeat-375-detail.png)
- [Country information](../output/ui-stage8-5/country-long-375-detail.png)
- [Machine findings](../output/ui-stage8-5/review.json)

Screenshots show rendered layouts, not the complete temporal animation. Existing
animation/identity tests and the manual fixture buttons complement them. No new
production/full-game acceptance is claimed. System font fallbacks were used in
the offline preview; this is not an exact-font visual certification. Audio is
optional polish and is documented separately in [AUDIO_ASSETS.md](AUDIO_ASSETS.md).

Mandatory gameplay, authentication, spectator access and GroqCloud narration
remain separate requirements. The bonus does not replace them. Full-game and
round-two production acceptance and final submission evidence remain human gates.
