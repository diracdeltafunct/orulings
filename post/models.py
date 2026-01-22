# post/models.py
from django.contrib.auth.models import User
from django.db import models
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
