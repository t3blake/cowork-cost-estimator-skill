# Cowork Cost Estimator Skill — Design

> **Terminology**: "Cowork" here refers to **Cowork in M365 Copilot** —
> Microsoft's agentic, multi-step "work on this for me" experience inside
> M365 Copilot (distinct from a single-turn M365 Copilot Chat prompt, and
> distinct from GitHub Copilot). Cowork sessions can run longer, touch more
> files/content, and consume meaningfully more tokens than a normal Copilot
> Chat turn, which is exactly why customers need an upfront cost signal.

## 1. Purpose

Give customers an upfront, honest estimate of the **token consumption / cost**
a Cowork (M365 Copilot) task will incur before (or while) it runs, so they
can decide whether to proceed as-is, narrow scope, split the work, or route
part of it to a cheaper/simpler surface — e.g. a single M365 Copilot Chat
prompt instead of a full Cowork session, or GitHub Copilot for code-specific
sub-tasks — instead of running everything through Cowork.

The skill must be:
- **As accurate as possible** given available signal (task text, attached
  files, repo size, model selected, historical session data).
- **Transparent about what it cannot know** — it should never present a single
  false-precision number without caveats.
- **Actionable** — it should suggest concrete ways to reduce cost.
- **Memory-aware** — it must not repeat cost-optimization suggestions the
  customer has already ruled out (e.g. "we don't have GitHub Copilot seats",
  "Cowork isn't enabled for our tenant"), and should persist newly stated
  constraints as memories for future estimates.

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
| Prior similar sessions | Only if surfaced earlier in *this* chat (e.g. a past `/cost` output) or via an admin-granted Credits API/connector; **not** natively queryable by the agent | Optional, rarely available — see §4.2 |
| Stored memories about tool availability/licensing | Memory store (user + repo scoped) | Yes, must always be checked |

## 4. Estimation Methodology

Produce a **range**, not a point estimate: **low / expected / high**, each
broken into input tokens and output tokens, then converted to a cost range
using the pricing table for the selected model(s).

### 4.1 Phase-based token model

Break the task into phases and estimate each independently, then sum:

1. **System & tool-schema overhead** — fixed cost per turn for the system
   prompt, tool definitions, and skill instructions currently loaded.
   (Roughly constant per model/product; calibrate from historical sessions.)
2. **Context ingestion** — tokens for repo files, attachments, or search
   results the agent must read to complete the task. Estimate via
   `characters / ~4` per file, weighted by how much of a file is likely
   relevant vs. skimmed.
3. **Conversation turns** — number of back-and-forth exchanges expected
   (clarifying questions, review cycles). Estimate low/expected/high counts
   based on task ambiguity.
4. **Tool/agent invocations** — each tool call (grep, view, edit, shell,
   sub-agent) has its own input+output token cost; multi-step or
   multi-file tasks multiply this.
5. **Output generation** — code, documents, or explanations the agent must
   produce; estimate by expected artifact size (e.g. "a design doc" ≈
   1,500–3,000 tokens; "a full CRUD feature" ≈ 8,000–20,000 tokens output).
6. **Retries/iteration buffer** — a multiplier (e.g. 1.2x–2x) applied to
   the "high" estimate to account for failed builds, test loops, or
   re-reading files after edits.

### 4.2 Calibration from history — a known limitation for Cowork

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

### 4.3 Pricing conversion

Maintain a small pricing config (per-model $/1K input tokens, $/1K output
tokens, updated periodically) to convert the token range into a dollar
range. If the product/model mix is unknown, present token counts only and
flag cost as "depends on model selection."

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
- **Reuse existing sessions/history**: continue an idle background agent
  instead of starting a fresh session that re-loads full context.

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
## Estimated Cost — "Add OAuth login to the API"

| | Input tokens | Output tokens | Est. cost (model: X) |
|---|---|---|---|
| Low      | 18,000 | 4,000  | $0.31 |
| Expected | 34,000 | 9,000  | $0.62 |
| High     | 60,000 | 16,000 | $1.12 |

Confidence: Medium (based on 3 similar past sessions in this repo)

### What could change this
- Number of review/clarification rounds with you (not yet known).
- Whether the auth provider requires exploring unfamiliar SDK docs.
- Any failing tests requiring debugging loops.

### Ways to reduce cost
- This includes a `design.md`-only phase — you could stop after review
  before implementation to control spend.
- The database migration piece is mechanical; consider a lighter model
  for that sub-step.
```
(GitHub Copilot suggestion omitted here because memory indicates the
customer has no GitHub Copilot seats.)

## 9. High-Level Architecture (for future implementation)

- `SKILL.md` — trigger description + workflow instructions (as above).
- `scripts/estimate.py` (or similar) — phase-based token calculator taking
  task metadata + optional file list as input.
- `pricing.json` — per-model $/1K token rates, versioned/dated.
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
  **(Answered, see §4.2): no per-session API today — only tenant/admin
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
- Where should pricing data live so it stays current without the skill
  needing an update each time rates change?
- Should the "use plain M365 Copilot Chat" / GitHub Copilot suggestions
  require confirmed licensing (via memory) before being shown at all, or
  is a conditional phrasing acceptable by default?

## 11. Non-Goals

- Not a hard cost cap or billing enforcement mechanism — purely advisory.
- Not a guarantee of exact token counts — always a range with caveats.
- Does not attempt to estimate wall-clock time, only token/cost.
