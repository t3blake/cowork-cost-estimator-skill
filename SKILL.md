---
name: Cowork Cost Estimator
description: >
  Use this skill when the user asks how many Copilot Credits a Cowork task
  will cost, how expensive a task/session will be, or wants a cheaper way
  to do something before or during a Cowork session. Triggers include:
  "how many credits will this use", "what will this cost", "estimate the
  cost of this task", "is this going to be expensive", "cheaper way to do
  this". Also use proactively when a task looks large (many files/apps,
  long multi-step work) to warn the customer before they commit to it.
---

# Cowork Cost Estimator

Estimates the Copilot Credit cost of a Cowork task **before** committing
to it, with transparent caveats and memory-aware cost-optimization tips.

> **Disclaimer:** proof-of-concept / modeling aid, not a production tool.
> No warranty or guarantee of accuracy — output is a rough, non-binding
> planning estimate, not an official Microsoft figure. Treat only
> official Microsoft documentation and the tenant's own Microsoft 365
> admin center Credits report as sources of truth for actual cost.

## Hard requirement: keep this skill's own overhead low

This skill must not cost more, in tokens/context, than the task it is
estimating. Concretely:

- Prefer the archetype lookup (`archetypes.json`) over open-ended
  reasoning. Read the file once, match, and stop — do not re-read it per
  candidate archetype.
- Only fall back to `scripts/estimate.py` when no archetype confidently
  matches. Call it once with best-guess rough inputs; do not iterate on
  it or call it more than once per estimate.
- Do not read the user's actual attached files/content in full merely to
  size them — use file names, counts, and any size metadata already
  visible. Do not open every attachment just to estimate its length.
- Keep the response itself short: the output template in "Response
  format" below, nothing more. No restating the user's request back to
  them, no verbose reasoning trace, no re-printing the full archetype
  table.
- Ask at most one clarifying question, and only if the task genuinely
  cannot be classified at all. Otherwise proceed with stated assumptions
  instead of a back-and-forth.

## Steps

1. **Check memory first.** Before drafting any cost-optimization tips,
   check stored memory/preferences for statements about tool
   availability (e.g. "no GitHub Copilot seats", "Cowork not enabled for
   our tenant"). Suppress any tip that contradicts a known memory. Prefer
   a more recent explicit statement in the current conversation over an
   older stored memory if they conflict.
2. **Classify the task.** Identify the distinct deliverable(s) requested,
   then compare each against the archetypes in `archetypes.json` by
   keyword/intent overlap.
   - **Single deliverable:** use that archetype's range directly.
   - **2–3 distinct different-type deliverables** (e.g. a deck + a doc +
     an email): apply the **primary + partial** rule — take the archetype
     with the highest "expected" credits as primary (full low/expected/
     high), then add 50% of each additional distinct archetype's low/
     expected/high. Sum low with low, expected with expected, high with
     high. State each component archetype in the basis line (e.g.
     "presentation_creation (primary) + 50% doc_summary + 50%
     communications_draft").
   - **Same archetype repeated many times** (e.g. "draft 5 similar
     emails"), or **4+ distinct deliverables**: do not keep summing —
     classify as `bulk_or_org_wide` instead, since per-item cost amortizes
     further than the primary+50% rule assumes, and that archetype
     already covers this shape of task.
3. **If no confident archetype match:** run `scripts/estimate.py` with
   best-effort rough sizing inputs:
   - `--chars`: approximate character count of the task text plus any
     visible file sizes (do not open files just to count characters)
   - `--attachments`: number of attached files
   - `--steps`: expected number of discrete tool/agent steps
   - `--turns`: expected clarification/review turns
   - `--apps`: number of distinct M365 apps/data sources involved
   Treat its output as Low confidence and say so.
4. **Apply the credit range** (low/expected/high) from whichever path was
   used.
5. **Sanity-check only, do not recompute.** Silently judge whether the
   task's shape (deliverable count, tool-call breadth, context size)
   looks like Microsoft's own Light (0–1 tool calls, 0–1 deliverables),
   Medium (several tool calls, 2+ outputs), or Heavy (many tool calls,
   sustained runtime, many outputs) usage tier. This is a plausibility
   check on your own range, not a second estimate — never output the
   125/500/1200 figures themselves. Only add a one-line caveat if your
   computed range looks implausibly low for a task that is clearly Heavy
   by this definition; otherwise say nothing about it.
6. **List 2–4 relevant "what could change this" caveats** — choose only
   ones that actually apply to this task, from: unknown review/
   clarification rounds, unknown search/discovery scope, retry/failure
   loops, attachment size not yet known, model/routing changes
   mid-session.
7. **List cost-optimization tips**, filtered through memory (step 1):
   - Suggest a single M365 Copilot Chat prompt instead of a full Cowork
     session, if the task is really a one-shot question/edit.
   - Suggest GitHub Copilot (IDE/PR review) for code-specific sub-tasks,
     unless memory says the customer doesn't have it.
   - Suggest narrowing scope or splitting the task if it's large and
     loosely defined.
   - Suggest stopping after a lower-cost phase (e.g. a plan/draft) before
     a more expensive execution phase, when the task naturally splits
     that way.
   - **If the customer may execute in this same session after reading the
     estimate:** suggest starting execution in a fresh session instead,
     *but hedge it* — say plainly that we can't confirm how much (if
     anything) this saves, since it hasn't been isolated from other
     variables in testing. Pair the suggestion with a one-line
     carry-forward summary (task + chosen archetype/approach + any scope
     already settled) the customer can paste into the new session, so it
     doesn't re-derive scope from scratch. Rework/re-planning, not the
     estimate step, is the bigger real cost driver — a bare restart
     without that handoff note can cost more than it saves.
8. **Output using the Response format below only.** No commentary before
   or after it.

## Response format

```
## Estimated Cost — "<short task summary>"

| | Copilot Credits |
|---|---|
| Low      | N |
| Expected | N |
| High     | N |

Basis: <archetype name, or "phase-based heuristic (no archetype match)">
Confidence: <Low|Medium|High>

### What could change this
- <caveat 1>
- <caveat 2>
- <optional: one-line tier-plausibility caveat from step 5, only if it applies>

### Ways to reduce cost
- <tip 1>
- <tip 2>
- <optional: fresh-session tip with hedge + "Carry forward: <task + approach in one line>", only if applicable>
```

## Files in this skill

- `archetypes.json` — lookup table of task archetypes and estimated
  Copilot Credit ranges. Update via re-share as real data comes in (e.g.
  from a `/cost` skill or lab testing).
- `scripts/estimate.py` — fallback phase-based calculator, used only when
  no archetype matches confidently.

Note: `archetypes.json`'s current ranges are seed placeholders derived
from general public estimates, not verified Microsoft data. Treat matches
against it as Low–Medium confidence until replaced with real observed
figures from lab testing in this tenant.

Reference only (not read at runtime, not shipped as a file): Microsoft's
own Customer Cowork Estimator uses a fixed Light=125/Medium=500/
Heavy=1200 credits-per-prompt table for org-wide monthly capacity
planning. Do not use these numbers as this skill's per-task output — see
design.md §4.5 for why, and for the sanity-check-only usage in Step 5.
