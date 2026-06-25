import json
import os
import sys
from datetime import datetime

import requests

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL")
MIN_DISCOUNT = int(os.environ.get("MIN_DISCOUNT", 50))
DATA_FILE = os.environ.get("DATA_FILE", "data/known_deals.json")
STEAM_API = "https://store.steampowered.com/api/featuredcategories"

CURRENCY = {
    1: "$", 2: "£", 3: "€", 5: "₽", 6: "R$",
    7: "¥", 8: "₩", 9: "₹", 10: "RM", 11: "PHP",
    12: "S$", 13: "฿", 14: "₴", 15: "₪",
    16: "CLP", 17: "S/", 18: "R$", 19: "zł",
    20: "NT$", 21: "kr", 22: "kr", 23: "CHF",
    24: "₸", 25: "HRK", 26: "Kč", 27: "kr",
    28: "kr", 29: "kr", 30: "₫", 31: "₺",
    32: "₭", 33: "kr", 34: "лв",
    35: "HK$", 36: "R", 37: "Rp", 38: "R",
    39: "₨", 40: "ARS", 41: "COP", 42: "$",
    43: "₱", 44: "د.إ", 45: "₦",
}


def load_data():
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"deals": {}}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def fmt_price(cents: int, cc: int) -> str:
    if cents == 0:
        return "Free"
    sym = CURRENCY.get(cc, "$")
    return f"{sym}{cents / 100:.2f}"


def fetch_featured() -> dict:
    r = requests.get(STEAM_API, timeout=30)
    r.raise_for_status()
    return r.json()


def check_major_sale(items: list) -> str | None:
    if len(items) >= 80:
        return "🔥 **Steam Sale lớn đang diễn ra!**"
    return None


def build_embed(item: dict, category: str):
    appid = item.get("id")
    name = item.get("name", "Unknown")
    disc = item.get("discount_percent") or 0
    orig = item.get("original_price") or 0
    final = item.get("final_price") or 0
    cc = item.get("currency") or 1

    is_freebie = disc == 100 or (orig > 0 and final == 0)

    if is_freebie:
        title = f"🎁 FREE — {name}"
        color = 0x00FF00
        price_field = f"~~{fmt_price(orig, cc)}~~ → **Free! 🆓**"
    else:
        title = f"{name}  (-{disc}%)"
        color = 0x66C0F4
        price_field = (
            f"~~{fmt_price(orig, cc)}~~ → **{fmt_price(final, cc)}**  (-{disc}%)"
        )

    img = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"

    return {
        "title": title,
        "url": f"https://store.steampowered.com/app/{appid}",
        "color": color,
        "thumbnail": {"url": img},
        "fields": [
            {"name": "💰 Price", "value": price_field, "inline": True},
            {"name": "📂 Category", "value": category.title(), "inline": True},
        ],
        "footer": {
            "text": f"Steam Deal Bot • {datetime.now().strftime('%H:%M %d/%m/%Y')}"
        },
    }


def send_discord(embeds: list[dict], header: str | None = None):
    if not DISCORD_WEBHOOK:
        print("SKIP: no webhook URL")
        return

    payloads = []
    if header:
        payloads.append({"content": header})

    for i in range(0, len(embeds), 10):
        batch = embeds[i : i + 10]
        payloads.append({"embeds": batch})

    for p in payloads:
        r = requests.post(DISCORD_WEBHOOK, json=p)
        r.raise_for_status()


def main():
    if not DISCORD_WEBHOOK:
        print("FATAL: DISCORD_WEBHOOK_URL not set")
        sys.exit(1)

    known = load_data()
    deals = known.get("deals", {})

    print("Fetching Steam featured deals...")
    data = fetch_featured()

    new_embeds = []
    updated_deals = dict(deals)
    reported_ids = set()

    for cat_key in ["specials", "top_sellers", "new_releases"]:
        cat = data.get(cat_key, {})
        if not isinstance(cat, dict):
            continue
        items = cat.get("items", [])
        if not items:
            continue

        for item in items:
            appid = str(item.get("id"))
            if not appid:
                continue

            disc = item.get("discount_percent") or 0
            orig = item.get("original_price") or 0
            final = item.get("final_price") or 0
            name = item.get("name", "?")
            is_freebie = disc == 100 or (orig > 0 and final == 0)

            if disc < MIN_DISCOUNT and not is_freebie:
                continue

            prev = deals.get(appid)
            if prev and prev["disc"] == disc and prev["final"] == final:
                continue

            if appid not in reported_ids:
                reported_ids.add(appid)
                print(f"  NEW: {name}  (-{disc}%)  [{cat_key}]")
                new_embeds.append(build_embed(item, cat_key.replace("_", " ")))

            updated_deals[appid] = {
                "name": name,
                "disc": disc,
                "final": final,
                "seen": datetime.now().isoformat(),
            }

    if not new_embeds:
        print("No new deals to report.")
        save_data({"deals": updated_deals, "last_update": datetime.now().isoformat()})
        return

    specials_items = data.get("specials", {}).get("items", [])
    header = check_major_sale(specials_items)

    send_discord(new_embeds, header)
    print(f"Sent {len(new_embeds)} deal(s) to Discord ✓")
    save_data({"deals": updated_deals, "last_update": datetime.now().isoformat()})


if __name__ == "__main__":
    main()
