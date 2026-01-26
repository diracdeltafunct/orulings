"""
Script to parse Riftbound errata PDFs and update card data.

Downloads errata PDFs from:
- Origins: https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/5bcbb23cb6131680ec8d469de6c87a3966a7622d.pdf
- Spiritforged: https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/44d1c3c1185a8360b290ddfbb1ba7f7aaae34e62.pdf

Finds old text and new text for each card, then updates the riftbound_cards.json
with an "errata_text" field containing the new text.

Requires: pip install pypdf requests
"""

import json
import re
import sys
from pathlib import Path

import requests

try:
    from pypdf import PdfReader
except ImportError:
    print("pypdf is required. Install it with:")
    print("  pip install pypdf")
    sys.exit(1)


ERRATA_PDFS = [
    {
        "name": "Origins",
        "url": "https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/5bcbb23cb6131680ec8d469de6c87a3966a7622d.pdf",
    },
    {
        "name": "Spiritforged",
        "url": "https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/44d1c3c1185a8360b290ddfbb1ba7f7aaae34e62.pdf",
    },
]


def download_pdf(url, output_path):
    """Download a PDF file."""
    print(f"  Downloading: {url}")
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(response.content)
    print(f"  Saved to: {output_path}")
    return output_path


def extract_text_from_pdf(pdf_path):
    """Extract all text from a PDF file."""
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text


def parse_errata_from_text(text):
    """Parse errata entries from PDF text.

    The format in the PDF is:
    Card Name
    [NEW TEXT] <new ability text>
    ▲
    [OLD TEXT] <old ability text>
    """
    errata_entries = []

    # Split into lines and clean
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for "[NEW TEXT]" pattern
        new_match = re.match(r"^\[NEW\s*TEXT\]\s*(.*)$", line, re.IGNORECASE)
        if new_match:
            new_text = new_match.group(1).strip()

            # Collect continuation lines until we hit [OLD TEXT] or ▲
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if re.match(r"^\[(NEW|OLD)\s*TEXT\]", next_line, re.IGNORECASE):
                    break
                if next_line == "▲":
                    j += 1  # Skip the ▲ marker
                    break
                new_text += " " + next_line
                j += 1

            # Now look for "[OLD TEXT]"
            if j < len(lines):
                old_match = re.match(
                    r"^\[OLD\s*TEXT\]\s*(.*)$", lines[j], re.IGNORECASE
                )
                if old_match:
                    old_text = old_match.group(1).strip()

                    # Collect continuation lines until next card (next [NEW TEXT])
                    k = j + 1
                    while k < len(lines):
                        next_line = lines[k]
                        if re.match(r"^\[NEW\s*TEXT\]", next_line, re.IGNORECASE):
                            break
                        # Stop at page markers or section headers
                        if re.match(
                            r"^(Page\s*\d+|ERRATA|CARD\s*ERRATA|Riftbound\s*Card\s*Errata|Last\s*Updated)",
                            next_line,
                            re.IGNORECASE,
                        ):
                            break
                        # Skip ▲ markers
                        if next_line == "▲":
                            k += 1
                            continue
                        # Check if this is a new card name (line before [NEW TEXT])
                        if k + 1 < len(lines) and re.match(
                            r"^\[NEW\s*TEXT\]", lines[k + 1], re.IGNORECASE
                        ):
                            break
                        old_text += " " + next_line
                        k += 1

                    # Look backwards to find the card name
                    # Card name is the line immediately before [NEW TEXT]
                    card_name = None
                    for back in range(i - 1, max(i - 5, -1), -1):
                        potential = lines[back]
                        # Skip markers, headers, and other errata text
                        if re.match(r"^\[(OLD|NEW)\s*TEXT\]", potential, re.IGNORECASE):
                            continue
                        if potential == "▲":
                            continue
                        if re.match(
                            r"^(Page\s*\d+|ERRATA|CARD\s*ERRATA|Riftbound|Last\s*Updated|Note:)",
                            potential,
                            re.IGNORECASE,
                        ):
                            continue
                        if len(potential) > 100:
                            continue
                        # Found a good candidate
                        card_name = potential
                        break

                    if card_name and new_text:
                        # Clean up the texts - remove extra spaces
                        old_text = re.sub(r"\s+", " ", old_text).strip()
                        new_text = re.sub(r"\s+", " ", new_text).strip()
                        # Clean up card name
                        card_name = re.sub(r"\s+", " ", card_name).strip()

                        errata_entries.append(
                            {
                                "card_name": card_name,
                                "old_text": old_text,
                                "new_text": new_text,
                            }
                        )

                    i = k
                    continue

        i += 1

    return errata_entries


