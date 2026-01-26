"""
Script to scrape card data from the Riftbound card gallery.
https://riftbound.leagueoflegends.com/en-us/card-gallery/

Collects: Energy, Power, Might, Domain, Card Type, Ability, Rarity, Card Set, and Image URL
for each card and saves to a JSON file.

Requires: pip install playwright
Then run: playwright install chromium
"""

import asyncio
import json
import re
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright is required. Install it with:")
    print("  pip install playwright")
    print("  playwright install chromium")
    sys.exit(1)


def strip_html(html_text):
    """Remove HTML tags from text."""
    if not html_text:
        return ""
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", " ", html_text)
    # Normalize whitespace
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def extract_card_data(raw_card):
    """Extract relevant fields from a raw card object."""
    card = {
        "id": raw_card.get("id", ""),
        "name": raw_card.get("name", ""),
        "collector_number": raw_card.get("collectorNumber"),
    }

    # Energy (cost) - extract numeric value from nested structure
    if "energy" in raw_card:
        energy_data = raw_card["energy"]
        if isinstance(energy_data, dict):
            # Structure is: {'label': 'Energy', 'value': {'id': 1, 'label': '1'}}
            value = energy_data.get("value", {})
            if isinstance(value, dict):
                card["energy"] = value.get("id")
            else:
                card["energy"] = value
        else:
            card["energy"] = energy_data

    # Power - extract numeric value from nested structure
    if "power" in raw_card:
        power_data = raw_card["power"]
        if isinstance(power_data, dict):
            value = power_data.get("value", {})
            if isinstance(value, dict):
                card["power"] = value.get("id")
            else:
                card["power"] = value
        else:
            card["power"] = power_data

    # Might - extract numeric value from nested structure
    if "might" in raw_card:
        might_data = raw_card["might"]
        if isinstance(might_data, dict):
            value = might_data.get("value", {})
            if isinstance(value, dict):
                card["might"] = value.get("id")
            else:
                card["might"] = value
        else:
            card["might"] = might_data

    # Domain
    if "domain" in raw_card:
        domain_data = raw_card["domain"]
        if isinstance(domain_data, dict):
            if "values" in domain_data and domain_data["values"]:
                domains = [
                    v.get("label", v.get("id", "")) for v in domain_data["values"]
                ]
                card["domain"] = domains[0] if len(domains) == 1 else domains
            elif "value" in domain_data:
                card["domain"] = domain_data["value"].get(
                    "label", domain_data["value"].get("id", "")
                )

    # Card Type
    if "cardType" in raw_card:
        card_type_data = raw_card["cardType"]
        if isinstance(card_type_data, dict):
            if "type" in card_type_data:
                types = card_type_data["type"]
                if isinstance(types, list):
                    type_labels = [t.get("label", t.get("id", "")) for t in types]
                    card["card_type"] = (
                        type_labels[0] if len(type_labels) == 1 else type_labels
                    )
            elif "value" in card_type_data:
                card["card_type"] = card_type_data["value"].get("label", "")

    # Rarity
    if "rarity" in raw_card:
        rarity_data = raw_card["rarity"]
        if isinstance(rarity_data, dict) and "value" in rarity_data:
            card["rarity"] = rarity_data["value"].get(
                "label", rarity_data["value"].get("id", "")
            )

    # Card Set
    if "set" in raw_card:
        set_data = raw_card["set"]
        if isinstance(set_data, dict) and "value" in set_data:
            card["card_set"] = set_data["value"].get(
                "label", set_data["value"].get("id", "")
            )

    # Card Image URL
    if "cardImage" in raw_card:
        img_data = raw_card["cardImage"]
        if isinstance(img_data, dict) and "url" in img_data:
            card["image_url"] = img_data["url"]

    # Ability/Text - extract from richText HTML
    if "text" in raw_card:
        text_data = raw_card["text"]
        if isinstance(text_data, dict):
            rich_text = text_data.get("richText", {})
            if isinstance(rich_text, dict) and "body" in rich_text:
                card["ability"] = strip_html(rich_text["body"])

    # Remove None values
    card = {k: v for k, v in card.items() if v is not None}

    return card


