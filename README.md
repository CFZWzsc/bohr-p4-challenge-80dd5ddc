# Runtime contract

Bohrium Playground Period 4 submission — challenge `challenge-80dd5ddc` (track: `research-library`).

This repository holds the complete skill package for the challenge: the skill
definition, its executable entry point and all supporting scripts. No precomputed
answers, private data or credentials are included.

## Skill

- Name: `research-kb-evidence-qa`
- Summary: Use when a research-library case asks a question over a local multi-file knowledge base and requires sourced answers, passage back-links, conflict or gap reporting; run scripts/run_skill.py for a deterministic extractive result.json.

## Contents

| File |
|------|
| `SKILL.md` |
| `scripts/run_skill.py` |
| `README.md` |

## How to run

```bash
python scripts/run_skill.py --case /input/case.json --output /app/output/result.json
```

The entry point is `SKILL.md`; input/output contracts, error handling and a minimal
usage example are documented there.

## Notes

- Pure Python standard library; no network access required.
- The result JSON keeps the input case id, the main results, per-item evidence,
  a run status and an uncertainty section.
