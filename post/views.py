import json
import os

from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render

from .models import Post, Tag, TextAsset


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

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Get all trsection files
    trsections_dir = os.path.join(base_dir, "staticfiles", "trsections")
    trsections = []
    if os.path.exists(trsections_dir):
        json_files = [f for f in os.listdir(trsections_dir) if f.endswith(".json")]
        top_level_files = [f for f in json_files if "." not in f.replace(".json", "")]

        for filename in sorted(
            top_level_files, key=lambda x: int(x.replace(".json", ""))
        ):
            section = filename.replace(".json", "")
            filepath = os.path.join(trsections_dir, filename)

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    trsections.append(
                        {
                            "section": section,
                            "text": data.get("text", ""),
                            "url": f"/trsections/{section}/",
                            "children": data.get("children", []),
                        }
                    )
            except (json.JSONDecodeError, IOError):
                pass

    # Get all crsection files
    crsections_dir = os.path.join(base_dir, "staticfiles", "crsections")
    crsections = []
    if os.path.exists(crsections_dir):
        json_files = [f for f in os.listdir(crsections_dir) if f.endswith(".json")]
        top_level_files = [f for f in json_files if "." not in f.replace(".json", "")]

        for filename in sorted(
            top_level_files, key=lambda x: int(x.replace(".json", ""))
        ):
            section = filename.replace(".json", "")
            filepath = os.path.join(crsections_dir, filename)

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    crsections.append(
                        {
                            "section": section,
                            "text": data.get("text", ""),
                            "url": f"/crsections/{section}/",
                            "children": data.get("children", []),
                        }
                    )
            except (json.JSONDecodeError, IOError):
                pass

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


def format_section_text(section_data):
    """Recursively format text in section data to bold text before colons."""
    section_data["text"] = bold_before_colon(section_data["text"])
    for child in section_data.get("children", []):
        format_section_text(child)
    return section_data


def trsection_detail(request, section):
    """
    Displays a tournament rules section with links to its immediate children.

    Args:
        section: Section number (e.g., "100", "301", "301.1")
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    trsections_dir = os.path.join(base_dir, "staticfiles", "trsections")

    # Find the top-level section (first part before any dot)
    parts = section.split(".")
    first_part = parts[0]

    # Determine the top-level section (e.g., "301" -> "300", "703.5.b.1" -> "700")
    # Top-level sections are x00 where x is the hundreds digit
    if len(first_part) >= 3:
        top_level = first_part[0] + "00"
    else:
        top_level = first_part

    # Load the top-level JSON file
    file_path = os.path.join(trsections_dir, f"{top_level}.json")

    if not os.path.exists(file_path):
        raise Http404(f"Section {section} not found")

    # Read the JSON file
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        raise Http404(f"Invalid JSON in section {section}")
    except Exception as e:
        raise Http404(f"Error reading section {section}: {str(e)}")

    # If requesting a subsection (not the top-level section), navigate to it
    if section != top_level:

        def find_section(obj, target):
            if obj["section"] == target:
                return obj
            for child in obj.get("children", []):
                result = find_section(child, target)
                if result:
                    return result
            return None

        section_data = find_section(data, section)
        if not section_data:
            raise Http404(f"Section {section} not found")
        data = section_data

    # Get text assets for template
    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    copyright_asset = TextAsset.objects.filter(asset_type="copyright").first()

    # Check if this is a top-level section (x00)
    is_top_level = section == top_level

    # Format text to bold content before colons
    data = format_section_text(data)

    context = {
        "section": data,
        "json_url": f"/trsections/{top_level}/",
        "is_top_level": is_top_level,
        "logo_asset": logo_asset,
        "copyright_asset": copyright_asset,
    }

    return render(request, "trsection_detail.html", context)


def crsection_detail(request, section):
    """
    Displays a core rules section with links to its immediate children.

    Args:
        section: Section number (e.g., "100", "301", "301.1")
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    crsections_dir = os.path.join(base_dir, "staticfiles", "crsections")

    # Find the top-level section (first part before any dot)
    parts = section.split(".")
    first_part = parts[0]

    # Determine the top-level section (e.g., "301" -> "300", "703.5.b.1" -> "700")
    # Top-level sections are x00 where x is the hundreds digit
    if len(first_part) >= 3:
        top_level = first_part[0] + "00"
    else:
        top_level = first_part

    # Load the top-level JSON file
    file_path = os.path.join(crsections_dir, f"{top_level}.json")

    if not os.path.exists(file_path):
        raise Http404(f"Section {section} not found")

    # Read the JSON file
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        raise Http404(f"Invalid JSON in section {section}")
    except Exception as e:
        raise Http404(f"Error reading section {section}: {str(e)}")

    # If requesting a subsection (not the top-level section), navigate to it
    if section != top_level:

        def find_section(obj, target):
            if obj["section"] == target:
                return obj
            for child in obj.get("children", []):
                result = find_section(child, target)
                if result:
                    return result
            return None

        section_data = find_section(data, section)
        if not section_data:
            raise Http404(f"Section {section} not found")
        data = section_data

    # Get text assets for template
    logo_asset = TextAsset.objects.filter(asset_type="logo").first()
    copyright_asset = TextAsset.objects.filter(asset_type="copyright").first()

    # Check if this is a top-level section (x00)
    is_top_level = section == top_level

    context = {
        "section": data,
        "json_url": f"/crsections/{top_level}/",
        "is_top_level": is_top_level,
        "logo_asset": logo_asset,
        "copyright_asset": copyright_asset,
    }

    return render(request, "crsection_detail.html", context)
