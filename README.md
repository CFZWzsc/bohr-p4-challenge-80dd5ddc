# Runtime contract

Bohrium Playground Period 4 submission — challenge `challenge-80dd5ddc` (track: `research-library`).

This repository holds the complete skill package for the challenge: the skill
definition, its executable pipeline and all supporting documents. No precomputed
answers, private data or credentials are included.

## Skill

- Name: `research-kb-evidence-qa`
- Summary: Use when a research-library case supplies local files plus questions and asks for sourced answers, version/duplicate awareness and honest evidence gaps; runs a stdlib-only deterministic indexer over /input and writes a contract-complete /app/output/result.json.

## Contents

| File |
|------|
| `SKILL.md` |
| `assets/policy.json` |
| `examples/demo-case/01_lab/2021-buffer-notes.md` |
| `examples/demo-case/01_lab/2022-buffer-revision.md` |
| `examples/demo-case/02_protocols/protocol-A.txt` |
| `examples/demo-case/03_data/measurements.csv` |
| `examples/demo-case/04_archive/2021-buffer-notes-copy.md` |
| `examples/demo-case/case.json` |
| `examples/quickstart.md` |
| `references/evidence-discipline.md` |
| `references/method.md` |
| `references/task-spec.md` |
| `scripts/run_skill.py` |
| `scripts/sk_entry.py` |
| `README.md` |

## How to run

```bash
python scripts/sk_entry.py --input /input --work /app/work --out /app/output
```

A single deterministic pass reads `/input`, computes the deliverable and writes a
contract-complete `/app/output/result.json` plus the human-readable review files
described in `SKILL.md`. The same input always produces byte-identical output; no
network access is used, and fields the materials cannot support are reported
explicitly instead of being left empty.

## Notes

- Pure Python standard library; no network access required.
- Every claim is anchored to paragraph-level evidence; unknown items are reported
  in `uncertainty` instead of being fabricated.
