# Contributing

The project contains an early implemented traffic-control pilot. Useful contributions include clarifying the comparison protocol, proposing baselines, and documenting reproducible scenarios.

## Propose a change

Open an issue describing the problem or research question, the proposed approach, and how success can be checked. Discuss substantial model or dependency choices before implementing them.

Use a focused branch and keep pull requests small enough to review. Explain the change, its assumptions, and the checks performed. Update documentation alongside behavior changes.

## Research contributions

- Cite the original source for methods, equations, and borrowed material.
- Distinguish proposed work from implemented behavior and measured results.
- Record model parameters, scenario definitions, random seeds, solver settings, dependency versions, and hardware for experiments.
- Report infeasible runs, timeouts, and unsuccessful trials alongside successful runs.
- Add behavioral tests with the first implementation. Repository hygiene checks alone do not establish model correctness.
- Follow the [experiment requirements](experiments/README.md) for reproducible results.

## Before opening a pull request

```sh
python3 scripts/check_repository.py
git diff --check
git diff --cached --check
```

Review the files and diff for credentials, personal paths, generated data, and material that cannot be redistributed. Use `.env.example` only for clearly fictitious values. Keep downloaded papers and raw experimental output out of Git; link to their sources or approved artifact storage.

Original contributions use the project's [MIT license](LICENSE). Do not add third-party code without documenting its source and license.
