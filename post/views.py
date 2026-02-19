import json
import re
from difflib import SequenceMatcher

import requests
from django.conf import settings
from django.contrib.auth import authenticate, login
from django.core.mail import send_mail
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ContactForm
from .models import Card, CardDomain, Post, RuleSection, Tag, TextAsset


def post_list(request):
    posts = Post.objects.filter(is_index_post=False).order_by("-pub_date")
    tags = Tag.objects.all()
    search_query = request.GET.get("q", "")

    if search_query:
        posts = posts.filter(
            Q(title__icontains=search_query) | Q(tag__name__icontains=search_query)
        )

    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    copyright_asset = TextAsset.objects.filter(asset_type="copyright").first()

    context = {
        "posts": posts,
        "tags": tags,
        "search_query": search_query,
        "logo_asset": logo_asset,
        "copyright_asset": copyright_asset,
    }

    return render(request, "post_list.html", context)


def post_detail(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    tags = Tag.objects.all()

    # Fetch text assets
    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    copyright_asset = TextAsset.objects.filter(asset_type="copyright").first()

    context = {
        "post": post,
        "tags": tags,
        "logo_asset": logo_asset,
        "copyright_asset": copyright_asset,
    }

    return render(request, "post_detail.html", context)


def blog_index(request):
    try:
        special_post = Post.objects.get(is_index_post=True)
    except Post.DoesNotExist:
        special_post = None
    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    copyright_asset = TextAsset.objects.filter(asset_type="copyright").first()

    # Get top-level TR sections from database
    tr_top_level = RuleSection.objects.filter(
        rule_type="TR", parent__isnull=True
    ).prefetch_related("children")

    trsections = []
    for section in tr_top_level:
        trsections.append(
            {
                "section": section.section,
                "text": section.text,
                "url": f"/trsections/{section.section}/",
                "children": list(section.children.values("section", "text")),
            }
        )

    # Get top-level CR sections from database
    cr_top_level = RuleSection.objects.filter(
        rule_type="CR", parent__isnull=True
    ).prefetch_related("children")

    crsections = []
    for section in cr_top_level:
        crsections.append(
            {
                "section": section.section,
                "text": section.text,
                "url": f"/crsections/{section.section}/",
                "children": list(section.children.values("section", "text")),
            }
        )

    context = {
        "special_post": special_post,
        "logo_asset": logo_asset,
        "copyright_asset": copyright_asset,
        "trsections": trsections,
        "crsections": crsections,
        "tr_last_updated": get_rules_last_updated("TR"),
        "cr_last_updated": get_rules_last_updated("CR"),
    }
    return render(request, "blog_index.html", context)


def bold_before_colon(text):
    """Helper function to bold text before first colon."""
    if ":" in text:
        parts = text.split(":", 1)
        return f"<strong>{parts[0]}:</strong>{parts[1]}"
    return text


def linkify_references(text, section_type="tr"):
    """
    Convert rule references in text to hyperlinks.

    Args:
        text: The text to process
        section_type: Either 'tr' (tournament rules) or 'cr' (comprehensive rules)

    Returns:
        Text with references converted to HTML links
    """
    # Handle CR references (e.g., "See CR 127" or "CR 127.")
    if section_type == "cr_single":
        cr_link = r'<a href="#rule-\1">CR \1</a>'
    else:
        cr_link = r'<a href="/crsections/\1/">CR \1</a>'
    text = re.sub(
        r"\bCR\s+(\d{3}(?:\.\d+)*(?:\.[a-zA-Z])?(?:\.\d+)*)\b\.?",
        cr_link,
        text,
    )

    # Handle regular section references (e.g., "See 402" or "rule 703.4")
    # Match patterns like "See 402", "see 703.4.a", "rule 318", etc.
    if section_type == "tr":
        base_url = "/trsections/"
    elif section_type == "cr_single":
        base_url = None
    else:
        base_url = "/crsections/"

    # Match section numbers that appear after words like "See", "see", "rule", "Rule", "section", "Section"
    # or standalone section numbers that look like references
    if base_url is None:
        text = re.sub(
            r"\b(See|see|rule|Rule|section|Section)\s+(\d{3}(?:\.\d+)*(?:\.[a-zA-Z])?(?:\.\d+)*)\b",
            r'\1 <a href="#rule-\2">\2</a>',
            text,
        )
    else:
        text = re.sub(
            r"\b(See|see|rule|Rule|section|Section)\s+(\d{3}(?:\.\d+)*(?:\.[a-zA-Z])?(?:\.\d+)*)\b",
            rf'\1 <a href="{base_url}\2/">\2</a>',
            text,
        )

    return text


def format_section_text(section_data, section_type="tr"):
    """
    Recursively format text in section data to bold text before colons and linkify references.

    Args:
        section_data: The section data dictionary
        section_type: Either 'tr' or 'cr' to determine link targets
    """
    # Always linkify the main section text
    section_data["text"] = linkify_references(section_data["text"], section_type)
    section_data["text"] = bold_before_colon(section_data["text"])

    # For children, check if they will be rendered as clickable links
    for child in section_data.get("children", []):
        child_section_str = child.get("section", "")
        has_letter = any(
            letter in child_section_str for letter in ["a", "b", "c", "d", "e"]
        )
        has_children = len(child.get("children", [])) > 0
        will_be_clickable_link = has_children and not has_letter

        # Only linkify child references if child won't be rendered as a clickable link
        if not will_be_clickable_link:
            child["text"] = linkify_references(child["text"], section_type)
        child["text"] = bold_before_colon(child["text"])

        # Recursively format grandchildren
        for grandchild in child.get("children", []):
            format_section_text(grandchild, section_type)

    return section_data


def get_rules_last_updated(rule_type):
    """Get the last updated date from rules metadata file."""
    import os

    if rule_type == "TR":
        metadata_path = os.path.join(
            settings.BASE_DIR, "staticfiles/trsections_january_2026/metadata.json"
        )
    else:
        metadata_path = os.path.join(
            settings.BASE_DIR, "staticfiles/crsections/metadata.json"
        )

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            return metadata.get("last_updated", "Unknown")
    except (FileNotFoundError, json.JSONDecodeError):
        return "Unknown"


def trsection_detail(request, section):
    """
    Displays a tournament rules section with links to its immediate children.

    Args:
        section: Section number (e.g., "100", "301", "301.1")
    """
    # Get the section from database
    try:
        section_obj = RuleSection.objects.prefetch_related(
            "children__children__children__children"
        ).get(rule_type="TR", section=section)
    except RuleSection.DoesNotExist:
        raise Http404(f"Section {section} not found")

    # Convert to dict format
    data = section_obj.to_dict()

    # Get text assets for template
    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    copyright_asset = TextAsset.objects.filter(asset_type="copyright").first()

    # Get top-level section number
    top_level = section_obj.get_top_level_section()

    # Check if this is a top-level section (x00)
    is_top_level = section == top_level

    # Format text to bold content before colons and linkify references
    data = format_section_text(data, section_type="tr")

    # Get parent section if exists
    parent_section = None
    if section_obj.parent:
        parent_section = section_obj.parent.section

    context = {
        "section": data,
        "json_url": f"/trsections/{top_level}/",
        "is_top_level": is_top_level,
        "parent_section": parent_section,
        "logo_asset": logo_asset,
        "copyright_asset": copyright_asset,
        "last_updated": get_rules_last_updated("TR"),
    }

    return render(request, "trsection_detail.html", context)


def crsection_detail(request, section):
    """
    Displays a comprehensive rules section with links to its immediate children.

    Args:
        section: Section number (e.g., "100", "301", "301.1")
    """
    # Get the section from database
    try:
        section_obj = RuleSection.objects.prefetch_related(
            "children__children__children__children"
        ).get(rule_type="CR", section=section)
    except RuleSection.DoesNotExist:
        raise Http404(f"Section {section} not found")

    # Convert to dict format
    data = section_obj.to_dict()

    # Get text assets for template
    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    copyright_asset = TextAsset.objects.filter(asset_type="copyright").first()

    # Get top-level section number
    top_level = section_obj.get_top_level_section()

    # Check if this is a top-level section (x00)
    is_top_level = section == top_level

    # Format text to bold content before colons and linkify references
    data = format_section_text(data, section_type="cr")

    # Get parent section if exists
    parent_section = None
    if section_obj.parent:
        parent_section = section_obj.parent.section

    context = {
        "section": data,
        "json_url": f"/crsections/{top_level}/",
        "is_top_level": is_top_level,
        "parent_section": parent_section,
        "logo_asset": logo_asset,
        "copyright_asset": copyright_asset,
        "last_updated": get_rules_last_updated("CR"),
    }

    return render(request, "crsection_detail.html", context)


def core_rules(request):
    """
    Single-page view for all Comprehensive Rules with anchor navigation.
    """
    top_level_sections = RuleSection.objects.filter(
        rule_type="CR", parent__isnull=True
    ).prefetch_related("children__children__children__children")

    sections = []
    for section_obj in top_level_sections:
        data = section_obj.to_dict()
        data = format_section_text(data, section_type="cr_single")
        sections.append(data)

    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    copyright_asset = TextAsset.objects.filter(asset_type="copyright").first()

    context = {
        "sections": sections,
        "logo_asset": logo_asset,
        "copyright_asset": copyright_asset,
        "last_updated": get_rules_last_updated("CR"),
    }

    return render(request, "core_rules.html", context)


def secret_login(request):
    """Secret admin login page"""
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            # Redirect to admin page after successful login
            return redirect("/admin/")
        else:
            # Return to login page with error
            return render(
                request, "secret_login.html", {"error": "Invalid credentials"}
            )

    # GET request - show login form
    return render(request, "secret_login.html")


def save_annotation(request):
    """
    AJAX endpoint to save annotations for a rule section.
    Requires user to be authenticated.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=403)

    try:
        data = json.loads(request.body)
        rule_type = data.get("rule_type")
        section = data.get("section")
        annotation_html = data.get("annotation")

        if not all([rule_type, section]):
            return JsonResponse({"error": "Missing required fields"}, status=400)

        # Get the section from database
        section_obj = RuleSection.objects.get(rule_type=rule_type, section=section)

        # Update the annotations field
        section_obj.annotations = annotation_html
        section_obj.save()

        return JsonResponse(
            {
                "success": True,
                "message": "Annotation saved successfully",
                "section": section,
            }
        )

    except RuleSection.DoesNotExist:
        return JsonResponse({"error": f"Section {section} not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def search_rules(request):
    """
    Search view for rule sections (both TR and CR).
    Searches in section numbers, text, and annotations.
    """
    search_query = request.GET.get("q", "")
    results = []

    if search_query:
        # Search in both TR and CR sections
        results = (
            RuleSection.objects.filter(
                Q(section__icontains=search_query)
                | Q(text__icontains=search_query)
                | Q(annotations__icontains=search_query)
            )
            .select_related("parent")
            .order_by("rule_type", "order")[:50]
        )  # Limit to 50 results

    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    copyright_asset = TextAsset.objects.filter(asset_type="copyright").first()

    context = {
        "search_query": search_query,
        "results": results,
        "result_count": len(results),
        "logo_asset": logo_asset,
        "copyright_asset": copyright_asset,
    }

    return render(request, "search_results.html", context)


def _fuzzy_name_match(query, card_names, cutoff=0.75):
    """Return card names that fuzzy-match the query, sorted by relevance."""
    clean_query = re.sub(r"[^a-z0-9 ]", "", query.lower())
    if not clean_query:
        return []
    scored = []
    for name in card_names:
        clean_name = re.sub(r"[^a-z0-9 ]", "", name.lower())
        # Substring match on punctuation-stripped name
        if clean_query in clean_name:
            scored.append((name, 1.0))
            continue
        # Score against each word and the full name
        best = SequenceMatcher(None, clean_query, clean_name).ratio()
        for word in clean_name.split():
            best = max(best, SequenceMatcher(None, clean_query, word).ratio())
        if best >= cutoff:
            scored.append((name, best))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in scored]


def card_search(request):
    """
    Card search page with filters for all card fields.
    If only one result, redirects directly to the card detail page.
    """
    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    copyright_asset = TextAsset.objects.filter(asset_type="copyright").first()

    # Get filter parameters
    name = request.GET.get("name", "").strip()
    card_type = request.GET.get("card_type", "")
    card_set = request.GET.get("card_set", "")
    rarity = request.GET.get("rarity", "")
    domain = request.GET.get("domain", "")
    energy_min = request.GET.get("energy_min", "")
    energy_max = request.GET.get("energy_max", "")
    power_min = request.GET.get("power_min", "")
    power_max = request.GET.get("power_max", "")
    ability = request.GET.get("ability", "").strip()
    has_errata = request.GET.get("has_errata", "")

    # Start with all cards
    cards = Card.objects.all()
    search_performed = False

    # Apply filters
    if name:
        cards = cards.filter(name__icontains=name)
        search_performed = True
    if card_type:
        cards = cards.filter(card_type=card_type)
        search_performed = True
    if card_set:
        cards = cards.filter(card_set=card_set)
        search_performed = True
    if rarity:
        cards = cards.filter(rarity=rarity)
        search_performed = True
    if domain:
        cards = cards.filter(domain__name=domain)
        search_performed = True
    if energy_min:
        cards = cards.filter(energy__gte=int(energy_min))
        search_performed = True
    if energy_max:
        cards = cards.filter(energy__lte=int(energy_max))
        search_performed = True
    if power_min:
        cards = cards.filter(power__gte=int(power_min))
        search_performed = True
    if power_max:
        cards = cards.filter(power__lte=int(power_max))
        search_performed = True
    if ability:
        cards = cards.filter(ability__icontains=ability)
        search_performed = True
    if has_errata == "yes":
        cards = cards.exclude(errata_text__isnull=True).exclude(errata_text="")
        search_performed = True
    elif has_errata == "no":
        cards = cards.filter(Q(errata_text__isnull=True) | Q(errata_text=""))
        search_performed = True

    # Get distinct results
    cards = cards.distinct()

    # If only one result, redirect to card detail
    if search_performed and cards.count() == 1:
        return redirect("card_detail", card_id=cards.first().card_id)

    # Fuzzy fallback when name search returns no results
    fuzzy_match = False
    if search_performed and cards.count() == 0 and name:
        all_names = list(Card.objects.values_list("name", flat=True).distinct())
        matched_names = _fuzzy_name_match(name, all_names)
        if matched_names:
            cards = Card.objects.filter(name__in=matched_names)
            # Re-apply non-name filters
            if card_type:
                cards = cards.filter(card_type=card_type)
            if card_set:
                cards = cards.filter(card_set=card_set)
            if rarity:
                cards = cards.filter(rarity=rarity)
            if domain:
                cards = cards.filter(domain__name=domain)
            if energy_min:
                cards = cards.filter(energy__gte=int(energy_min))
            if energy_max:
                cards = cards.filter(energy__lte=int(energy_max))
            if power_min:
                cards = cards.filter(power__gte=int(power_min))
            if power_max:
                cards = cards.filter(power__lte=int(power_max))
            if ability:
                cards = cards.filter(ability__icontains=ability)
            if has_errata == "yes":
                cards = cards.exclude(errata_text__isnull=True).exclude(errata_text="")
            elif has_errata == "no":
                cards = cards.filter(Q(errata_text__isnull=True) | Q(errata_text=""))
            cards = cards.distinct()
            if cards.exists():
                fuzzy_match = True

    # Get choices for dropdowns
    domains = CardDomain.objects.all().order_by("name")

    context = {
        "cards": cards if search_performed else None,
        "search_performed": search_performed,
        "fuzzy_match": fuzzy_match,
        "result_count": cards.count() if search_performed else 0,
        "domains": domains,
        "logo_asset": logo_asset,
        "copyright_asset": copyright_asset,
        # Pass back filter values for form
        "filter_name": name,
        "filter_card_type": card_type,
        "filter_card_set": card_set,
        "filter_rarity": rarity,
        "filter_domain": domain,
        "filter_energy_min": energy_min,
        "filter_energy_max": energy_max,
        "filter_power_min": power_min,
        "filter_power_max": power_max,
        "filter_ability": ability,
        "filter_has_errata": has_errata,
    }

    return render(request, "card_search.html", context)


def card_detail(request, card_id):
    """
    Card detail page showing card image and all data fields.
    """
    card = get_object_or_404(Card, card_id=card_id)

    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    copyright_asset = TextAsset.objects.filter(asset_type="copyright").first()

    context = {
        "card": card,
        "logo_asset": logo_asset,
        "copyright_asset": copyright_asset,
    }

    return render(request, "card_detail.html", context)


def contact(request):
    """Contact form page with reCAPTCHA validation."""
    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    error_message = None
    success_message = None

    if request.method == "POST":
        form = ContactForm(request.POST)

        # Verify reCAPTCHA
        recaptcha_response = request.POST.get("g-recaptcha-response")
        recaptcha_data = {
            "secret": settings.RECAPTCHA_SECRET_KEY,
            "response": recaptcha_response,
        }
        recaptcha_verify = requests.post(
            "https://www.google.com/recaptcha/api/siteverify", data=recaptcha_data
        )
        recaptcha_result = recaptcha_verify.json()

        if not recaptcha_result.get("success"):
            error_message = "reCAPTCHA verification failed. Please try again."
        elif form.is_valid():
            # Send email
            name = form.cleaned_data["name"]
            contact_type = form.cleaned_data["contact_type"]
            contact_info = form.cleaned_data["contact_info"]
            reason = form.cleaned_data["reason"]
            message = form.cleaned_data["message"]

            # Build email content
            email_subject = f"[ScoutsCode Contact] {reason.title()} from {name}"
            email_body = f"""New contact form submission:

Name: {name}
Contact Type: {contact_type.title()}
Contact Info: {contact_info}
Reason: {reason.title()}

Message:
{message}
"""

            try:
                send_mail(
                    subject=email_subject,
                    message=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=["diracdeltafunct@gmail.com"],
                    fail_silently=False,
                )
                success_message = "Your message has been sent successfully!"
                form = ContactForm()  # Reset form on success
            except Exception:
                error_message = "Failed to send message. Please try again later."
    else:
        form = ContactForm()

    context = {
        "form": form,
        "logo_asset": logo_asset,
        "error_message": error_message,
        "success_message": success_message,
        "recaptcha_site_key": settings.RECAPTCHA_SITE_KEY,
    }

    return render(request, "contact.html", context)
