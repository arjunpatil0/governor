# Research journal

A chronological lab notebook. It exists so that the reasoning behind this project (hypotheses, decisions,
failures, corrections) can be reconstructed later for a paper, a thesis chapter or an interview.

## Rules
- One file per entry: `NNNN_YYYY-MM-DD_slug.md`. Append-only: never rewrite an old entry. If an earlier entry
  turns out wrong, write a new entry that says so and links back ("Correction to 0002").
- Every factual claim cites evidence: a commit hash, a data file path, or a paper.
- Write what you believed *at the time*, including wrong beliefs. Setbacks are the most valuable entries.
- Decisions with real alternatives also get an ADR in `../decisions/`.

## Entry template
```
# NNNN — <title>
Date: YYYY-MM-DD · Phase: <W1/W2/...> · Author: <Arjun / Claude Code / reviewer>
## Question            what we were trying to find out or build
## Belief going in     hypothesis / expectation, and why
## What we did         method, linked to commits / pre-registration
## What happened       results with numbers + file paths
## Interpretation      what it means; alternative explanations considered
## Setbacks / surprises  what went wrong or contradicted expectations, and how it was handled
## Decisions           links to ADRs
## Next                what this changes about the plan
```
