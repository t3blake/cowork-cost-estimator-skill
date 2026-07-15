# Cowork Cost Estimator Skill — Design

> **Terminology**: "Cowork" here refers to **Cowork in M365 Copilot** —
> Microsoft's agentic, multi-step "work on this for me" experience inside
> M365 Copilot (distinct from a single-turn M365 Copilot Chat prompt, and
> distinct from GitHub Copilot). Cowork sessions can run longer, touch more
> files/content, and consume meaningfully more **Copilot Credits** than a
> normal Copilot Chat turn, which is exactly why customers need an upfront
> cost signal. This design intentionally estimates in **Copilot Credits**,
> not dollars — see §4.4.

## 1. Purpose

Give customers an upfront, honest estimate of the **Copilot Credit
consumption** a Cowork (M365 Copilot) task will incur before (or while) it
runs, so they can decide whether to proceed as-is, narrow scope, split the
work, or route part of it to a cheaper/simpler surface — e.g. a single
M365 Copilot Chat prompt instead of a full Cowork session, or GitHub
Copilot for code-specific sub-tasks — instead of running everything
through Cowork.

The skill must be:
- **As Token efficient as possible** The estimate can't cost more than the work it's intended to estimate. it needs to be extremely lightweight and avoid going down rabbit holes that burn credits.
- **As accurate as possible** given available signal (task text, attached
  files, repo size, model selected, historical session data).
- **Transparent about what it cannot know** — it should never present a single
  false-precision number without caveats.
- **Actionable** — it should suggest concrete ways to reduce cost.
- **Memory-aware** — it must not repeat cost-optimization suggestions the
  customer has already ruled out (e.g. "we don't have GitHub Copilot seats",
  "Cowork isn't enabled for our tenant"), and should persist newly stated
  constraints as memories for future estimates.
- **Token/context efficient by design (hard requirement)** — the skill's
  own overhead must never exceed the cost of the task it's estimating.
  Concretely: prefer the cheap archetype lookup (§4.2) over open-ended
  phase-based reasoning (§4.1); read reference files once, not per
  candidate; don't open attachments in full just to size them; cap
  clarifying questions at one, only if truly needed; keep the response
  itself limited to the fixed output template (§8), no restated request,
  no verbose reasoning trace. See `SKILL.md` in this repo for the
  enforced instructions.

## 2. Trigger Conditions (SKILL.md front matter, for later implementation)

```yaml
name: cost-estimator
description: >
  Use this skill when the user asks how many tokens, how much it will cost,
  or how expensive a task/session will be before or during a Cowork task.
  Triggers include: "how many tokens will this use", "what will this cost",
  "estimate the cost of this task", "is this going to be expensive",
  "cheaper way to do this". Also use proactively when a task looks large
  (many files, whole-repo operations, long-running multi-phase work) to
  warn the customer before they commit to it.
```

## 3. Inputs

| Input | Source | Required? |
|---|---|---|
| Task description (raw prompt) | User message | Yes |
| Target model(s) | Explicit user choice, or session default | Yes |
| Repo / workspace size (file count, LOC, largest files) | Local file system scan | Optional but improves accuracy |
| Attachments (docs, spreadsheets, images) | User-provided files | Optional |
| Expected sub-agent / background agent use | Inferred from task complexity | Optional |
| Prior similar sessions | Only if surfaced earlier in *this* chat (e.g. a past `/cost` output) or via an admin-granted Credits API/connector; **not** natively queryable by the agent | Optional, rarely available — see §4.3 |
| Stored memories about tool availability/licensing | Memory store (user + repo scoped) | Yes, must always be checked |

## 4. Estimation Methodology

Produce a **range**, not a point estimate: **low / expected / high**,
expressed in **Copilot Credits** — the actual unit Microsoft meters and
shows in the tenant admin Credits report (§4.3 covers the underlying
telemetry limitation). We deliberately do **not** convert to dollars by
default (see §4.4): credit-to-dollar rates vary by contract, region, and
prepaid pack discounts, none of which the skill can verify per-tenant, so
converting would add a second, harder-to-keep-accurate layer on top of an
already-approximate estimate for no real benefit to most customers.