def main():
    print("Riftbound Errata PDF Parser")
    print("=" * 40)

    script_dir = Path(__file__).parent
    cards_file = script_dir / "riftbound_cards.json"
    output_file = script_dir / "riftbound_cards_with_errata.json"

    # Load existing card data
    if not cards_file.exists():
        print(f"ERROR: {cards_file} not found. Run scrape_cards.py first.")
        sys.exit(1)

    with open(cards_file, "r", encoding="utf-8") as f:
        cards = json.load(f)

    print(f"Loaded {len(cards)} cards from {cards_file}")

    def normalize_name(name):
        """Normalize card name for matching - handle apostrophes and spacing."""
        name = name.lower().strip()
        # Replace various apostrophe types with standard one (using Unicode code points)
        # U+2019 RIGHT SINGLE QUOTATION MARK, U+2018 LEFT SINGLE QUOTATION MARK
        name = name.replace("\u2019", "'").replace("\u2018", "'").replace("`", "'")
        # Normalize whitespace (collapse multiple spaces to single)
        name = re.sub(r"\s+", " ", name)
        return name

    # Create a lookup by card name (lowercase for matching)
    cards_by_name = {}
    for card in cards:
        name = normalize_name(card.get("name", ""))
        if name:
            if name not in cards_by_name:
                cards_by_name[name] = []
            cards_by_name[name].append(card)

    # Download and parse errata PDFs
    all_errata = []

    print("\nDownloading and parsing errata PDFs...")
    for pdf_info in ERRATA_PDFS:
        pdf_name = pdf_info["name"]
        pdf_url = pdf_info["url"]
        pdf_path = script_dir / f"errata_{pdf_name.lower()}.pdf"

        print(f"\n{pdf_name} Errata:")

        # Download PDF
        try:
            download_pdf(pdf_url, pdf_path)
        except Exception as e:
            print(f"  ERROR downloading: {e}")
            continue

        # Extract text
        try:
            text = extract_text_from_pdf(pdf_path)
            print(f"  Extracted {len(text)} characters of text")

            # Save debug text
            debug_file = script_dir / f"debug_errata_{pdf_name.lower()}.txt"
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"  Saved debug text to: {debug_file}")

        except Exception as e:
            print(f"  ERROR extracting text: {e}")
            continue

        # Parse errata
        errata = parse_errata_from_text(text)
        print(f"  Found {len(errata)} errata entries")

        for e in errata:
            e["source"] = pdf_name

        all_errata.extend(errata)

    print(f"\nTotal errata entries found: {len(all_errata)}")

    # Print all errata for debugging
    if all_errata:
        print("\nAll errata entries:")
        for e in all_errata:
            print(f"  - [{e['source']}] {e['card_name']}")

    # Match errata to cards and update
    matched = 0
    unmatched = []

    for errata in all_errata:
        card_name = normalize_name(errata["card_name"])

        # Try exact match first
        if card_name in cards_by_name:
            for card in cards_by_name[card_name]:
                card["errata_text"] = errata["new_text"]
                card["errata_old_text"] = errata["old_text"]
            matched += 1
            print(f"  Matched: {errata['card_name']}")
        else:
            # Try partial match (card name might have subtitle like "Ahri, Alluring")
            found = False
            for name, card_list in cards_by_name.items():
                # Check if the errata card name is contained in or contains the JSON card name
                if card_name in name or name in card_name:
                    for card in card_list:
                        card["errata_text"] = errata["new_text"]
                        card["errata_old_text"] = errata["old_text"]
                    matched += 1
                    found = True
                    print(f"  Matched (partial): {errata['card_name']} -> {name}")
                    break
                # Also try matching just the first part before comma
                if "," in card_name:
                    first_part = card_name.split(",")[0].strip()
                    if first_part in name or name.startswith(first_part):
                        for card in card_list:
                            card["errata_text"] = errata["new_text"]
                            card["errata_old_text"] = errata["old_text"]
                        matched += 1
                        found = True
                        print(
                            f"  Matched (first part): {errata['card_name']} -> {name}"
                        )
                        break

            if not found:
                unmatched.append(errata["card_name"])

    print(f"\nMatched {matched} errata entries to cards")

    if unmatched:
        print(f"Unmatched errata ({len(unmatched)}):")
        for name in unmatched:
            print(f"  - {name}")

    # Save updated cards
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cards, f, indent=2, ensure_ascii=False)

    print(f"\nSaved updated cards to {output_file}")

    # Show sample errata
    if all_errata:
        print("\n" + "=" * 40)
        print("Sample errata entries:")
        print("=" * 40)
        for errata in all_errata[:3]:
            print(f"Card: {errata['card_name']}")
            old_display = (
                errata["old_text"][:100] + "..."
                if len(errata["old_text"]) > 100
                else errata["old_text"]
            )
            new_display = (
                errata["new_text"][:100] + "..."
                if len(errata["new_text"]) > 100
                else errata["new_text"]
            )
            print(f"Old: {old_display}")
            print(f"New: {new_display}")
            print("-" * 40)


if __name__ == "__main__":
    main()
