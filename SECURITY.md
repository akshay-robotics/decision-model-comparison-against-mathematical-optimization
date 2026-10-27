# Security

This is a local research tool, not a hosted traffic-control service. The web
servers bind only to loopback. Do not expose them through a proxy, tunnel, or
public interface. Use Python 3.11 or newer for installing the project.

Keep API keys in the local environment or ignored `.env` file. Saved-result
viewing requires no key and cannot start paid model calls. New experiments can
contact OpenRouter over HTTPS with your own key. Use a dedicated key with an
appropriate spending limit.

Raw results, requests, responses, failure records, credentials, licenses, local
environments, and temporary tools are excluded from publication. Only the
selected synthetic traffic dataset, prompts without authorization headers,
historical source snapshots, and generated media are intended for release.

Before publishing, run:

```sh
python3 scripts/check_repository.py
python3 scripts/check_publication_security.py
python3 scripts/validate_release.py
python3 -m unittest discover -s tests -v
```

The publication check examines ZIP contents and common credential/privacy
patterns. It is not a guarantee that every possible secret or vulnerability is
absent. See the [pre-publication review](docs/security-review.md) for scope and
remaining limits. Historical source archives preserve the experiment and do
not inherit later security fixes; do not use their old web server.

Report sensitive security issues through GitHub's private vulnerability
reporting feature when available. Never put keys, personal data, or private
logs in a public issue or pull request.
