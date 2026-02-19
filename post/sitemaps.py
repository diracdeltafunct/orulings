from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Card, RuleSection


class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return ["blog_index", "card_search", "core_rules", "contact"]

    def location(self, item):
        return reverse(item)


class CardSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return Card.objects.all()

    def location(self, obj):
        return reverse("card_detail", kwargs={"card_id": obj.card_id})


class TRSectionSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return RuleSection.objects.filter(rule_type="TR", parent__isnull=True)

    def location(self, obj):
        return reverse("trsection_detail", kwargs={"section": obj.section})


class CRSectionSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return RuleSection.objects.filter(rule_type="CR", parent__isnull=True)

    def location(self, obj):
        return reverse("crsection_detail", kwargs={"section": obj.section})
