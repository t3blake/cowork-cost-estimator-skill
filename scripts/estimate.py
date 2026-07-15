#!/usr/bin/env python3
"""
Fallback phase-based Copilot Credit estimator for the Cowork Cost
Estimator skill.

Used ONLY when no archetype in archetypes.json confidently matches the
task. Does the arithmetic in code -- deliberately kept dependency-free
and deterministic -- so the skill's own token/context footprint stays
low instead of having the model reason the math out loud.

Usage:
    python estimate.py --chars 4200 --attachments 2 --steps 5 --turns 2 --apps 3

All inputs are rough, self-reported sizing signals, not exact counts.
Output: a single line of JSON with a low/expected/high Copilot Credit
range and a confidence label.
"""
import argparse
import json

BASE_OVERHEAD = 15           # fixed system/skill-instruction overhead, in credits
PER_1K_CHARS_CONTEXT = 2.0   # context ingestion cost per 1,000 characters of task text
PER_ATTACHMENT_CHARS = 2000  # assumed skimmed size per attachment when no size is known
PER_TURN = 8                 # each expected clarification/review turn
PER_STEP = 6                 # each tool/agent invocation or discrete step
PER_APP = 10                 # each additional M365 app/data source touched beyond the first

RETRY_MULTIPLIER = {
    "low": 1.0,
    "expected": 1.3,
    "high": 1.8,
}


def estimate(chars: int, attachments: int, steps: int, turns: int, apps: int):
    context_cost = (chars / 1000.0) * PER_1K_CHARS_CONTEXT
    attachment_cost = (attachments * PER_ATTACHMENT_CHARS / 1000.0) * PER_1K_CHARS_CONTEXT
    step_cost = steps * PER_STEP
    turn_cost = turns * PER_TURN
    app_cost = max(0, apps - 1) * PER_APP

    subtotal = BASE_OVERHEAD + context_cost + attachment_cost + step_cost + turn_cost + app_cost

    return {
        "low": round(subtotal * RETRY_MULTIPLIER["low"]),
        "expected": round(subtotal * RETRY_MULTIPLIER["expected"]),
        "high": round(subtotal * RETRY_MULTIPLIER["high"]),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Fallback phase-based Copilot Credit estimator (used when no archetype matches)."
    )
    parser.add_argument("--chars", type=int, default=0,
                         help="Approx. characters of task text plus visible file sizes")
    parser.add_argument("--attachments", type=int, default=0,
                         help="Number of attached files")
    parser.add_argument("--steps", type=int, default=3,
                         help="Expected number of discrete tool/agent steps")
    parser.add_argument("--turns", type=int, default=1,
                         help="Expected clarification/review turns")
    parser.add_argument("--apps", type=int, default=1,
                         help="Number of distinct M365 apps/data sources touched")
    args = parser.parse_args()

    credits = estimate(args.chars, args.attachments, args.steps, args.turns, args.apps)

    result = {
        "unit": "Copilot Credits",
        "low": credits["low"],
        "expected": credits["expected"],
        "high": credits["high"],
        "confidence": "Low",
        "basis": "phase-based heuristic (no archetype match; not backed by observed credit data)",
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