async def scrape_cards():
    """Scrape all card data from the Riftbound card gallery."""

    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        print("Navigating to card gallery...")
        await page.goto(
            "https://riftbound.leagueoflegends.com/en-us/card-gallery/",
            wait_until="domcontentloaded",
            timeout=60000,
        )

        # Wait for page to be ready
        print("Waiting for page content...")
        await page.wait_for_timeout(3000)

        # Extract __NEXT_DATA__ which contains all card information
        print("Extracting card data from page...")
        next_data = await page.evaluate("""() => {
            const script = document.querySelector('script#__NEXT_DATA__');
            if (script) {
                return script.textContent;
            }
            return null;
        }""")

        await browser.close()

        if not next_data:
            print("ERROR: Could not find __NEXT_DATA__ on page")
            return []

        data = json.loads(next_data)

        # Navigate to the card gallery blade
        blades = (
            data.get("props", {}).get("pageProps", {}).get("page", {}).get("blades", [])
        )

        card_gallery_blade = None
        for blade in blades:
            if blade.get("type") == "riftboundCardGallery":
                card_gallery_blade = blade
                break

        if not card_gallery_blade:
            print("ERROR: Could not find riftboundCardGallery blade")
            return []

        # Get raw cards from the blade
        raw_cards = card_gallery_blade.get("cards", {}).get("items", [])
        print(f"Found {len(raw_cards)} cards in data")

        # Extract and clean card data
        cards = []
        for raw_card in raw_cards:
            card = extract_card_data(raw_card)
            cards.append(card)

        return cards


def main():
    """Main entry point."""
    print("Riftbound Card Gallery Scraper")
    print("=" * 40)

    # Run the async scraper
    cards = asyncio.run(scrape_cards())

    if not cards:
        print("\nNo cards were scraped.")
        return

    # Save to JSON
    script_dir = Path(__file__).parent
    output_file = script_dir / "riftbound_cards.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cards, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(cards)} cards to {output_file}")

    # Print stats
    cards_with_energy = sum(1 for c in cards if "energy" in c)
    cards_with_power = sum(1 for c in cards if "power" in c)
    cards_with_might = sum(1 for c in cards if "might" in c)
    cards_with_ability = sum(1 for c in cards if "ability" in c)

    # Count unique domains, types, sets, rarities
    domains = set()
    card_types = set()
    card_sets = set()
    rarities = set()

    for c in cards:
        if "domain" in c:
            d = c["domain"]
            if isinstance(d, list):
                domains.update(d)
            else:
                domains.add(d)
        if "card_type" in c:
            t = c["card_type"]
            if isinstance(t, list):
                card_types.update(t)
            else:
                card_types.add(t)
        if "card_set" in c:
            card_sets.add(c["card_set"])
        if "rarity" in c:
            rarities.add(c["rarity"])

    print(f"\nStats:")
    print(f"  Total cards: {len(cards)}")
    print(f"  Cards with energy: {cards_with_energy}")
    print(f"  Cards with power: {cards_with_power}")
    print(f"  Cards with might: {cards_with_might}")
    print(f"  Cards with ability text: {cards_with_ability}")
    print(f"\n  Domains: {sorted(domains)}")
    print(f"  Card types: {sorted(card_types)}")
    print(f"  Card sets: {sorted(card_sets)}")
    print(f"  Rarities: {sorted(rarities)}")

    # Print sample cards
    print("\n" + "=" * 40)
    print("Sample cards:")
    print("=" * 40)
    for card in cards[:3]:
        print(json.dumps(card, indent=2))
        print("-" * 40)


if __name__ == "__main__":
    main()