### 4.1 Phase-based sizing model

Microsoft doesn't publish a fixed token-to-credit formula — credit cost
for a given interaction depends on the model selected, context volume,
tools/plugins engaged, and runtime, decided at runtime by the platform.
So this phase breakdown isn't used to compute credits directly; it's used
to **size the task in relative terms** (roughly how much context, how
many steps, how much output), which then does one of two things:
(a) helps classify the task into an archetype (§4.2) with a known
observed credit range, or (b) if no archetype fits, produces a rough
credit range via a labeled, low-confidence heuristic multiplier (see the
note at the end of this section) rather than a precise conversion.

Break the task into phases and estimate each independently, then sum:

1. **System & tool-schema overhead** — fixed cost per turn for the system
   prompt, tool definitions, and skill instructions currently loaded.
   (Roughly constant per model/product; calibrate from historical sessions.)
2. **Context ingestion** — size of repo files, attachments, or search
   results the agent must read to complete the task. Estimate via
   `characters / ~4` per file as a relative-size proxy, weighted by how
   much of a file is likely relevant vs. skimmed.
3. **Conversation turns** — number of back-and-forth exchanges expected
   (clarifying questions, review cycles). Estimate low/expected/high counts
   based on task ambiguity.
4. **Tool/agent invocations** — each tool call (grep, view, edit, shell,
   sub-agent) adds its own overhead; multi-step or multi-file tasks
   multiply this.
5. **Output generation** — code, documents, or explanations the agent must
   produce; estimate by expected artifact size (e.g. "a design doc" is
   much smaller than "a full multi-file report or workflow automation").
6. **Retries/iteration buffer** — a multiplier (e.g. 1.2x–2x) applied to
   the "high" estimate to account for failed steps, review cycles, or
   re-reading files after edits.

**On converting this size estimate to a credit number without an
archetype match:** be explicit in the output that this path has no
observed grounding — it's a relative-size heuristic, not a measured
credit range, and should carry a **Low** confidence label (§5) until real
`/cost`-sourced data lets it be promoted into `archetypes.json`.


### 4.2 Curated example/archetype library (cheap first-pass lookup)

**Good instinct, with caveats.** A pre-built reference table is much
cheaper than deriving an estimate from first principles every time,
because the model only has to *classify and compare*, not reason through
the full phase breakdown in §4.1. But a **live fetch of an arbitrary
GitHub Pages URL** as the mechanism has real downsides worth designing
around:

| Concern | Why it matters |
|---|---|
| **Staleness** | Pricing/model/credit-rate changes silently invalidate a static page unless someone actively maintains it — directly undermines the "as accurate as possible" goal. |
| **Latency & availability** | Adds a network round trip and an external dependency; needs a defined fallback if the page is unreachable. |
| **Trust / prompt-injection surface** | Fetched page content is read as context by the model. If the page is edited by anyone other than a trusted maintainer (or compromised), it becomes an injection vector. Must be pinned to a specific, review-gated source — not freely user-editable. |
| **Context cost of the page itself** | If the page is a long, unstructured example list, "comparing the prompt against it" still means reading the whole thing into context — which can erode the token savings if not kept small/structured. |
| **Per-tenant nuance** | Generic examples may not reflect a specific customer's repo size, licensing, or environment — risk of misleading precision if presented as the estimate rather than an anchor/reference point. |

**Confirmed via Microsoft Learn** ("Customize Copilot Cowork",
`learn.microsoft.com/microsoft-365/copilot/cowork/cowork-customize`,
updated 2026-07-01): the **Upload a skill** flow accepts either a single
`.md` file *or* a `.zip`/`.skill` archive with `SKILL.md` at its root plus
companion files (limits: ≤10MB compressed, ≤50MB uncompressed, ≤100
files). So bundling `archetypes.json` alongside `SKILL.md` in a
`.zip`/`.skill` package is directly supported — no external hosting is
required for this. Sharing works per-skill (private or specific org
users) with a **re-share** action to push updates to everyone who has it,
which also gives us a built-in update/versioning path for the lookup
table over time.

