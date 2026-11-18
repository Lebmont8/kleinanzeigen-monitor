# Verification
Verified on 2026-11-18, Python 3.12.
- python -m unittest discover -s tests -v: 8 tests passed.
- Coverage includes modern/legacy/JSON-LD parsing, pagination, search URL validation, state round-trip and credential-safe delivery errors.
- Synthetic fixtures only. No real search requests or Telegram messages were sent during public-edition checks.

## CI configuration
The GitHub Actions example is included at ci/github-actions.yml as a reference, not an active workflow. Run the documented verification commands locally. To enable Actions in your own repository, place this file under .github/workflows/.
