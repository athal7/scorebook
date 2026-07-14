# Scorebook — Design

## Project goal

Build a DIY device to score slow-pitch softball games at the
at-bat / plate-appearance level (not pitch-by-pitch), replacing a
paper scorebook. The device must support extracting per-game data
after the fact so a separate script can compute season stats
(AVG/OBP/SLG/OPS and friends). Budget is ~$50 for anything not
already owned.

This document is the single source of truth for the design. A
developer picking this up cold should be able to start implementing
directly from it.

---

## Hardware — primary path: jailbroken Kindle Paperwhite

Target a **used Kindle Paperwhite**, 1st gen (model `EY21`, 2012) or
2nd gen (model `DP75SDI`, 2013). Prefer 2nd gen if the price is
comparable:

| | PW1 (`EY21`) | PW2 (`DP75SDI`) |
|---|---|---|
| SoC | i.MX508 @ 800MHz | i.MX6 SoloLite @ 1GHz |
| Screen | 758×1024, 6" E Ink Pearl/Carta | same |
| Jailbreak ceiling | firmware 5.4.4.2 (hard ceiling) | 5.4.4.2 safely; 5.4.5–5.6.x "with caveats" |

PW2 is noticeably snappier for custom e-ink drawing and has a wider
jailbreak-firmware compatibility window. Used market prices cluster
$30–55 (checked live via eBay-adjacent listings, mid-2026), which fits
the budget on its own.

### Buying checklist

- Identify the model by the back label: "Kindle" logo on the back =
  PW1; "Amazon" on the back + a light-gray "Kindle" logo on the front
  = PW2. Don't trust Amazon's "Nth generation" marketing labels — they
  conflate all Kindle models, not just Paperwhites.
- Ask the seller **not** to connect the unit to WiFi before shipping.
  Risk: an autonomous OTA update could push firmware past the
  jailbreak ceiling.
- Ask for a photo of Settings → menu → Device Info → Firmware Version
  before buying.
- On arrival: power on in **Airplane Mode immediately**, verify the
  firmware version before ever touching WiFi, deregister from any
  prior Amazon account (Settings → menu → Deregister), then jailbreak
  while still offline.

### Jailbreak

Use MobileRead's **"K5 JailBreak"** method — mature, long-running,
still patched through 2025 for newer firmware via "KindleBreak" plus
hotfixes. **KUAL** (Kindle Unified Application Launcher) is the
on-device app launcher used to run custom apps.

### Dev environment

Genuine Python 2.7 and 3.9 via NiLuJe's maintained cross-compiled
`kindle-python` package, distributed via the MRPI installer. SSH
access is available over USB.

### Rendering / partial refresh: FBInk

Use **FBInk** (NiLuJe's actively maintained C library + CLI + official
Python bindings `py-fbink`), which exposes the Kindle's mxcfb ioctl
waveform-mode API directly.

- Fast waveform modes `DU`/`A2` for common at-bat-entry partial-refresh
  updates (region-based, e.g. `fbink -s top=,left=,width=,height=`).
  Estimated ~100–300ms.
- Slower full-grayscale modes `GC16`/`GL16` for periodic full refreshes
  to clear e-ink ghosting — do a full refresh **once per half-inning**.

### Input

The Kindle's built-in **capacitive touchscreen**. No physical buttons
need to be wired.

### Power

Built-in battery (~1400–1500mAh class), well within a 2-hour game's
continuous-use envelope. Must disable the stock `powerd` daemon's
auto-dim/screensaver/sleep behavior via documented `lipc-set-prop`
calls (a known-solved problem in the jailbreak community) — otherwise
the screen will sleep mid-game.

### WiFi policy: **never enable WiFi on this device, permanently**

This is a deliberate decision, not just a data-extraction convenience
— it protects the jailbreak indefinitely from Amazon's forced
firmware auto-updates, the most common way jailbroken Kindles get
bricked/patched. All data extraction happens via USB, never network.

### Data extraction

The app writes CSV/SQLite export files to a folder on the Kindle's
internal storage (after each game, or via a manual "Menu → Export"
action). To retrieve: plug the Kindle into a computer via USB — it
mounts as a standard **USB Mass Storage** drive (stock Kindle
behavior, no extra tooling needed) — drag the exported files off,
unplug.

Note: plugging in USB while the custom app is running triggers the
stock "USB Drive Mode" screen, which takes over the display and
suspends the custom app. This is expected and fine, since extraction
only happens between games, never mid-game.

---