**Recommended approach — bundle in the package itself, not a live fetch:**

1. **Ship the lookup table as a companion file inside the `.zip`/`.skill`
   package** (e.g. `archetypes.json` sitting next to `SKILL.md` at the
   archive root or in a subfolder), with **credit ranges, not tokens or
   dollars**, as the recorded unit. This is fast, offline-safe, avoids
   the injection/staleness/latency risks of fetching an external page,
   and is a first-class supported pattern per the upload docs above — no
   extra plumbing needed.
2. **Classify, don't free-text-compare.** Define a small fixed set of task
   archetypes (e.g. "single doc summary", "multi-file report synthesis",
   "spreadsheet analysis", "cross-app workflow automation", "large
   codebase-style repo operation") each with a known **observed credit
   range**. Classifying the user's prompt into one of ~6–10 archetypes is
   a cheap operation; free-form similarity matching against a large
   example list is not.
3. **Two-tier fallback:** use the archetype lookup as the fast first pass;
   only fall through to the full phase-based breakdown (§4.1) when no
   archetype match is confident, or when the task is unusually large/
   ambiguous. Always disclose which path produced the number, and flag
   the phase-based fallback's credit figure as a lower-confidence
   heuristic (§4.1) since it isn't backed by an observed credit range.
3a. **Combining archetypes for multi-deliverable requests.** A single
    request often spans more than one archetype (e.g. a deck + a Word
    doc + an email). Naively taking "the high end of the closest match"
    (the original approach) under-counts real multi-artifact cost — lab
    testing showed a 3-artifact task landing well outside a single
    archetype's high bound. The **primary + partial** rule instead: take
    the highest-"expected" archetype as primary (full range), add 50% of
    each additional *distinct* archetype's range (summed low-with-low,
    expected-with-expected, high-with-high), reflecting that shared
    research/setup benefits every subsequent output but each still adds
    real generation/QA cost. Validated against lab data: deck (320) + 50%
    doc_summary (30) + 50% communications_draft (50) = 400 expected vs.
    430 actual on the clean run — within a few percent. Same-*type*
    repetition (e.g. "5 similar emails") or 4+ distinct deliverables
    amortizes further than this rule assumes, so those route to
    `bulk_or_org_wide` instead of continued summing.
4. **Keep updates flowing through re-share, not live editing.** When the
   `/cost` skill (§4.3) or maintainer review produces better reference
   data, update `archetypes.json` in the package and use Cowork's
   **re-share** action so everyone who has the skill gets the refreshed
   table automatically — this replaces the need for any external hosting
   or live fetch to keep the data current.
5. **Feed it from the `/cost` skill idea (§4.3), not free crowdsourcing.**
   If a `/cost`-style skill captures real completed-task costs, route
   those into `archetypes.json` through a **reviewed update process**
   before re-sharing the package, not a live, publicly-editable page.
   This turns the earlier open question about a `/cost` skill into the
   actual data pipeline for keeping the lookup table accurate, while
   keeping the trust boundary intact.
6. **A hosted external page is now the fallback, not the default** — only
   worth it for scenarios the bundled-file approach doesn't cover (e.g.
   sharing reference data across tenants outside the Share dialog's
   org-user model, or updates too frequent to re-share manually). If
   used, fetch from a **pinned, org-owned, change-controlled source**
   (tagged release/commit, not `main`/live HEAD), cache it for the
   session, and treat its content as data to parse — never as
   instructions to follow.

### 4.3 Calibration from history — a known limitation for Cowork

**Important constraint discovered during design review:** unlike a coding-
agent environment with its own queryable session-telemetry store, Cowork
does **not** give the agent itself a native way to query the credit cost of
its own past sessions. Credit accounting lives in the **Microsoft 365 admin
center** (Reports → Usage → Microsoft 365 Copilot → Credits) — a tenant/
admin-level surface, aggregated per user/day/agent, not a per-conversation
API the running agent can call by default.

