#!/usr/bin/env python3
import argparse
import os
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


BASE_URL = os.environ.get("KLEINANZEIGEN_URL", "")
STATE_PATH = Path(os.environ.get("KLEINANZEIGEN_STATE", ".state/state.json"))
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
MAX_PAGES = 5
REQUEST_DELAY_SECONDS = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
        },
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} for {url}")
        return response.read().decode("utf-8", errors="replace")


def validate_url(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    if p.scheme != "https" or p.hostname not in {"www.kleinanzeigen.de", "kleinanzeigen.de"} or p.username or p.password:
        raise ValueError("Provide an HTTPS Kleinanzeigen search URL")
    return url


def page_url(page: int) -> str:
    validate_url(BASE_URL)
    if page < 1: raise ValueError("Page must be positive")
    p = urllib.parse.urlsplit(BASE_URL)
    parts = [x for x in p.path.split("/") if x and not re.fullmatch(r"seite:\d+", x)]
    if page > 1:
        pos = len(parts) - 1 if parts and re.match(r"c\d", parts[-1]) else len(parts)
        parts.insert(pos, f"seite:{page}")
    return urllib.parse.urlunsplit((p.scheme, p.netloc, "/" + "/".join(parts), p.query, ""))


def clean_text(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def extract_field(pattern: str, block: str) -> str:
    match = re.search(pattern, block, flags=re.I | re.S)
    if not match:
        return ""
    return clean_text(match.group(1))


def extract_json_ld(block: str) -> dict:
    match = re.search(
        r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        block,
        flags=re.I | re.S,
    )
    if not match:
        return {}
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def extract_items(page_html: str) -> list[dict[str, str]]:
    items = []
    pattern = re.compile(
        r'<article\b(?P<attrs>[^>]*)>(?P<body>.*?)</article>',
        flags=re.I | re.S,
    )
    for match in pattern.finditer(page_html):
        attrs = match.group("attrs")
        body = match.group("body")
        ad_id_match = re.search(r'\bdata-adid="(\d+)"', attrs, flags=re.I)
        if not ad_id_match:
            continue
        ad_id = ad_id_match.group(1)
        href_match = re.search(r'data-href="([^"]+)"', attrs)
        if not href_match:
            href_match = re.search(r'<a\b[^>]*href="([^"]+)"', body, flags=re.I)
        href = href_match.group(1) if href_match else ""
        if href.startswith("/"):
            href = "https://www.kleinanzeigen.de" + href

        json_ld = extract_json_ld(body)
        title = extract_field(r'<h[23][^>]*>\s*<a\b[^>]*>(.*?)</a>\s*</h[23]>', body)
        if not title:
            title = clean_text(str(json_ld.get("title", "")))
        description = extract_field(
            r'class="[^"]*aditem-main--middle--description[^"]*"[^>]*>(.*?)</p>',
            body,
        )
        if not description:
            description = extract_field(
                r'<p\b[^>]*class="[^"]*text-bodyRegular[^"]*text-onSurfaceSubdued[^"]*"[^>]*>(.*?)</p>',
                body,
            )
        if not description:
            description = clean_text(str(json_ld.get("description", "")))
        price = extract_field(
            r'class="[^"]*aditem-main--middle--price-shipping--price[^"]*"[^>]*>(.*?)</p>',
            body,
        )
        if not price:
            price = extract_field(
                r'<p\b[^>]*class="[^"]*text-title3[^"]*font-strong[^"]*text-secondary[^"]*"[^>]*>(.*?)</p>',
                body,
            )
        location = extract_field(
            r'class="[^"]*aditem-main--top--left[^"]*"[^>]*>(.*?)</div>',
            body,
        )
        if not location:
            location = extract_field(
                r'<div\b[^>]*class="[^"]*text-onSurfaceNonessential[^"]*"[^>]*>(.*?)</div>',
                body,
            )
        item_text = clean_text(body)
        status_words = []
        lower = item_text.lower()
        for label in ("reserviert", "deaktiviert", "gelöscht", "pausiert"):
            if label in lower:
                status_words.append(label)

        items.append(
            {
                "id": ad_id,
                "title": title or f"Anzeige {ad_id}",
                "url": href,
                "price": price,
                "location": location,
                "description": description,
                "status": ", ".join(status_words) or "visible",
            }
        )
    return items


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"created_at": utc_now(), "known": {}, "last_seen_ids": []}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(STATE_PATH)


def read_bot_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token or not CHAT_ID: raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    return token


def send_telegram(text: str) -> None:
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": "false"}).encode()
    r = urllib.request.Request(f"https://api.telegram.org/bot{read_bot_token()}/sendMessage", data=data, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=30) as response: response.read()
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Telegram delivery failed") from None


def collect_items(max_pages: int) -> list[dict[str, str]]:
    by_id = {}
    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(REQUEST_DELAY_SECONDS)
        page_items = extract_items(fetch(page_url(page)))
        for item in page_items:
            by_id[item["id"]] = item
        if len(page_items) == 0:
            break
    return list(by_id.values())


def format_item(prefix: str, item: dict[str, str]) -> str:
    lines = [prefix, item["title"]]
    details = " · ".join(part for part in [item.get("price"), item.get("location")] if part)
    if details:
        lines.append(details)
    if item.get("status") and item["status"] != "visible":
        lines.append(f"Статус: {item['status']}")
    if item.get("description"):
        lines.append(item["description"][:220])
    if item.get("url"):
        lines.append(item["url"])
    return "\n".join(lines)


def main() -> int:
    global BASE_URL, STATE_PATH, CHAT_ID
    parser = argparse.ArgumentParser(description="Monitor Kleinanzeigen apartment listings.")
    parser.add_argument("--baseline", action="store_true", help="Save current listings without notifications.")
    parser.add_argument("--dry-run", action="store_true", help="Do not send Telegram messages.")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    parser.add_argument("--url", default=BASE_URL)
    parser.add_argument("--state", type=Path, default=STATE_PATH)
    args = parser.parse_args()
    if not args.url: parser.error("--url or KLEINANZEIGEN_URL is required")
    BASE_URL = validate_url(args.url)
    STATE_PATH = args.state
    if not 1 <= args.max_pages <= 20: parser.error("--max-pages must be between 1 and 20")

    items = collect_items(args.max_pages)
    if not items:
        raise RuntimeError("No listings parsed from Kleinanzeigen")

    state = load_state()
    known = state.setdefault("known", {})
    previous_seen = set(state.get("last_seen_ids", []))
    current_ids = {item["id"] for item in items}

    alerts = []
    for item in items:
        existing = known.get(item["id"])
        if existing is None:
            if not args.baseline:
                alerts.append(format_item("Новое объявление:", item))
        elif item["id"] not in previous_seen:
            alerts.append(format_item("Объявление снова появилось в выдаче:", item))
        elif existing.get("status") != item.get("status") and item.get("status") == "visible":
            alerts.append(format_item("Статус объявления снова активный:", item))

        known[item["id"]] = {
            **item,
            "first_seen_at": existing.get("first_seen_at") if existing else utc_now(),
            "last_seen_at": utc_now(),
        }

    for missing_id in previous_seen - current_ids:
        if missing_id in known:
            known[missing_id]["last_missing_at"] = utc_now()

    state["last_seen_ids"] = sorted(current_ids)
    state["last_checked_at"] = utc_now()
    state["source_url"] = BASE_URL
    save_state(state)

    if args.baseline:
        print(f"baseline saved: {len(items)} listings")
        return 0

    if not alerts:
        print(f"no changes: {len(items)} listings checked")
        return 0

    for alert in alerts[:10]:
        print(alert)
        print("---")
        if not args.dry_run:
            send_telegram(alert)
            time.sleep(1)
    if len(alerts) > 10 and not args.dry_run:
        send_telegram(f"Ещё {len(alerts) - 10} обновлений Kleinanzeigen. Ограничила сообщение первыми 10.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"kleinanzeigen monitor error: {exc}", file=sys.stderr)
        raise SystemExit(1)
