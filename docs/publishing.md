# Publishing to GitHub

## Prepared locally

- Project overview with explicit research-planning status.
- Research plan, reference attribution, and experiment documentation requirements.
- Contribution guidance, an issue form, and a pull request template.
- Ignore rules for local data, credentials, caches, and the reference PDF.
- Automated checks for local Markdown file links and selected repository hygiene rules.

## Before the first public push

1. Review the prepared MIT license, README, small published dataset, media, and marketing copy.
2. Selected destination: owner `akshay-robotics`, repository `decision-model-comparison`, public visibility. Account authentication and the first push must be verified before treating it as published.
3. Configure your Git author identity if it is not already set. Use your preferred public or GitHub-provided private email.
4. Run the checks below and review every staged file. The automated checks are limited and are not a full secret scanner.
5. Create the initial commit and an empty GitHub repository, then connect the remote and push `main`.
6. Confirm the first Actions run succeeds. Configure branch protection and required checks as appropriate for collaborators.

```sh
python3 scripts/check_repository.py
python3 scripts/check_publication_security.py
python3 scripts/validate_release.py
git add .
git diff --cached --check
git diff --cached --stat
git diff --cached
git status --short
```

After reviewing the staged content, commit with a message such as `chore: establish research repository`. Copy the remote URL from the actual GitHub repository rather than using a placeholder.

Use the account's GitHub-provided no-reply address for commit attribution; do not
publish a personal email. Complete the [security review](security-review.md)
before the first push.

## Suggested GitHub metadata

- **Description:** Early comparisons of decision models and an optimizer for SUMO traffic-signal control.
- **Prepared release:** browser-recorded demo, five-post thread, three graphics, and credential-free paired pilot results; see the project README.
- **Topics:** `decision-making`, `traffic-signal-control`, `sumo`, `optimization`, `reproducible-research`.
- **Default branch:** `main`.

## Reference material and results

Keep `TR2023-059.pdf` local and ignored. Its cover includes an IEEE copyright notice restricting redistribution; see the [reference notes](../references/README.md). Link to the original publication.

Before publishing results, record the implementation revision, complete configuration, environment, seeds, hardware, and reproduction command. Do not label a release as reproducing the paper until that claim is supported by a documented evaluation.