Practical implication: unless a prior session explicitly captured its own
cost into the transcript (e.g. the customer ran a `/cost`-style skill
before and that output is still visible in chat history), there is **no
ground-truth number to calibrate against** for "similar past tasks." The
skill must be honest about this rather than pretending to have historical
telemetry it doesn't have. Fallback order, most to least reliable:

1. **In-transcript prior cost data** — if an earlier turn in *this same*
   conversation already surfaced credit/token numbers (from a prior
   `/cost` run or similar), reuse those as a real data point.
2. **Admin-exposed credits API/connector** (if the tenant has granted the
   skill access to one) — usable only as a coarse sanity check, since it's
   aggregated by user/day/agent, not by individual session, so it can
   confirm "this kind of work tends to run heavy/light" but not give an
   exact per-task figure.
3. **User self-reported figures** — ask the customer what similar past
   tasks cost them per their own admin dashboard; treat this as a labeled,
   unverified input, not a computed value.
4. **Pure heuristic estimate** (§4.1) — the default and most common case;
   must be clearly flagged as heuristic-only with no historical backing,
   which should also lower the reported confidence level (§5).

This replaces any assumption that the skill can silently query a session-
usage database the way a coding-agent tool (e.g. `session_store_sql`)
might — that pattern does not apply to Cowork today.

### 4.4 Pricing conversion

**Default: stay in Copilot Credits, no dollar conversion.** Per user
decision, the skill reports **Credits only** by default. Rationale:

- Credits are the unit Microsoft itself meters and shows in the tenant
  admin Credits report — reporting in the same unit means the customer
  can directly cross-check the estimate against their own dashboard.
- A credit-to-dollar rate depends on contract terms (list vs. negotiated
  rate), region, and prepaid credit-pack discounts — none of which the
  skill can know or verify per tenant. Adding a dollar layer would bolt a
  second, harder-to-keep-accurate conversion onto an already-approximate
  estimate, for accuracy the skill can't actually guarantee.
- Removing the dollar step also removes the need to maintain a
  `pricing.json` rate table at all — one less thing to go stale.

