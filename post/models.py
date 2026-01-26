# post/models.py
from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _
from mdeditor.fields import MDTextField

from tag.models import Tag


class Post(models.Model):
    title = models.CharField(max_length=200)
    content = MDTextField(null=True, blank=True)
    content_preview = models.TextField(null=True, blank=True)
    pub_date = models.DateTimeField("date published")
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    is_index_post = models.BooleanField(default=False)
    url = models.URLField(blank=True, null=True)
    tag = models.ForeignKey(Tag, on_delete=models.SET_NULL, null=True, blank=False)

    def __str__(self):
        return self.title


class TextAsset(models.Model):
    ASSET_TYPES = (
        ("logo", "Logo"),
        ("copyright", "Copyright"),
        ("about", "About"),
        ("contact", "Contact"),
    )
    asset_type = models.CharField(max_length=50, choices=ASSET_TYPES)
    content = models.TextField()

    def __str__(self):
        return f"{self.get_asset_type_display()}: {self.content[:50]}"


class Set(models.TextChoices):
    ORIGINS = "Origins", _("Origins")
    SPIRITFORGED = "Spiritforged", _("Spiritforged")
    PROVING_GROUNDS = "Proving Grounds", _("Proving Grounds")


class CardType(models.TextChoices):
    LEGEND = "Legend", _("Legend")
    SPELL = "Spell", _("Spell")
    UNIT = "Unit", _("Unit")
    RUNE = "Rune", _("Rune")
    GEAR = "Gear", _("Gear")
    BATTLEFIELD = "Battlefield", _("Battlefield")


class Domain(models.TextChoices):
    CHAOS = "Chaos", _("Chaos")
    ORDER = "Order", _("Order")
    FURY = "Fury", _("Fury")
    CALM = "Calm", _("Calm")
    MIND = "Mind", _("Mind")
    BODY = "Body", _("Body")
    COLORLESS = "Colorless", _("Colorless")


class Rarity(models.TextChoices):
    COMMON = "Common", _("Common")
    UNCOMMON = "Uncommon", _("Uncommon")
    RARE = "Rare", _("Rare")
    EPIC = "Epic", _("Epic")
    SHOWCASE = "Showcase", _("Showcase")


class CardDomain(models.Model):
    """Represents a domain that can be assigned to cards."""

    name = models.CharField(max_length=20, choices=Domain.choices, unique=True)

    def __str__(self):
        return self.name


class Card(models.Model):
    card_id = models.CharField(max_length=20, unique=True)  # e.g., "sfd-198-221"
    name = models.CharField(max_length=50)
    collector_number = models.IntegerField()
    energy = models.IntegerField(default=0)
    power = models.IntegerField(default=0)
    domain = models.ManyToManyField(CardDomain, related_name="cards", blank=True)
    card_type = models.CharField(
        max_length=20,
        choices=CardType.choices,
        default=CardType.UNIT,
    )
    rarity = models.CharField(
        max_length=20,
        choices=Rarity.choices,
        default=Rarity.COMMON,
    )
    card_set = models.CharField(
        max_length=20,
        choices=Set.choices,
        default=Set.ORIGINS,
    )
    image_url = models.URLField(max_length=200)
    ability = models.TextField(blank=True, default="")
    errata_text = models.TextField(blank=True, null=True)
    errata_old_text = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["card_set", "collector_number"]

    def __str__(self):
        return f"{self.name} ({self.card_id})"

    @property
    def has_errata(self):
        return bool(self.errata_text)


class RuleSection(models.Model):
    """
    Base model for rule sections (both Tournament Rules and Comprehensive Rules).
    Uses self-referential foreign key for hierarchical structure.
    """

    RULE_TYPE_CHOICES = [
        ("TR", "Tournament Rules"),
        ("CR", "Comprehensive Rules"),
    ]

    rule_type = models.CharField(max_length=2, choices=RULE_TYPE_CHOICES)
    section = models.CharField(max_length=50, db_index=True)  # e.g., "703.4.a.5"
    text = models.TextField()
    annotations = models.TextField(blank=True, default="")
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    # Order within parent for consistent display
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["rule_type", "order", "section"]
        unique_together = ["rule_type", "section"]
        indexes = [
            models.Index(fields=["rule_type", "section"]),
            models.Index(fields=["parent", "order"]),
        ]

    def __str__(self):
        return f"{self.get_rule_type_display()} {self.section}"

    def get_top_level_section(self):
        """Get the top-level section number (e.g., '700' from '703.4.a')"""
        parts = self.section.split(".")
        first_part = parts[0]
        if len(first_part) >= 3:
            return first_part[0] + "00"
        return first_part

    def has_letter(self):
        """Check if section contains a letter (a, b, c, d, e)"""
        return any(letter in self.section for letter in ["a", "b", "c", "d", "e"])

    def to_dict(self, include_children=True):
        """Convert section to dictionary format matching JSON structure"""
        data = {
            "section": self.section,
            "text": self.text,
            "annotations": self.annotations,
            "children": [],
        }

        if include_children:
            for child in self.children.all():
                data["children"].append(child.to_dict(include_children=True))

        return data
