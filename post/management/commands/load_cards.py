"""
Django management command to load card data from riftbound_cards_with_errata.json
into the database.

Usage:
    python manage.py load_cards
    python manage.py load_cards --clear  # Clear existing cards first
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from post.models import Card, CardDomain


class Command(BaseCommand):
    help = "Load card data from riftbound_cards_with_errata.json into the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing cards before loading",
        )
        parser.add_argument(
            "--file",
            type=str,
            default="scripts/riftbound_cards_with_errata.json",
            help="Path to the JSON file (default: scripts/riftbound_cards_with_errata.json)",
        )

    def handle(self, *args, **options):
        json_path = Path(options["file"])

        if not json_path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {json_path}"))
            return

        # Load JSON data
        with open(json_path, "r", encoding="utf-8") as f:
            cards_data = json.load(f)

        self.stdout.write(f"Loaded {len(cards_data)} cards from {json_path}")

        # Clear existing data if requested
        if options["clear"]:
            deleted_cards, _ = Card.objects.all().delete()
            deleted_domains, _ = CardDomain.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(
                    f"Cleared {deleted_cards} cards and {deleted_domains} domains"
                )
            )

        # Create all domain objects first
        domain_objects = {}
        for domain_name in [
            "Chaos",
            "Order",
            "Fury",
            "Calm",
            "Mind",
            "Body",
            "Colorless",
        ]:
            domain_obj, created = CardDomain.objects.get_or_create(name=domain_name)
            domain_objects[domain_name] = domain_obj
            if created:
                self.stdout.write(f"  Created domain: {domain_name}")

        # Track statistics
        created_count = 0
        updated_count = 0
        error_count = 0

        for card_data in cards_data:
            try:
                card_id = card_data.get("id", "")

                # Prepare card fields
                card_fields = {
                    "name": card_data.get("name", ""),
                    "collector_number": card_data.get("collector_number", 0),
                    "energy": card_data.get("energy", 0),
                    "power": card_data.get("power", 0),
                    "card_type": card_data.get("card_type", "Unit"),
                    "rarity": card_data.get("rarity", "Common"),
                    "card_set": card_data.get("card_set", "Origins"),
                    "image_url": card_data.get("image_url", ""),
                    "ability": card_data.get("ability", ""),
                    "errata_text": card_data.get("errata_text"),
                    "errata_old_text": card_data.get("errata_old_text"),
                }

                # Create or update the card
                card, created = Card.objects.update_or_create(
                    card_id=card_id,
                    defaults=card_fields,
                )

                # Handle domains (many-to-many)
                domains = card_data.get("domain", [])
                if isinstance(domains, str):
                    domains = [domains]

                # Clear existing domains and add new ones
                card.domain.clear()
                for domain_name in domains:
                    if domain_name in domain_objects:
                        card.domain.add(domain_objects[domain_name])

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as e:
                error_count += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"Error loading card {card_data.get('name', 'unknown')}: {e}"
                    )
                )

        # Print summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Created: {created_count} cards"))
        self.stdout.write(self.style.SUCCESS(f"Updated: {updated_count} cards"))
        if error_count:
            self.stdout.write(self.style.ERROR(f"Errors: {error_count}"))

        total_cards = Card.objects.count()
        self.stdout.write(self.style.SUCCESS(f"Total cards in database: {total_cards}"))