**When a dollar figure might still be worth adding:** only if a specific
customer provides their own known credit rate (e.g. "our contract prices
credits at $X"), which the skill can multiply in in real time, clearly
labeled as customer-provided rather than assumed. This should stay an
explicit opt-in, not a default behavior, and doesn't require shipping any
pricing data with the skill itself.

### 4.5 Cross-check against Microsoft's official Customer Cowork Estimator

**Data point discovered during lab review:** Microsoft publishes its own
"Customer Cowork Estimator" workbook (linked directly from the [usage-
based-billing overview](https://learn.microsoft.com/en-us/microsoft-365/copilot/usage-based-billing-overview-copilot-credits)
Learn page as `aka.ms/CustomerCoworkEstimator`), used for org-wide capacity
planning. It defines a fixed 3-tier **per-prompt** credit rate:

| Tier | Credits/prompt | Definition (Microsoft's own wording) |
|---|---|---|
| Light | 125 | Narrow context, lightweight model, 0–1 tool calls, minimal runtime — 0–1 deliverables |
| Medium | 500 | Richer context, capable model, several tool calls, moderate runtime — 2+ outputs |
| Heavy | 1200 | Broad context aggregation, high-quality model, many tool calls, sustained runtime — many outputs |

Its persona-based monthly totals (e.g. "Corporate Knowledge Worker": 22
light + 11 medium + 5 heavy prompts/month) reconcile exactly against
`count × rate` (22×125 + 11×500 + 5×1200 = 14,250), confirming this is a
literal, simple weighted sum — not a black box. The sheet is explicitly
labeled illustrative, derived from Frontier-program telemetry as of a
snapshot date, and assumes a specific model ("Anthropic Opus 4.8").

**Why we are *not* adopting this as our per-task credit model:** our
skill estimates a single upcoming task kicked off by one user message —
which, by Microsoft's own definition, is itself "one prompt." Adopting
the table literally would collapse our estimate into picking one of only
three fixed numbers (125 / 500 / 1200) for the whole task — far coarser
than the phase-based range we already produce, and it doesn't fit our own
lab data: both observed results (**430** and **745** credits, see
`results.md`/`results2.md`) fall strictly *between* the three fixed
values, not on one of them. That's strong evidence that Microsoft's 3-tier
table is a simplified **planning average** for monthly aggregate math, not
the real per-session metering granularity — real billing clearly scales
more continuously with actual context/tool-calls/retries, which is what
our phase-based model (§4.1) already approximates.

**How we do use it — as a sanity-check classifier, not an input to the
number.** After computing our own low/expected/high range, silently check
whether the task's shape (deliverable count, tool-call breadth, context
size) suggests it sits in Microsoft's Light/Medium/Heavy territory. Only
surface this if it's informative — e.g. our number looks implausibly low
for a task that is clearly "many deliverables, many tool calls, sustained
build" (Heavy by their own definition) — as a one-line qualitative caveat
(not the literal 125/500/1200 figures, and never as a second competing
number):

> "This task's shape (multiple deliverables, several tool calls) puts it
> in Microsoft's higher-usage tier — expect the wider end of the range
> above, especially if any step needs rework."

This preserves the whole point of the skill (task-specific, continuously-
scaled, transparent-about-uncertainty) while still benefiting from an
authoritative, Microsoft-sourced plausibility check. Treat the 125/500/
1200 rates as versioned reference constants tied to a specific snapshot
date/model — revisit if Microsoft updates the estimator or changes the
underlying model.

## 5. Transparency Requirements

The output must always include an explicit **"What this estimate can't
account for"** section, covering (as applicable to the specific task):

- Unknown number of clarification/review round-trips with the user.
- Files or dependencies not yet discovered (e.g. task requires exploring an
  unfamiliar codebase; true scope may only emerge mid-task).
- Whether the task will trigger background/sub-agents, which add their own
  full context overhead.
- Retry/failure loops (failing tests, build errors, flaky tools) that are
  inherently unpredictable.
- Model or reasoning-effort changes made mid-session by the user.
- Large or dynamic attachments (e.g. a spreadsheet that may expand once
  parsed) whose real size isn't known until opened.
- Any pricing assumptions (list model + rate used) since prices/models can
  change.

The skill should present a **confidence level** (e.g. Low/Medium/High) for
the estimate based on how much of the above is known vs. unknown, not just
a bare number.

## 6. Cost Optimization Suggestions

After the estimate, the skill proposes ways to reduce cost, filtered
through memory (see §7). Candidate suggestions:

- **Use plain M365 Copilot Chat instead of Cowork**: if the task is really
  a single question, a short summary, or a one-shot document edit, a
  regular M365 Copilot Chat prompt (or the native Word/Excel/PowerPoint/
  Outlook Copilot experience) accomplishes it without the extra overhead
  of a multi-step Cowork session (planning turns, tool calls, longer
  context retention across steps).
- **Offload to GitHub Copilot (IDE / PR review)**: for sub-tasks that are
  really code edits, inline completions, or PR review comments, using
  Copilot in the editor or Copilot code review is cheaper than having
  Cowork carry that piece through its agentic loop.
- **Narrow scope**: split a large ask into smaller sessions so each stays
  within a small, well-defined context window instead of one large
  multi-phase session.
- **Right-size the model/reasoning effort**: use a lighter/faster model for
  mechanical or well-defined sub-tasks, reserving high-effort models for
  genuinely hard reasoning steps.
- **Batch questions**: ask all clarifying questions up front instead of
  iterating turn-by-turn, to avoid repeated full-context re-sends.
- **Avoid redundant re-reads**: reference specific files/line ranges rather
  than asking the agent to re-scan a whole repo each turn.
- **Keep session context matched to what the next step actually needs** —
  this cuts both directions, and the skill should pick the direction that
  applies rather than always defaulting one way:
  - **Reuse** an existing/idle session if it already holds context the
    next step needs (files already found, scope already established) —
    restarting would just force re-deriving that.
  - **Start fresh** if the current conversation only holds overhead the
    next step doesn't need. This is our own skill's typical case: the
    cost-estimate exchange itself doesn't help execution. **Hedged, not a
    firm rule** — our only lab comparison of this (`results.md` vs.
    `results2.md`) mixed session-freshness with an unrelated docx-js
    library bug, so we cannot yet isolate how much (if anything) a fresh
    session actually saves. State this uncertainty plainly whenever the
    tip is given rather than presenting it as a proven saving.
  - **If recommending a fresh session, always pair it with a short
    carry-forward summary** (task + chosen approach/archetype + any
    scope already decided) the customer can paste into the new session.
    Lab evidence suggests **rework/re-planning, not the estimate step
    itself, is the dominant real cost driver** (e.g. the docx-js
    debugging spiral and repeated PPT font/QA iterations in `results.md`).
    A restart that forces the next session to re-derive scope from
    scratch could cost more than it saves; a restart paired with a
    compact handoff note avoids that trap.

## 7. Memory-Aware Filtering (critical requirement)

Before presenting optimization suggestions, the skill must:

1. **Query stored memories** (user-scoped and repository-scoped) for
   statements about tool/product availability or preference, e.g.:
   - "We don't have GitHub Copilot licenses."
   - "We're not licensed for Cowork / it's not enabled in our tenant."
   - "Never suggest splitting sessions, we prefer one long session."
2. **Suppress or rewrite** any suggestion contradicted by a stored memory.
   If GitHub Copilot is memory-flagged as unavailable, drop that
   suggestion entirely rather than showing it crossed out — don't remind
   the customer of something they can't use.
3. **Prefer the most recent explicit statement** in the current
   conversation over an older stored memory if they conflict (the user may
   have just gained/lost a license).
4. **Persist new constraints** the customer states during this skill's own
   interaction (e.g., "we don't use GitHub Copilot") as a new memory so
   future estimates — in this or other tasks — respect it automatically.
5. Never invent or assume licensing state; if unknown, suggestions should
   be phrased conditionally ("if you have GitHub Copilot seats...") rather
   than presented as settled fact, until a memory or explicit statement
   confirms one way or the other.

## 8. Output Format (example)

```
## Estimated Cost — "Prepare a quarterly report from last month's emails and calendar, and draft it in Word"

| | Copilot Credits |
|---|---|
| Low      | 180  |
| Expected | 340  |
| High     | 600  |

Basis: Archetype match — "multi-file report synthesis" (§4.2)
Confidence: Medium (archetype has 3 prior observed data points)

### What could change this
- Number of review/clarification rounds with you (not yet known).
- How much enterprise search is needed to find the source emails/files.
- Whether the Word draft goes through multiple revision rounds.

### Ways to reduce cost
- If this is really "summarize last month" with no drafting needed, a
  single M365 Copilot Chat prompt would be cheaper than a full Cowork
  session.
```
(No GitHub Copilot suggestion here since this task has no code component;
if it did, and memory indicated the customer has no GitHub Copilot seats,
that suggestion would be omitted entirely.)

## 9. High-Level Architecture (v0 implemented in this repo)

A first testable version of this package now exists in this repo as
`SKILL.md`, `archetypes.json`, and `scripts/estimate.py`, plus a packaged
`cowork-cost-estimator-skill.zip` at the repo root ready for lab-testing
via Cowork's **Upload skill** flow. Treat `archetypes.json`'s credit
ranges as unverified seed placeholders until replaced with real numbers
observed during lab testing.

**Packaging (confirmed):** per Microsoft Learn ("Customize Copilot
Cowork" — `learn.microsoft.com/microsoft-365/copilot/cowork/
cowork-customize`, updated 2026-07-01), Cowork's **Upload skill** flow
accepts a `.zip`/`.skill` archive with `SKILL.md` at its root plus
companion files (≤10MB compressed, ≤50MB uncompressed, ≤100 files). The
companion **Use Copilot Cowork** page (`microsoft-365/copilot/cowork/
use-cowork`, updated 2026-07-13) confirms companion files can include
**scripts**: "Skills can also include up to 20 companion files (such as
reference documents and scripts), with a total of 10 MB per skill" (that
20-file/10MB figure applies to the OneDrive-authored path; the zip-upload
path above has the looser 100-file/50MB limit). So a companion
`estimate.py` is an explicitly supported file type. **Remaining open
question:** the docs don't confirm whether Cowork *executes* a bundled
script directly as a subprocess, or reads it as reference code it
reimplements at runtime — behaviorally different, worth testing directly,
but not a blocker either way since the logic still ships with the skill.

This skill should ship as such an archive:

```
cowork-cost-estimator-skill/
├── SKILL.md          (frontmatter: name + description, required)
├── archetypes.json    (§4.2 lookup table, credit ranges — see below)
└── scripts/
    └── estimate.py    (§4.1 phase-based calculator, used as fallback)
```

Updates ship by editing the package and using Cowork's **re-share**
action, which pushes the refreshed archive to everyone the skill was
shared with — this is the update/versioning mechanism, no external
hosting required for the common case.

Note: Cowork explicitly warns users to "only upload skills from sources
you trust," since a skill runs as instructions to the AI. This reinforces
§4.2's stance against pulling in unreviewed external content at runtime —
the whole point of bundling `archetypes.json` in the trusted, reviewed
package is to avoid introducing exactly that kind of untrusted input.

**Units — Copilot Credits, not dollars (by design choice, see §4.4).**
`archetypes.json` and `estimate.py` output ranges in **Copilot Credits**
only. There is no `pricing.json`/dollar-conversion file in the default
package — see §4.4 for why, and for the narrow case where a dollar
conversion could still be added.

- `SKILL.md` — trigger description + workflow instructions (as above).
- `archetypes.json` — versioned, PR-reviewed lookup table of task
  archetypes with reference **credit** ranges (§4.2); the fast first
  pass, checked before falling back to phase-based estimation.
- `scripts/estimate.py` — phase-based **credit** estimator taking task
  metadata + optional file list as input; used when no archetype match
  is confident.
- Memory lookup — reuse the existing Copilot memory system
  (`store_memory` / `vote_memory` equivalents) rather than building a new
  store; the skill only *reads* memories to filter suggestions and *writes*
  new ones when the customer states a constraint.
- Historical calibration — no native session-telemetry query exists for
  Cowork. Limit to: (a) reusing prior in-transcript `/cost` output if
  present, (b) an optional admin-granted Credits Report connector for
  coarse, aggregate sanity-checking only, (c) explicit user-reported
  figures. Never assume a hidden per-session usage database is queryable.

## 10. Open Questions

- Does Cowork expose per-session token/cost telemetry we can query
  programmatically for calibration, or only after-the-fact totals?
  **(Answered, see §4.3): no per-session API today — only tenant/admin
  aggregate Credits reporting; per-session numbers only exist if a prior
  `/cost`-style skill already put them in the transcript.)**
- Would it be worth building a lightweight `/cost` skill first, purely so
  that its output persists in chat history and becomes a calibration
  input for *this* estimator on future related tasks in the same thread?
- If/when an admin-level Credits API connector becomes available to
  skills, what permission model would let this skill call it safely
  without over-scoping access to tenant-wide billing data?
- Should the estimate be shown once at task start, or refreshed
  mid-session as scope becomes clearer?
- Does Cowork execute a bundled `scripts/estimate.py` directly, or only
  read it as reference material it reimplements at runtime? (§9 — needs
  hands-on testing, not just doc confirmation.)
- Now that pricing is credits-only by default, how often does
  `archetypes.json` realistically need re-sharing to stay accurate as
  Microsoft's own credit-per-task behavior shifts over time?
- Should the "use plain M365 Copilot Chat" / GitHub Copilot suggestions
  require confirmed licensing (via memory) before being shown at all, or
  is a conditional phrasing acceptable by default?

## 11. Non-Goals

- Not a hard cost cap or billing enforcement mechanism — purely advisory.
- Not a guarantee of exact credit counts — always a range with caveats.
- Not a dollar-cost calculator by default — see §4.4 for the narrow,
  opt-in exception.
- Does not attempt to estimate wall-clock time, only Copilot Credits.
