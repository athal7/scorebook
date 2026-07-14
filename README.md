# Scorebook

A standalone e-ink softball scorebook device — a DIY replacement for a
paper scorebook, built for scoring a slow-pitch softball team's games at
the plate-appearance level.

## What it does

Scorebook runs on repurposed e-ink hardware (a jailbroken Kindle
Paperwhite, primarily) and lets you score a game by tapping through
at-bat results and runner advancement on a touchscreen, instead of
writing in a paper scorebook. Each game's data is stored on-device and
exported after the game so it can be aggregated into season stats
(AVG, OBP, SLG, OPS, and more) on a laptop.

## Budget

Roughly $50, excluding hardware already owned. The primary hardware
path (a used jailbroken Kindle Paperwhite) is chosen specifically
because it fits comfortably within that budget and needs no separate
battery pack.

## Design

The full design — hardware selection and rationale, data model, UI
flow, on-device software architecture, and the season-stats
aggregation approach — lives in [`docs/design.md`](docs/design.md).
Start there before writing any code.

## Status

Design-only. No application code exists yet; this repo currently
holds the design documentation that a future implementation session
will build against.
