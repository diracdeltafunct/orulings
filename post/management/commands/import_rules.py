import json
import os

from django.core.management.base import BaseCommand

from post.models import RuleSection


class Command(BaseCommand):
    help = "Import rules from JSON files into the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--rule-type",
            type=str,
            choices=["tr", "cr", "both"],
            default="both",
            help="Which rules to import (tr, cr, or both)",
        )

    def handle(self, *args, **options):
        rule_type = options["rule_type"]

        if rule_type in ["tr", "both"]:
            self.import_rules("TR", "staticfiles/trsections")

        if rule_type in ["cr", "both"]:
            self.import_rules("CR", "staticfiles/crsections")

    def import_rules(self, rule_type, directory):
        """Import rules from JSON directory into database"""
        self.stdout.write(f"Importing {rule_type} rules from {directory}...")

        # Clear existing rules of this type
        deleted_count = RuleSection.objects.filter(rule_type=rule_type).delete()[0]
        self.stdout.write(f"Deleted {deleted_count} existing {rule_type} sections")

        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        rules_dir = os.path.join(base_dir, directory)

        if not os.path.exists(rules_dir):
            self.stdout.write(self.style.ERROR(f"Directory not found: {rules_dir}"))
            return

        # Get all JSON files
        json_files = sorted([f for f in os.listdir(rules_dir) if f.endswith(".json")])
        top_level_files = [f for f in json_files if "." not in f.replace(".json", "")]

        total_sections = 0
        for filename in top_level_files:
            filepath = os.path.join(rules_dir, filename)

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                count = self.import_section(data, rule_type, None, 0)
                total_sections += count
                self.stdout.write(f"  Imported {filename}: {count} sections")

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully imported {total_sections} {rule_type} sections"
            )
        )

    def import_section(self, data, rule_type, parent, order):
        """Recursively import a section and its children"""
        # Create the section
        section = RuleSection.objects.create(
            rule_type=rule_type,
            section=data["section"],
            text=data.get("text", ""),
            parent=parent,
            order=order,
        )

        count = 1

        # Import children
        for idx, child_data in enumerate(data.get("children", [])):
            count += self.import_section(child_data, rule_type, section, idx)

        return count
