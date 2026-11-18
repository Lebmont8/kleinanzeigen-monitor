# Kleinanzeigen Monitor

Dependency-free Python monitoring for new and reappearing listings, with local deduplication and optional Telegram delivery.

No personal location, budget, recipient, credentials or historical state is included. Provide your own HTTPS search URL.

~~~sh
python monitor.py --url https://www.kleinanzeigen.de/s-wohnung-mieten/c203 --baseline
python monitor.py --url https://www.kleinanzeigen.de/s-wohnung-mieten/c203 --dry-run
~~~

Export TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID locally for delivery. No OpenClaw configuration is read. State defaults to .state/state.json and is ignored by Git. --baseline records listings without notifying; --dry-run suppresses delivery but still updates state. At most 20 pages per invocation, with a delay between requests. Scheduling is explicit, not installed automatically.

Run python -m unittest discover -s tests -v for offline synthetic fixtures. Markup may change; zero parsed results is an error, not a successful empty baseline. No access-control bypass is implemented.

See LICENSE for source inspection rights.

## CI configuration
The GitHub Actions example is included at ci/github-actions.yml as a reference, not an active workflow. Run the documented verification commands locally. To enable Actions in your own repository, place this file under .github/workflows/.