## Hardware — fallback path: Raspberry Pi 4 + Waveshare HAT

**Only used if the Kindle jailbreak fails on the purchased unit.**

- Waveshare 3.7" e-Paper HAT, $28.99, 480×280, B&W 4-grey, true 40-pin
  GPIO HAT (plugs directly onto Pi 4). 0.3s partial refresh / 3s full
  refresh. Driven by Waveshare's actively-maintained `e-Paper` GitHub
  repo (vendor demo-quality Python driver using `RPi.GPIO` +
  `spidev`), works unmodified on Pi 4 + Raspberry Pi OS Bookworm (Pi 4
  has no RP1 GPIO issues, unlike Pi 5).
- Input: 8 tactile switches (~$2 total) wired to free Pi 4 GPIO pins
  as a D-pad (Up/Down/Left/Right) + OK/Back/Undo/Menu — avoid GPIO
  pins used by the HAT's SPI/DC/RST/BUSY/PWR lines.
- Power: a separate USB-C power bank (10,000mAh, ~$15–30), since
  there's no WiFi/power at the field. This is the reason the Kindle
  path is preferred — it solves power for free via its own battery.
- Data extraction (fallback path only): a Flask endpoint + mDNS
  (`scorebook.local`) for browser-based download at home post-game,
  or pull the SD card / scp the SQLite file directly.
- Bookworm gotchas: `config.txt` moved to `/boot/firmware/config.txt`;
  enable SPI via `sudo raspi-config nonint do_spi 0`; the default `pi`
  user is already in the `gpio`/`spi`/`i2c` groups.

---

## Scoring fidelity: Tier B

Three tiers were considered; **Tier B** was chosen.

- **Tier A** (rejected): result + RBI + runs only, no defense.
  Insufficient for OBP/SLG since it can't distinguish 1B/2B/3B/HR/BB/HBP/SF
  from generic outs.
- **Tier B** (chosen): full offensive result-type enum, automatic
  base-state derivation, fielding position of outs. See below.
- **Tier C** (rejected): full traditional fielder-sequence notation
  (e.g. "6-3"). Too much input burden for a touchscreen device, and
  yields fielding stats rec teams rarely use.

### What Tier B captures

- Full offensive result-type enum per plate appearance:
  `1B, 2B, 3B, HR, BB, IBB, HBP, K, KL, IP_OUT, FC, E, SAC, SF, DP, ROE`
- **Automatic base-state model**: track who's on 1st/2nd/3rd and
  derive runs/RBI/LOB from runner advancement, rather than manually
  counting RBI. Less error-prone, less input burden, more data than
  manual counting.
- **Fielding-position-of-out: ON** — capture the fielder's position
  (1–9) for outs-in-play. (Explicitly confirmed wanted, overriding the
  originally-considered "optional" default.)
- No stolen bases, no balks — slow-pitch softball assumption (no
  leadoffs/steals in most slow-pitch leagues). The base-state model is
  force-advance-only, not a full baserunning simulation.
- **Variable game length** — do not hardcode 7 or 9 innings; support
  run-rule/mercy early endings, extra innings, and doubleheaders
  (modeled as separate `Game` rows).
- **Whole roster bats** — no fixed batting-order cap (rec softball
  commonly bats everyone present, not just a fixed 9 or 10).
- Substitutions, pinch-hitters, and courtesy runners are supported.
- The **opponent's offense is tracked only at line-score level** (runs
  scored per inning) — no PA-level tracking for the opposing team,
  only for our own team's lineup.

---

## Data model

Six logical tables:

- **`Team(id, name)`**
- **`Player(id, team_id, name, jersey_number, default_position)`**
- **`Game(id, date, home_team_id, away_team_id, our_side [home|away], location, scheduled_innings [nullable], status [in_progress|final], created_at)`**
- **`LineupSlot(id, game_id, batting_order, player_id, position, entered_inning, exited_inning [nullable])`**
  — substitutions are modeled as new `LineupSlot` rows sharing a
  `batting_order` value with an `exited_inning` set on the outgoing
  row. No separate `Substitution` table needed.
- **`PlateAppearance(id, game_id, inning, half [top|bottom], batter_player_id, batting_order, result [enum above], rbi, outs_on_play [0..3], fielder_position [nullable 1-9], base_state_before, base_state_after, runs_scored [JSON array of player_ids], seq, created_at)`**
  — this is the core event table.
