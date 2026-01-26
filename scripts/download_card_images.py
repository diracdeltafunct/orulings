"""
Script to download card images from the Riftbound card gallery.
Uses the riftbound_cards.json file as reference for image URLs.

Images are saved to the static/cards folder.
"""

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


def download_image(url, save_path, timeout=30):
    """Download an image from URL and save to path."""
    try:
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()

        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    Error downloading: {e}")
        return False


def main():
    script_dir = Path(__file__).parent
    json_file = script_dir / "riftbound_cards.json"

    # Static folder is one level up from scripts
    static_dir = script_dir.parent / "static" / "cards"

    # Create cards directory if it doesn't exist
    static_dir.mkdir(parents=True, exist_ok=True)

    print("Riftbound Card Image Downloader")
    print("=" * 40)
    print(f"Source: {json_file}")
    print(f"Destination: {static_dir}")
    print()

    # Load card data
    if not json_file.exists():
        print(f"ERROR: {json_file} not found. Run scrape_cards.py first.")
        sys.exit(1)

    with open(json_file, "r", encoding="utf-8") as f:
        cards = json.load(f)

    print(f"Found {len(cards)} cards in JSON file")

    # Filter cards with image URLs
    cards_with_images = [c for c in cards if "image_url" in c and c["image_url"]]
    print(f"Cards with image URLs: {len(cards_with_images)}")
    print()

    # Download images
    downloaded = 0
    skipped = 0
    failed = 0

    for i, card in enumerate(cards_with_images):
        card_id = card.get("id", f"unknown_{i}")
        image_url = card["image_url"]

        # Determine file extension from URL
        parsed_url = urlparse(image_url)
        path = parsed_url.path
        ext = os.path.splitext(path)[1] or ".png"

        # Clean up extension (remove query params if any got included)
        if "?" in ext:
            ext = ext.split("?")[0]

        # Create filename from card ID
        filename = f"{card_id}{ext}"
        save_path = static_dir / filename

        # Skip if already downloaded
        if save_path.exists():
            skipped += 1
            if (i + 1) % 100 == 0:
                print(
                    f"  [{i + 1}/{len(cards_with_images)}] Skipping (already exists)..."
                )
            continue

        # Download the image
        if (i + 1) % 20 == 0 or i == 0:
            print(
                f"  [{i + 1}/{len(cards_with_images)}] Downloading {card.get('name', card_id)}..."
            )

        if download_image(image_url, save_path):
            downloaded += 1
        else:
            failed += 1

        # Small delay to be respectful to the server
        time.sleep(0.1)

    print()
    print("=" * 40)
    print(f"Complete!")
    print(f"  Downloaded: {downloaded}")
    print(f"  Skipped (already existed): {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Total images in folder: {len(list(static_dir.glob('*')))}")


if __name__ == "__main__":
    main()
