import json
import re

from django.contrib.auth import authenticate, login
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Post, RuleSection, Tag, TextAsset


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
    text = re.sub(
        r"\bCR\s+(\d{3}(?:\.\d+)*(?:\.[a-zA-Z])?(?:\.\d+)*)\b\.?",
        r'<a href="/crsections/\1/">CR \1</a>',
        text,
    )

    # Handle regular section references (e.g., "See 402" or "rule 703.4")
    # Match patterns like "See 402", "see 703.4.a", "rule 318", etc.
    if section_type == "tr":
        base_url = "/trsections/"
    else:
        base_url = "/crsections/"

    # Match section numbers that appear after words like "See", "see", "rule", "Rule", "section", "Section"
    # or standalone section numbers that look like references
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
    }

    return render(request, "crsection_detail.html", context)


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