- **Run/RBI stats per player are derived**, not stored: they come from
  `PlateAppearance.runs_scored` via query/view. No separate `Run`
  table is needed. (This can be normalized into a
  `RunScored(pa_id, player_id, earned)` table later during the
  export/aggregation step if a flat structure turns out to be more
  convenient — but the source of truth stays the JSON array on
  `PlateAppearance`.)

---

## UI / interaction flow

Adapted for the Kindle's touchscreen — no physical buttons.

1. **AT-BAT home screen** (persistent) — score, inning, outs, base
   diagram, on-deck batter highlighted. Tap → Result screen. Menu icon
   → game admin (substitutions, manual base edit, end-inning override,
   end-game).
2. **RESULT screen** — a grid of tappable result-type buttons
   (`1B 2B 3B HR` / `BB HBP K IP-out` / `FC E SAC SF` / `DP ROE`). Tap
   a cell to select.
3. **ADVANCE screen** (shown only if there are runners on base, or the
   batter reached) — a base diagram with each runner; tap a runner
   then tap their ending base (stay / +1 / +2 / score / out). Pre-seed
   with the most-likely (force-advance) outcome so the common case is
   a single confirming tap. This screen is what makes runs/RBI
   automatic.
4. **FIELDER prompt** (only on outs-in-play, since fielding capture is
   ON) — tap a position 1–9.
5. **CONFIRM screen** — one-line summary (e.g. "#12 Lopez: 2B, 1 RBI,
   Ruiz scores"). Confirm commits the PA (advances batting order,
   updates outs/score) and returns to the AT-BAT screen. An **Undo**
   action reverts the last committed PA via append-only reversal
   (never destructively deletes).

### e-ink refresh discipline

Buffer the full framebuffer, diff against the last frame, and issue
partial-refresh calls (`DU`/`A2` waveform) only for the changed
region(s). Force one full refresh (`GC16`/`GL16`) per half-inning to
clear accumulated ghosting.

---

## On-device software architecture (Python)

- **`game_state.py`** — pure domain state machine, no I/O (innings,
  outs, batting-order rotation, base-state transitions, run/RBI
  derivation). 100% unit-testable without any hardware.
- **`store.py`** — SQLite via stdlib `sqlite3`, WAL mode, one commit
  per committed plate appearance. Chosen over JSON/CSV specifically
  for crash-safety on unexpected power loss and for direct
  queryability during export.
- **`display.py`** — rendering abstraction (e.g. Pillow for
  compositing, or direct framebuffer drawing) behind an interface,
  calling out to FBInk for the actual partial/full refresh. Swappable
  with a fake/no-op display for laptop-side development.
- **`input.py`** — touch event handling (position → semantic UI
  event), swappable with a fake/keyboard input for laptop-side
  development.
- **`app.py`** — thin controller wiring input → state machine →
  persistence → render.
- **No network code anywhere on-device** — deliberately, per the
  no-WiFi-ever policy above.
- Runs as an on-device auto-launched app (via KUAL) with crash
  recovery: reload the in-progress game from SQLite on relaunch after
  any crash.

---

## Season stats aggregation (off-device)

Lives **off-device**, in a separate script — not on the Kindle.

- **`aggregate.py`** (stdlib `sqlite3` + `csv`; pandas optional) run on
  a laptop, ingests exported per-game SQLite/CSV files (pulled off the
  Kindle via USB) from a folder.
- Computes: PA, AB, H, 1B/2B/3B/HR, TB, AVG, OBP, SLG, OPS, BB, IBB,
  HBP, K, SF, SAC, RBI, R, LOB, and a per-inning line score per game.
- Since `fielder_position` is captured, also computes crude
  putout/assist/error tallies by position.

### Why off-device

Stat formulas will evolve and are much easier to iterate on a laptop
than a headless/homebrew Kindle environment. Keeping this off-device
keeps the on-device app frozen and reliable.

---

## Open items / suggested next steps for the implementing session

1. Buy the Kindle (see buying checklist above), verify firmware,
   jailbreak, and confirm FBInk partial-refresh works as expected via
   a trivial "draw a rectangle, refresh just that region" prototype.
   **This is the single biggest technical risk in the whole project**
   and should be validated early, before writing any app logic.
2. Implement `game_state.py` first, fully unit-tested, independent of
   any hardware. This is where correctness lives, and it's the one
   piece that's identical regardless of which hardware path — Kindle
   or Pi fallback — ends up being used.
3. Implement `store.py` against the data model above.
4. Only then build `display.py`/`input.py`/`app.py` against the real
   device once FBInk is validated.
5. Write `aggregate.py` last, against real exported data from a test
   game.
