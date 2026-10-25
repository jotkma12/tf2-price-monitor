"""TF2 price monitor.

No scraping is performed. Set PRICE_API_URL only to an API endpoint that you
are authorized to use. The expected payload is documented in README.md and
must be adapted to the provider's actual documentation.
"""
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

import requests

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("tf2-price-monitor")

TIMEOUT = 20


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def normalize_provider_payload(payload: Any) -> list[dict]:
    """Normalize the provider response to our internal contract.

    Expected: {"items": [{"item_name": str, "source": str, "price": number,
    "currency": str, "item_url": optional str, "kind": "sell"|"buy_order"}]}
    This is a project contract, not a claim about any vendor's response.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError(
            "Unexpected provider response. Adapt normalize_provider_payload() "
            "to the provider's documented JSON schema."
        )

    normalized = []
    for row in payload["items"]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("item_name", "")).strip()
        source = str(row.get("source", "")).strip()
        currency = str(row.get("currency", "USD")).strip().upper()
        kind = str(row.get("kind", "sell")).strip().lower()
        try:
            price = float(row["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if not name or not source or price < 0 or kind not in {"sell", "buy_order"}:
            continue
        normalized.append({
            "item_name": name,
            "source": source,
            "currency": currency or "USD",
            "kind": kind,
            "item_url": str(row.get("item_url", "")).strip() or None,
            "price": price,
        })
    return normalized


def fetch_prices() -> list[dict]:
    endpoint = os.getenv("PRICE_API_URL", "").strip()
    api_key = os.getenv("PRICE_API_KEY", "").strip()
    if not endpoint:
        log.warning(
            "No PRICE_API_URL configured. Safe setup mode: no network request "
            "and no fabricated prices will be stored."
        )
        return []

    headers = {"Accept": "application/json"}
    if api_key:
        # Confirm the actual auth header with the provider's documentation.
        # Change this adapter if the provider uses another scheme.
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.get(endpoint, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    return normalize_provider_payload(response.json())


def supabase_request(method: str, table: str, *, params=None, json_body=None):
    base = required_env("SUPABASE_URL").rstrip("/")
    key = required_env("SUPABASE_SERVICE_ROLE_KEY")
    url = f"{base}/rest/v1/{table}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    response = requests.request(
        method, url, headers=headers, params=params, json=json_body, timeout=TIMEOUT
    )
    response.raise_for_status()
    if response.status_code == 204 or not response.text:
        return []
    return response.json()


def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.info("Telegram not configured; skipping notification.")
        return
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
        timeout=TIMEOUT,
    )
    response.raise_for_status()


def process_prices(prices: list[dict]) -> int:
    if not prices:
        log.info("No prices to process.")
        return 0

    changed_count = 0
    for price in prices:
        # Find or create the item row.
        filters = (
            f"item_name=eq.{requests.utils.quote(price['item_name'], safe='')}"
            f"&source=eq.{requests.utils.quote(price['source'], safe='')}"
            f"&kind=eq.{price['kind']}"
        )
        existing = supabase_request("GET", "tf2_items", params={
            "select": "id,item_name,source,kind,item_url",
            "item_name": f"eq.{price['item_name']}",
            "source": f"eq.{price['source']}",
            "kind": f"eq.{price['kind']}",
            "limit": "1",
        })

        if existing:
            item = existing[0]
        else:
            created = supabase_request("POST", "tf2_items", json_body=[{
                "item_name": price["item_name"],
                "source": price["source"],
                "kind": price["kind"],
                "item_url": price["item_url"],
            }])
            if not created:
                log.error("Could not create item row for %s", price["item_name"])
                continue
            item = created[0]

        previous = supabase_request("GET", "price_observations", params={
            "select": "price,currency,observed_at",
            "item_id": f"eq.{item['id']}",
            "order": "observed_at.desc",
            "limit": "1",
        })
        now = datetime.now(timezone.utc).isoformat()
        # Store every successful observation to build history.
        supabase_request("POST", "price_observations", json_body=[{
            "item_id": item["id"],
            "price": price["price"],
            "currency": price["currency"],
            "observed_at": now,
        }])

        if previous:
            old = previous[0]
            try:
                old_price = float(old["price"])
            except (TypeError, ValueError):
                old_price = price["price"]
            if old_price != price["price"] or old.get("currency") != price["currency"]:
                changed_count += 1
                message = (
                    f"TF2 price changed\n"
                    f"Item: {price['item_name']}\n"
                    f"Source: {price['source']} ({price['kind']})\n"
                    f"Previous: {old_price:.6f} {old.get('currency', '')}\n"
                    f"Current: {price['price']:.6f} {price['currency']}\n"
                    f"Observed: {now}"
                )
                if price.get("item_url"):
                    message += f"\n{price['item_url']}"
                send_telegram(message)
                log.info("Price changed: %s", price["item_name"])
            else:
                log.info("No price change: %s", price["item_name"])
        else:
            log.info("First observation saved for %s; no change alert sent.", price["item_name"])

    return changed_count


def main() -> int:
    try:
        prices = fetch_prices()
        if not prices:
            log.info("Run completed; no observations were added.")
            return 0
        count = process_prices(prices)
        log.info("Run complete. Changed prices: %s", count)
        return 0
    except Exception:
        log.exception("Monitor run failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
