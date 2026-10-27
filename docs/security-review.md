# Pre-publication security review

Review date: October 26, 2026. Scope: the files selected for the first public
commit, nested source ZIP members, published traffic data, media metadata,
current Python/JavaScript code, web handlers, and GitHub Actions settings.

## Changes made before release

- Removed local filesystem paths from the network's generated comment in the
  working tree and all three source archives. Network geometry is unchanged.
  Future network builds use relative paths.
- Removed the browser page's embedded historical attempt export. Raw provider
  requests/responses, failure journals, and local result folders remain ignored.
  The published paired traffic results retain all ten selected episodes.
- Added Host/Origin validation to both loopback servers, required JSON requests
  for simulation work, bounded request bodies, rejected concurrent simulation
  jobs, and added browser response protections. This reduces cross-site and
  DNS-rebinding access to paid model operations.
- Disabled redirects for current authenticated provider requests, enforced the
  HTTPS provider destination, and stopped returning provider/solver error
  details to the browser. Model output remains a validated signal choice;
  it is never executed as code.
- Updated the image library and build tooling after checking known advisories;
  current package installation requires Python 3.11+. See the dependency
  review evidence below.
- Replaced current XML result readers with `defusedxml` and verified that
  entity-expansion input is rejected.
- Pinned the checkout action to the verified upstream commit, kept Actions
  permissions at `contents: read`, and disabled persisted checkout credentials.
- Added an offline publication gate that scans nested ZIPs and checks common
  key formats, configured local secret values, private paths/emails, private
  account identifiers, unsafe archive paths, and raw-log filenames. It prints
  file/rule names without printing matched values. CI runs the same gate.

## Review evidence

The release checks verify dataset counts, source fingerprints, checksums,
post lengths, graphics, and the video hash. The credential/privacy check also
scans the source archive members rather than trusting ZIP filenames. Media
metadata inspection found no author names, EXIF location data, or private
filesystem paths. The demo records only the saved browser canvas.

Security regression tests cover cross-origin/rebound requests, non-JSON and
oversized inputs, queue bounds, private error suppression, redirect refusal,
allowed saved replay loading, and nested-archive scanning. Existing controller
and scoring tests also remain part of the release checks.

The isolated Python 3.12 environment installed successfully and passed all
48 enabled tests; two live SUMO integration tests were not run during this
review. Figure regeneration also succeeded with the patched media tools.
OSV returned no active advisories for the 28 reviewed package versions; the
[package-only evidence](security-dependencies.json) records those versions.
This includes Pillow 13.0.0, pip 26.2.2, setuptools 84.2.1, and defusedxml 0.7.1.

Bandit 1.9.4 scanned current Python code and reported zero high
or medium findings. Its 48 low findings were reviewed: subprocess calls use
argument lists with no shell, executable lookup assumes a trusted local
environment, seeded randomness generates simulation demand rather than
credentials, remaining ElementTree use constructs XML, and assertions check
offline data/media consistency rather than authorization. Run the release
validator normally, without Python's `-O` flag. Raw scanner reports stay local
because they can contain developer filesystem paths.

## Limits

This is a focused review, not an independent penetration test or a certification.
Known-advisory checks are point-in-time checks of package versions; they do not
prove that bundled native binaries or every dependency is vulnerability-free.
The local research servers are not designed for untrusted multiuser hosting.
Historical archives deliberately preserve the experimental core and do not
inherit the current network guards; use the current repository for browser
serving, and isolate historical reproduction. No history containing credentials
is intended for publication: this release starts with an initial commit.
