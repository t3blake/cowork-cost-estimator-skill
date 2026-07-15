# Cowork Cost Estimator Skill

> **Disclaimer:** This is a proof-of-concept / modeling exercise, not a
> production tool. It is intended for estimating and directional
> planning only — not as a guaranteed or contractual cost figure. It is
> provided with **no warranty or guarantee of accuracy** of any kind, and
> is not an official Microsoft product or statement. Credit ranges,
> archetypes, and heuristics in this repo are the author's own estimates
> and may be wrong, outdated, or tenant-specific in ways this skill
> cannot account for. **Only official Microsoft documentation and your
> own tenant's Microsoft 365 admin center Credits report should be
> treated as sources of truth** for actual Copilot Credit costs — use
> this skill's output only as a rough, non-binding planning aid.

A skill for **Cowork in M365 Copilot** that estimates the Copilot Credit
cost of a task *before* you run it — with transparent caveats about what
it can't know, and cost-optimization tips that respect your stored
memories (e.g. it won't suggest GitHub Copilot if you've told it you
don't have access).

> **Status: v0, lab-testing in progress.** Ranges in `archetypes.json` are
> seed estimates, not verified Microsoft data. See `design.md` for full
> reasoning and `results.md`/`results2.md` for real lab-test data this
> version has been calibrated against so far.

## Why this exists

Cowork sessions can spin up multi-step, multi-tool, multi-artifact work
before you know how expensive it'll be. This skill front-loads a
low/expected/high Copilot Credit estimate, tells you plainly what could
push it higher or lower, and suggests cheaper alternatives (a single
M365 Copilot Chat prompt, offloading code work to GitHub Copilot,
narrowing scope, etc.) — filtered so it never suggests something your
memories say you can't use.

It also has a hard, self-imposed constraint: **estimating a task must not
cost more, in tokens/context, than the task itself.**

## How it works (short version)

1. Classify the request against a small bundled archetype library
   (`archetypes.json`) with known credit ranges, instead of reasoning
   from scratch every time.
2. For multi-deliverable requests, combine archetypes with a
   primary + 50%-per-additional rule rather than double-counting or
   under-counting.
3. Fall back to a phase-based heuristic (`scripts/estimate.py`) only when
   no archetype confidently matches, clearly labeled lower-confidence.
4. Sanity-check the result against Microsoft's own Light/Medium/Heavy
   per-prompt tiers (from the official Customer Cowork Estimator) —
   used only as a plausibility check, never as the literal output.
5. Filter every optimization tip through stored memory before suggesting
   it.

See [`design.md`](./design.md) for the full design rationale, open
questions, and the reasoning behind each of these decisions.

## Files

| File | Purpose |
|---|---|
| `design.md` | Full design document: methodology, transparency requirements, memory-aware filtering, architecture, open questions. |
| `SKILL.md` | The actual instructions Cowork loads and follows when the skill runs. |
| `archetypes.json` | Bundled lookup table of task archetypes and their estimated Copilot Credit ranges. |
| `scripts/estimate.py` | Dependency-free fallback calculator used when no archetype matches. |
| `results.md`, `results2.md` | Real lab-test transcripts used to calibrate and pressure-test the estimator. |
| `CustomerCoworkEstimator.xlsx` | Microsoft's own reference "Customer Cowork Estimator" workbook, used as a cross-check data source (see `design.md` §4.5). |

## Installing in Cowork

Package `SKILL.md`, `archetypes.json`, and `scripts/` into a `.zip` (a
prebuilt one is generated at the repo root during development) and use
Cowork's **Upload a skill** flow. See `design.md` §9 for confirmed
packaging limits and options.

## Contributing / updating estimates

`archetypes.json` ranges should be refined as real observed credit data
comes in (lab testing, a `/cost`-style skill output, etc.) — see
`design.md` §4.2 for the intended update/re-share workflow.

## License

MIT — see [`LICENSE`](./LICENSE).
