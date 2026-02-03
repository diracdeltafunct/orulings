import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from post.models import RuleSection


class Command(BaseCommand):
    help = "Sync rules from JSON files into the database (insert new, update changed, delete missing)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--rule-type",
            type=str,
            choices=["tr", "cr"],
            required=True,
            help="Which rules to sync (tr or cr)",
        )
        parser.add_argument(
            "--source-dir",
            type=str,
            help="Source directory for JSON files (relative to project root). "
            "Defaults to staticfiles/trsections for TR and staticfiles/crsections for CR",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def handle(self, *args, **options):
        rule_type = options["rule_type"].upper()
        dry_run = options["dry_run"]

        # Determine source directory
        if options["source_dir"]:
            source_dir = options["source_dir"]
        else:
            source_dir = (
                "staticfiles/trsections"
                if rule_type == "TR"
                else "staticfiles/crsections"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))

        self.sync_rules(rule_type, source_dir, dry_run)

    def sync_rules(self, rule_type, directory, dry_run):
        """Sync rules from JSON directory with database"""
        self.stdout.write(f"Syncing {rule_type} rules from {directory}...")

        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        rules_dir = os.path.join(base_dir, directory)

        if not os.path.exists(rules_dir):
            self.stdout.write(self.style.ERROR(f"Directory not found: {rules_dir}"))
            return

        # Load all rules from JSON files into a flat dict {section: text}
        json_rules = {}
        self.load_json_rules(rules_dir, json_rules)

        self.stdout.write(f"Found {len(json_rules)} rules in JSON files")

        # Get existing rules from database
        existing_rules = {
            r.section: r for r in RuleSection.objects.filter(rule_type=rule_type)
        }

        self.stdout.write(f"Found {len(existing_rules)} existing rules in database")

        # Calculate differences
        json_sections = set(json_rules.keys())
        db_sections = set(existing_rules.keys())

        to_delete = db_sections - json_sections
        to_insert = json_sections - db_sections
        to_check_update = json_sections & db_sections

        # Find which existing rules need text updates
        to_update = []
        for section in to_check_update:
            db_rule = existing_rules[section]
            json_text = json_rules[section]
            if db_rule.text != json_text:
                to_update.append((section, json_text))

        # Report what will happen
        self.stdout.write(f"\nChanges to apply:")
        self.stdout.write(f"  Delete: {len(to_delete)} rules")
        self.stdout.write(f"  Insert: {len(to_insert)} rules")
        self.stdout.write(f"  Update: {len(to_update)} rules")
        self.stdout.write(f"  Unchanged: {len(to_check_update) - len(to_update)} rules")

        if to_delete:
            self.stdout.write(self.style.WARNING(f"\nRules to delete:"))
            for section in sorted(to_delete, key=self.section_sort_key):
                self.stdout.write(f"    {section}")

        if to_insert:
            self.stdout.write(self.style.SUCCESS(f"\nRules to insert:"))
            for section in sorted(to_insert, key=self.section_sort_key)[:20]:
                text_preview = (
                    json_rules[section][:50] + "..."
                    if len(json_rules[section]) > 50
                    else json_rules[section]
                )
                self.stdout.write(f"    {section}: {text_preview}")
            if len(to_insert) > 20:
                self.stdout.write(f"    ... and {len(to_insert) - 20} more")

        if to_update:
            self.stdout.write(self.style.WARNING(f"\nRules to update:"))
            for section, new_text in sorted(
                to_update, key=lambda x: self.section_sort_key(x[0])
            )[:10]:
                old_text = existing_rules[section].text
                self.stdout.write(f"    {section}:")
                self.stdout.write(f"      OLD: {old_text[:60]}...")
                self.stdout.write(f"      NEW: {new_text[:60]}...")
            if len(to_update) > 10:
                self.stdout.write(f"    ... and {len(to_update) - 10} more")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDry run complete. No changes made.")
            )
            return

        # Apply changes within a transaction
        with transaction.atomic():
            # Delete rules no longer in JSON
            if to_delete:
                deleted_count = RuleSection.objects.filter(
                    rule_type=rule_type, section__in=to_delete
                ).delete()[0]
                self.stdout.write(f"\nDeleted {deleted_count} rules")

            # Update existing rules with changed text
            for section, new_text in to_update:
                RuleSection.objects.filter(rule_type=rule_type, section=section).update(
                    text=new_text
                )
            if to_update:
                self.stdout.write(f"Updated {len(to_update)} rules")

            # Insert new rules
            if to_insert:
                self.insert_new_rules(rule_type, to_insert, json_rules, rules_dir)
                self.stdout.write(f"Inserted {len(to_insert)} rules")

        self.stdout.write(self.style.SUCCESS(f"\nSync complete!"))

    def load_json_rules(self, rules_dir, json_rules):
        """Load all rules from JSON files into a flat dict"""
        json_files = sorted([f for f in os.listdir(rules_dir) if f.endswith(".json")])
        top_level_files = [f for f in json_files if "." not in f.replace(".json", "")]

        for filename in top_level_files:
            filepath = os.path.join(rules_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.flatten_rules(data, json_rules)

    def flatten_rules(self, data, json_rules):
        """Recursively flatten rule hierarchy into dict"""
        section = data["section"]
        text = data.get("text", "")
        json_rules[section] = text

        for child in data.get("children", []):
            self.flatten_rules(child, json_rules)

    def insert_new_rules(self, rule_type, to_insert, json_rules, rules_dir):
        """Insert new rules while maintaining parent relationships"""
        # Load full hierarchy to determine parents
        hierarchy = {}
        json_files = sorted([f for f in os.listdir(rules_dir) if f.endswith(".json")])
        top_level_files = [f for f in json_files if "." not in f.replace(".json", "")]

        for filename in top_level_files:
            filepath = os.path.join(rules_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.build_hierarchy(data, hierarchy, None)

        # Sort sections to insert parents before children
        sorted_sections = sorted(to_insert, key=self.section_sort_key)

        # Create sections in order, parents first
        created = {}
        for section in sorted_sections:
            parent_section = hierarchy.get(section)
            parent_obj = None

            if parent_section:
                # Try to find parent in newly created or existing
                if parent_section in created:
                    parent_obj = created[parent_section]
                else:
                    parent_obj = RuleSection.objects.filter(
                        rule_type=rule_type, section=parent_section
                    ).first()

            rule_obj = RuleSection.objects.create(
                rule_type=rule_type,
                section=section,
                text=json_rules[section],
                parent=parent_obj,
                order=self.get_order(section),
            )
            created[section] = rule_obj

    def build_hierarchy(self, data, hierarchy, parent_section):
        """Build dict mapping section -> parent_section"""
        section = data["section"]
        hierarchy[section] = parent_section

        for child in data.get("children", []):
            self.build_hierarchy(child, hierarchy, section)

    def section_sort_key(self, section):
        """Generate sort key for section numbers like 702.1.b.1"""
        parts = section.split(".")
        key = []
        for part in parts:
            if part.isdigit():
                key.append((0, int(part)))
            else:
                # Letters sort after numbers at same level
                key.append((1, part))
        return key

    def get_order(self, section):
        """Get order value from section number"""
        parts = section.split(".")
        last_part = parts[-1]
        if last_part.isdigit():
            return int(last_part)
        else:
            # Convert letter to number (a=0, b=1, etc.)
            return ord(last_part.lower()) - ord("a")
