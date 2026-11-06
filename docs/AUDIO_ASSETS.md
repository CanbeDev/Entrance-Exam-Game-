# Stage 8.5 - Audio inventory and mapping

Date: 2026-11-03. Reduced Stage 8.5 scope; provenance updated after human review.

## Provenance and attribution

The reviewer confirms that all 19 originals were generated with **ElevenLabs on
the Free plan** for this non-commercial university entrance examination project.
This is human-reported provenance, not an inspected account/licence record.

The Audio Credits section exists once in `frontend/README.md`, with an ElevenLabs
link and the Free-plan/non-commercial statement. It is absent from the root
README. No duplicate credit was added. The provider's publication guidance specifies a title
credit containing `elevenlabs.io` or `11.ai` for Free-plan output.
See [ElevenLabs publication guidance](https://elevenlabs.io/docs/help-center/legal/can-i-publish-the-content-i-generate-on-the-platform).

**Human packaging/risk decision accepted, 2026-11-03.** The owner explicitly
accepts proceeding with the existing audio for this non-commercial project and
selects the 18 prepared gameplay clips for the public release, with all 19 originals
kept local. This is risk acceptance, not independently verified ElevenLabs permission.
No new subscription, regenerated audio or duplicate credit is needed.

Sound Effects Exhibit 4 permits
incorporation into games subject to its terms, while restricting standalone files,
samples and sound collections. It does not establish that this project's public
GitHub MP3s or directly retrievable game asset URLs are permitted. Attribution
alone is not clearance. The accepted human decision does not imply a legal
finding about these distribution channels; no permission guarantee is inferred.
See [ElevenCreative Sound Effects terms, Exhibit 4](https://elevenlabs.io/creative-terms).

All 19 original user-supplied files remain unchanged in `frontend/public/assets/audio/`.
They are MP3; installed Chrome decoded all 19 successfully into disconnected
OfflineAudioContext buffers (44,100 Hz, stereo). Durations below are decoded
sample lengths, not estimates from file size. Native local playback also loaded
successfully after explicit enablement; Chrome was muted. This is not an audible
quality/listening review.

| Original filename | Bytes | Decoded duration | Mapped event |
| --- | ---: | ---: | --- |
| `2._Your_soldiers_are_#3-1793668474509.mp3` | 73,197 | 3.000 s | attackerLoss |
| `Allocate_reinforceme_#2-1793668652676.mp3` | 36,909 | 1.480 s | allocate |
| `Attack_Low_war-drum__#1-1793668282761.mp3` | 73,197 | 3.000 s | attack |
| `Confirm_country_choi_#1-1793668213461.mp3` | 49,581 | 2.000 s | confirm |
| `Conquer_a_country_Sh_#4-1793668563611.mp3` | 49,581 | 2.000 s | conquer |
| `Dice_tie_Neutral_woo_#2-1793668515789.mp3` | 13,293 | 0.486 s | tie |
| `End_turn_Paper_turnp_#1-1793668726970.mp3` | 36,909 | 1.480 s | endTurn |
| `Enemy_loses_soldiers_#4-1793668430006.mp3` | 49,581 | 2.000 s | defenderLoss |
| `Error_Gentle_two-ton_#3-1793669060770.mp3` | 49,581 | 2.000 s | error |
| `Error_Gentle_two-ton_#4-1793669030910.mp3` | 49,581 | 2.000 s | Unused error alternative |
| `Heavy_wooden_dice_ro_#1-1793667977040.mp3` | 97,389 | 4.000 s | dice |
| `Lose_the_game_Somber_#1-1793668958052.mp3` | 73,197 | 3.000 s | defeat |
| `NPC_Step_Quiet_clock_#4-1793668781417.mp3` | 13,293 | 0.486 s | npc |
| `Pause_Soft_mechanica_#1-1793668868441.mp3` | 49,581 | 2.000 s | pause |
| `Select_a_country_Sof_#3-1793668132463.mp3` | 13,293 | 0.486 s | select |
| `Start_fast-forward_S_#1-1793668839457.mp3` | 49,581 | 2.000 s | fast |
| `Start_new_campaign_S_#3-1793668080452.mp3` | 97,389 | 4.000 s | campaign |
| `Transfer_soldiers_So_#1-1793668611702.mp3` | 97,389 | 4.000 s | transfer |
| `Win_the_game_Full_vi_#2-1793668917760.mp3` | 97,389 | 4.000 s | victory |

No byte-identical original duplicates were found. The two Error clips are
alternatives; #3 is selected and #4 remains unused. Mapping follows the supplied
filenames and intended categories; the human should audition the clips for tone,
loudness and suitability. Provenance is now **ElevenLabs Free plan, confirmed by
the reviewer**. Distribution permission for the proposed channels remains
unverified; no licence was invented. Panel audibility was separately confirmed by
the human and does not resolve distribution rights.

## Portable runtime files

The first browser check returned HTTP 404 for an escaped original filename
containing a hash character. Rather than rename or alter originals, the offline
`scripts/prepare-sound-assets.mjs` creates 18 byte-identical runtime copies in
`frontend/public/assets/sounds/`. Each has a portable event name such as
`dice.mp3`. The typed `src/sound/assets.ts` records exact original filenames;
`sounds/manifest.json` records source, runtime path, byte count and SHA-256.
The alternate Error clip is not copied. No audio bytes enter JavaScript.

From `frontend/`, the public verification needs only the reviewed runtime files:

```powershell
npm.cmd run check:sounds
npm.cmd test
```

The public check requires exactly 18 mappings, expected portable paths, no duplicate
or unexpected entries/files, exact manifest sizes and SHA-256 values. It proves
runtime integrity against the reviewed manifest, not original-source equality.

For explicit private-source verification, supply the 19 exact originals privately
at `frontend/public/assets/audio/`, then run:

```powershell
npm.cmd run test:sound-sources
```

This profile verifies all 19 source names, all 18 byte-identical original/runtime
comparisons and the unused alternate's hash, then runs the preparation manifest
consistency check. Missing originals fail the prerequisite; they are not silently
skipped or counted as verified. `prepare-sound-assets.mjs --check` remains the
private comparison command. The original source-specific regression was moved to
`tests/private/sound-sources.test.mjs`; public tests do not require that directory's
MP3 inputs. No original-source coverage was dropped.

Use `prepare-sound-assets.mjs` without `--check` only to regenerate copies after
an approved source change; this release did not regenerate or alter any audio.
The runtime copies and manifest add 1,025,021 public-asset bytes. In the current
local worktree, Vite also copies the originals because they remain under public/.
The updated release proposal keeps originals local and selects only the prepared
gameplay assets, conditionally on distribution approval. Do not upload a build
from this dirty worktree as though the originals had been excluded. No original was removed,
converted, normalized, truncated or overwritten. No OneDrive/Vite EBUSY error was
observed during the baseline/final builds or isolated previews; this does not
prove the watcher can never encounter a future file lock.

Runtime paths use only `/assets/sounds/<event>.mp3`; original filenames are
mapping/provenance data, not browser media URLs. Use a separate private verification
checkout for the source profile. Deployment must use the exact clean Git-content
package without the originals; never upload a private-overlay directory or its
dist. The local audit records the separate public and private results and exclusions.

The existing generated manifest's legacy provenance string and generator were
left byte-identical so their drift contract stays intact. Their recorded hashes
are useful integrity evidence, not distribution permission. This document records
the newly supplied provenance; no runtime/source/script change is authorized here.

## Trigger policy

- `select`: intentional map/roster inspection; `confirm`: chosen starting country.
- `fast` and `pause`: existing accepted local playback controls; no success claim.
- `campaign`: observed creation completion at revision zero.
- Other cues require newly observed committed receipts, a confirmed owner/session,
  current route and no unresolved pending operation. A submitted button click is
  insufficient. NPC Step's quiet cue is a fallback for a committed NPC action
  without a more specific mapped event.
- Dice begins when new committed exchange evidence arrives, alongside the existing
  roll presentation. The clip plays to its natural media end unless replaced or
  stopped. One optional follow-up can then mark conquest, defender loss, attacker
  loss or an all-tie exchange. Mixed losses select the defender-loss cue;
  authoritative numbers remain in the visual results.
- Reduced motion and fast-forward omit the optional follow-up. Skip cancels the
  matching follow-up without cutting the dice clip to zero length. New cues,
  mute and Pause cancel old playback/follow-ups. Gameplay never waits for audio.
- One voice, 160 ms normal cooldown, 1,200 ms fast-forward cooldown; new playback
  replaces the previous voice/follow-up. No historical audio queue. Completion and
  explicit Pause take priority. Some lower-priority cues are intentionally omitted.
- A new victory receipt plus completed state produces either human victory or
  owner defeat, never both. Old completed loads stay silent. Spectator polling
  never produces committed-game effects; intentional local inspection remains
  optional audible feedback after consent.

## Preferences and failure handling

Sound defaults off, effects volume 35%. Only `enabled` and bounded `volume`
are stored under `geopolitics.sound.v1`. No session/user/token/game data enters
this record. Restored enabled preferences still require explicit activation in
a new tab. Mute/zero volume stops playback; storage denial stays in memory.
Missing/blocked media cannot throw into gameplay. A small accessible status
reports unavailable sound without retrying any game or provider operation.

Evidence: `output/ui-stage8-5/audio-metadata.json`, `audio-inventory.json`,
`review.json`; tests: `frontend/tests/sound.test.mjs`.

Current Super QA diagnosis and measured playback evidence are retained locally in
`docs/UI_SOUND_DIAGNOSTIC_REPORT.md`. The 650 ms visual
animation deadline no longer truncates the four-second source dice clip.
