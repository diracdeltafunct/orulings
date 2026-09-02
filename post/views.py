import json
import logging
import os
import re
from html import unescape
from difflib import SequenceMatcher

import bleach
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit

logger = logging.getLogger(__name__)

from .forms import ContactForm, ProfileForm, RoleUpdateForm, SignUpForm
from .models import (
    AnnotationProposal,
    Bookmark,
    Card,
    CardDomain,
    PersonalNote,
    Post,
    RuleSection,
    Tag,
    UserProfile,
)

ALLOWED_ANNOTATION_TAGS = [
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strike",
    "strong",
    "u",
    "ul",
]
ALLOWED_ANNOTATION_ATTRS = {
    "a": ["href", "title", "target"],
}
PERSONAL_NOTE_MAX_LENGTH = 2000


def attribution(request):
    contributors = (
        User.objects.annotate(
            accepted_contribution_count=Count(
                "annotation_proposals",
                filter=Q(
                    annotation_proposals__status=AnnotationProposal.Status.APPROVED
                ),
                distinct=True,
            )
        )
        .filter(accepted_contribution_count__gt=0)
        .order_by("first_name", "username")
    )
    return render(request, "attribution.html", {"contributors": contributors})


@ratelimit(key="ip", rate="5/h", method="POST", block=True)
def signup(request):
    if request.user.is_authenticated:
        return redirect("profile")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Your contributor account has been created.")
            return redirect("profile")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


@login_required
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("profile")
    else:
        form = ProfileForm(user=request.user)
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return render(
        request,
        "registration/profile.html",
        {"form": form, "user_profile": user_profile},
    )


@login_required
def manage_users(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("Staff access required.")
    users = User.objects.select_related("profile").order_by("username")
    return render(request, "registration/manage_users.html", {"users": users})


@login_required
def update_user_role(request, user_id):
    if not request.user.is_staff:
        return HttpResponseForbidden("Staff access required.")
    target = get_object_or_404(User, pk=user_id)
    if request.method != "POST":
        return redirect("manage_users")

    form = RoleUpdateForm(request.POST, actor=request.user, target=target)
    if form.is_valid():
        form.save()
        messages.success(request, f"Updated {target.username}'s role.")
    else:
        messages.error(request, " ".join(form.non_field_errors()))
    return redirect("manage_users")


def post_list(request):
    posts = Post.objects.filter(is_index_post=False).order_by("-pub_date")
    tags = Tag.objects.all()
    search_query = request.GET.get("q", "")

    if search_query:
        posts = posts.filter(
            Q(title__icontains=search_query) | Q(tag__name__icontains=search_query)
        )

    context = {
        "posts": posts,
        "tags": tags,
        "search_query": search_query,
    }

    return render(request, "post_list.html", context)


def post_detail(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    tags = Tag.objects.all()

    # Fetch text assets

    context = {
        "post": post,
        "tags": tags,
    }

    return render(request, "post_detail.html", context)


def blog_index(request):
    try:
        special_post = Post.objects.get(is_index_post=True)
    except Post.DoesNotExist:
        special_post = None

    # Get top-level TR sections from database
    tr_top_level = RuleSection.objects.filter(
        rule_type="TR", parent__isnull=True
    ).prefetch_related("children")

    _TR_NO_SUBS = {"000", "100", "200", "300"}
    trsections = []
    for section in tr_top_level:
        trsections.append(
            {
                "section": section.section,
                "text": section.text,
                "url": f"/tournament-rules/#rule-{section.section}",
                "subs": [] if section.section in _TR_NO_SUBS else [
                    {
                        "section": child["section"],
                        "text": child["text"],
                        "url": f"/tournament-rules/#rule-{child['section']}",
                    }
                    for child in section.children.values("section", "text")
                ],
            }
        )

    # CR index structure: fixed top-level headers with their sub-index sections
    _CR_INDEX = [
        {"top": "000", "subs": ["001", "050"]},
        {"top": "100", "subs": ["101", "104", "120", "125", "140", "147", "152", "159", "168", "172", "176", "185"]},
        {"top": "300", "subs": ["301", "318", "325", "349", "360", "407", "440", "454", "458", "462", "468", "476", "649"]},
        {"top": "700", "subs": ["701", "706", "712", "716", "720", "726", "728", "734", "739", "800"]},
    ]
    all_cr_ids = [e["top"] for e in _CR_INDEX] + [s for e in _CR_INDEX for s in e["subs"]]
    cr_map = {
        r.section: r
        for r in RuleSection.objects.filter(rule_type="CR", section__in=all_cr_ids)
    }
    crsections = []
    for entry in _CR_INDEX:
        top = cr_map.get(entry["top"])
        if not top:
            continue
        crsections.append({
            "section": top.section,
            "text": top.text,
            "url": f"/crsections/{top.section}/",
            "subs": [
                {"section": s, "text": cr_map[s].text, "url": f"/crsections/{s}/"}
                for s in entry["subs"] if s in cr_map
            ],
        })

    context = {
        "special_post": special_post,
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
    elif section_type in ("cr_single", "tr_single"):
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


def attach_user_rule_data(section_data, notes_by_section, bookmarks_by_section):
    """Attach the current user's private note and bookmark to a rule tree."""
    section_data["personal_note"] = notes_by_section.get(section_data["section"], "")
    section_data["is_bookmarked"] = section_data["section"] in bookmarks_by_section
    section_data["bookmark_note"] = bookmarks_by_section.get(
        section_data["section"], ""
    )
    for child in section_data.get("children", []):
        attach_user_rule_data(child, notes_by_section, bookmarks_by_section)
    return section_data


def get_personal_notes(request, rule_type):
    if not request.user.is_authenticated:
        return {}
    return dict(
        PersonalNote.objects.filter(
            user=request.user, rule_section__rule_type=rule_type
        ).values_list("rule_section__section", "content")
    )


def get_bookmarks(request, rule_type):
    if not request.user.is_authenticated:
        return {}
    return dict(
        Bookmark.objects.filter(
            user=request.user, rule_section__rule_type=rule_type
        ).values_list("rule_section__section", "note")
    )


_rules_last_updated_cache = {}


def get_rules_last_updated(rule_type):
    """Get the last updated date from rules metadata file."""
    if rule_type in _rules_last_updated_cache:
        return _rules_last_updated_cache[rule_type]

    import os

    if rule_type == "TR":
        metadata_path = os.path.join(
            settings.BASE_DIR, "static/metadata/tr_metadata.json"
        )
    else:
        metadata_path = os.path.join(
            settings.BASE_DIR, "static/metadata/cr_metadata.json"
        )

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            result = metadata.get("last_updated", "Unknown")
            if result != "Unknown":
                _rules_last_updated_cache[rule_type] = result
            return result
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
            "children__children__children__children__children__children"
        ).get(rule_type="TR", section=section)
    except RuleSection.DoesNotExist:
        raise Http404(f"Section {section} not found")

    # Convert to dict format
    data = section_obj.to_dict()

    # Get text assets for template

    # Get top-level section number
    top_level = section_obj.get_top_level_section()

    # Check if this is a top-level section (x00)
    is_top_level = section == top_level

    # Format text to bold content before colons and linkify references
    data = format_section_text(data, section_type="tr")
    data = attach_user_rule_data(
        data, get_personal_notes(request, "TR"), get_bookmarks(request, "TR")
    )

    # Get parent section if exists
    parent_section = None
    if section_obj.parent:
        parent_section = section_obj.parent.section

    context = {
        "section": data,
        "json_url": f"/trsections/{top_level}/",
        "is_top_level": is_top_level,
        "parent_section": parent_section,
        "last_updated": get_rules_last_updated("TR"),
    }

    response = render(request, "trsection_detail.html", context)
    if request.user.is_authenticated:
        response["Cache-Control"] = "private, no-store"
    return response


def crsection_detail(request, section):
    """
    Displays a comprehensive rules section with links to its immediate children.

    Args:
        section: Section number (e.g., "100", "301", "301.1")
    """
    # Get the section from database
    try:
        section_obj = RuleSection.objects.prefetch_related(
            "children__children__children__children__children__children"
        ).get(rule_type="CR", section=section)
    except RuleSection.DoesNotExist:
        raise Http404(f"Section {section} not found")

    # Convert to dict format
    data = section_obj.to_dict()

    # Get text assets for template

    # Get top-level section number
    top_level = section_obj.get_top_level_section()

    # Check if this is a top-level section (x00)
    is_top_level = section == top_level

    # Format text to bold content before colons and linkify references
    data = format_section_text(data, section_type="cr")
    data = attach_user_rule_data(
        data, get_personal_notes(request, "CR"), get_bookmarks(request, "CR")
    )

    # Get parent section if exists
    parent_section = None
    if section_obj.parent:
        parent_section = section_obj.parent.section

    context = {
        "section": data,
        "json_url": f"/crsections/{top_level}/",
        "is_top_level": is_top_level,
        "parent_section": parent_section,
        "last_updated": get_rules_last_updated("CR"),
    }

    response = render(request, "crsection_detail.html", context)
    if request.user.is_authenticated:
        response["Cache-Control"] = "private, no-store"
    return response


def core_rules(request):
    """
    Single-page view for all Comprehensive Rules with anchor navigation.
    """
    top_level_sections = RuleSection.objects.filter(
        rule_type="CR", parent__isnull=True
    ).prefetch_related("children__children__children__children__children__children")

    notes_by_section = get_personal_notes(request, "CR")
    bookmarks_by_section = get_bookmarks(request, "CR")
    sections = []
    for section_obj in top_level_sections:
        data = section_obj.to_dict()
        data = format_section_text(data, section_type="cr_single")
        sections.append(
            attach_user_rule_data(data, notes_by_section, bookmarks_by_section)
        )

    context = {
        "sections": sections,
        "last_updated": get_rules_last_updated("CR"),
    }

    response = render(request, "core_rules.html", context)

    # Only use browser/CDN caching for anonymous users to avoid caching admin UI
    if not request.user.is_authenticated:
        response["Cache-Control"] = "public, max-age=600"
    else:
        response["Cache-Control"] = "no-store"

    return response


def tournament_rules(request):
    """
    Single-page view for all Tournament Rules with anchor navigation.
    """
    top_level_sections = RuleSection.objects.filter(
        rule_type="TR", parent__isnull=True
    ).prefetch_related("children__children__children__children__children__children")

    notes_by_section = get_personal_notes(request, "TR")
    bookmarks_by_section = get_bookmarks(request, "TR")
    sections = []
    for section_obj in top_level_sections:
        data = section_obj.to_dict()
        data = format_section_text(data, section_type="tr_single")
        sections.append(
            attach_user_rule_data(data, notes_by_section, bookmarks_by_section)
        )

    context = {
        "sections": sections,
        "last_updated": get_rules_last_updated("TR"),
    }

    response = render(request, "tournament_rules.html", context)

    if not request.user.is_authenticated:
        response["Cache-Control"] = "public, max-age=600"
    else:
        response["Cache-Control"] = "no-store"

    return response


@login_required
def bookmarks_page(request):
    search_query = request.GET.get("q", "").strip()
    bookmarks = Bookmark.objects.filter(user=request.user).select_related("rule_section")
    if search_query:
        bookmarks = bookmarks.filter(
            Q(note__icontains=search_query)
            | Q(rule_section__section__icontains=search_query)
            | Q(rule_section__text__icontains=search_query)
        )
    response = render(
        request,
        "registration/bookmarks.html",
        {"bookmarks": bookmarks, "search_query": search_query},
    )
    response["Cache-Control"] = "private, no-store"
    return response


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


@csrf_exempt
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

        # Sanitize HTML before saving
        if annotation_html:
            annotation_html = bleach.clean(
                annotation_html,
                tags=ALLOWED_ANNOTATION_TAGS,
                attributes=ALLOWED_ANNOTATION_ATTRS,
                strip=True,
            )
        annotation_html = annotation_html or ""

        if not request.user.is_staff:
            proposal = AnnotationProposal.objects.create(
                rule_section=section_obj,
                submitted_by=request.user,
                content=annotation_html,
            )
            return JsonResponse(
                {
                    "success": True,
                    "pending": True,
                    "message": "Annotation submitted for admin approval",
                    "proposal_id": proposal.pk,
                    "section": section,
                }
            )

        # Staff and admins are trusted to publish annotation edits immediately.
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


@login_required
def annotation_review_queue(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Admin access required.")
    proposals = AnnotationProposal.objects.filter(
        status=AnnotationProposal.Status.PENDING
    ).select_related("rule_section", "submitted_by")
    return render(
        request,
        "registration/annotation_review_queue.html",
        {"proposals": proposals},
    )


@login_required
def review_annotation_proposal(request, proposal_id, action):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Admin access required.")
    if request.method != "POST":
        return redirect("annotation_review_queue")
    if action not in {"approve", "reject"}:
        raise Http404("Unknown review action")

    with transaction.atomic():
        proposal = get_object_or_404(
            AnnotationProposal.objects.select_for_update().select_related(
                "rule_section"
            ),
            pk=proposal_id,
        )
        if proposal.status != AnnotationProposal.Status.PENDING:
            messages.warning(request, "That proposal has already been reviewed.")
            return redirect("annotation_review_queue")

        if action == "approve":
            proposal.rule_section.annotations = proposal.content
            proposal.rule_section.save(update_fields=["annotations"])
            proposal.status = AnnotationProposal.Status.APPROVED
            messages.success(request, "The annotation is now public.")
        else:
            proposal.status = AnnotationProposal.Status.REJECTED
            messages.success(request, "The annotation proposal was rejected.")

        proposal.reviewed_by = request.user
        proposal.reviewed_at = timezone.now()
        proposal.save(update_fields=["status", "reviewed_by", "reviewed_at"])

    return redirect("annotation_review_queue")


def save_personal_note(request):
    """Save or clear the authenticated user's private note for a rule section."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=403)

    try:
        data = json.loads(request.body)
        rule_type = data.get("rule_type")
        section = data.get("section")
        note_html = data.get("note") or ""
        if not all([rule_type, section]):
            return JsonResponse({"error": "Missing required fields"}, status=400)

        rule_section = RuleSection.objects.get(rule_type=rule_type, section=section)
        note_html = bleach.clean(
            note_html,
            tags=ALLOWED_ANNOTATION_TAGS,
            attributes=ALLOWED_ANNOTATION_ATTRS,
            strip=True,
        )
        note_text = unescape(strip_tags(note_html)).strip()
        if len(note_text) > PERSONAL_NOTE_MAX_LENGTH:
            return JsonResponse(
                {
                    "error": (
                        "Personal notes cannot exceed "
                        f"{PERSONAL_NOTE_MAX_LENGTH} characters."
                    )
                },
                status=400,
            )
        if note_html:
            PersonalNote.objects.update_or_create(
                user=request.user,
                rule_section=rule_section,
                defaults={"content": note_html},
            )
        else:
            PersonalNote.objects.filter(
                user=request.user, rule_section=rule_section
            ).delete()
        return JsonResponse({"success": True, "section": section})
    except RuleSection.DoesNotExist:
        return JsonResponse({"error": f"Section {section} not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)


def save_bookmark(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=403)

    try:
        data = json.loads(request.body)
        rule_type = data.get("rule_type")
        section = data.get("section")
        note = (data.get("note") or "").strip()
        if not all([rule_type, section]):
            return JsonResponse({"error": "Missing required fields"}, status=400)
        if len(note) > 250:
            return JsonResponse(
                {"error": "Bookmark notes cannot exceed 250 characters."}, status=400
            )

        rule_section = RuleSection.objects.get(rule_type=rule_type, section=section)
        bookmark, _ = Bookmark.objects.update_or_create(
            user=request.user,
            rule_section=rule_section,
            defaults={"note": note},
        )
        return JsonResponse({"success": True, "bookmark_id": bookmark.pk})
    except RuleSection.DoesNotExist:
        return JsonResponse({"error": f"Section {section} not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)


def remove_bookmark(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=403)

    try:
        data = json.loads(request.body)
        rule_type = data.get("rule_type")
        section = data.get("section")
        if not all([rule_type, section]):
            return JsonResponse({"error": "Missing required fields"}, status=400)
        Bookmark.objects.filter(
            user=request.user,
            rule_section__rule_type=rule_type,
            rule_section__section=section,
        ).delete()
        return JsonResponse({"success": True})
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)


@ratelimit(key="ip", rate="30/m", method="GET", block=True)
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

    context = {
        "search_query": search_query,
        "results": results,
        "result_count": len(results),
    }

    return render(request, "search_results.html", context)


def _safe_int(value, default=None):
    """Safely convert a string to int, returning default on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


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


@ratelimit(key="ip", rate="30/m", method="GET", block=True)
def card_search(request):
    """
    Card search page with filters for all card fields.
    If only one result, redirects directly to the card detail page.
    """

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
    if energy_min and _safe_int(energy_min) is not None:
        cards = cards.filter(energy__gte=_safe_int(energy_min))
        search_performed = True
    if energy_max and _safe_int(energy_max) is not None:
        cards = cards.filter(energy__lte=_safe_int(energy_max))
        search_performed = True
    if power_min and _safe_int(power_min) is not None:
        cards = cards.filter(power__gte=_safe_int(power_min))
        search_performed = True
    if power_max and _safe_int(power_max) is not None:
        cards = cards.filter(power__lte=_safe_int(power_max))
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
            if energy_min and _safe_int(energy_min) is not None:
                cards = cards.filter(energy__gte=_safe_int(energy_min))
            if energy_max and _safe_int(energy_max) is not None:
                cards = cards.filter(energy__lte=_safe_int(energy_max))
            if power_min and _safe_int(power_min) is not None:
                cards = cards.filter(power__gte=_safe_int(power_min))
            if power_max and _safe_int(power_max) is not None:
                cards = cards.filter(power__lte=_safe_int(power_max))
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

    # Paginate results
    page_obj = None
    result_count = 0
    if search_performed:
        result_count = cards.count()
        paginator = Paginator(cards, 24)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

    # Build query string without the page param for pagination links
    query_params = request.GET.copy()
    query_params.pop("page", None)
    page_query = query_params.urlencode()

    context = {
        "cards": page_obj,
        "page_query": page_query,
        "search_performed": search_performed,
        "fuzzy_match": fuzzy_match,
        "result_count": result_count,
        "domains": domains,
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

    context = {
        "card": card,
    }

    return render(request, "card_detail.html", context)


@ratelimit(key="ip", rate="5/m", method="POST", block=True)
def contact(request):
    """Contact form page with reCAPTCHA validation."""
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
                    recipient_list=[settings.CONTACT_EMAIL],
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
        "error_message": error_message,
        "success_message": success_message,
        "recaptcha_site_key": settings.RECAPTCHA_SITE_KEY,
    }

    return render(request, "contact.html", context)


def manifest_json(request):
    return render(request, "manifest.json", content_type="application/manifest+json")


def service_worker(request):
    return render(request, "sw.js", content_type="application/javascript")


def offline_page(request):
    return render(request, "offline.html")


def resume(request):
    return render(request, "resume.html")


def resume_download(request):
    path = os.path.join(settings.BASE_DIR, "static", "resume", "muckle_resume.pdf")
    response = FileResponse(open(path, "rb"), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="muckle_resume.pdf"'
    return response


@ratelimit(key="ip", rate="30/m", method="GET", block=True)
def api_rule(request, rule_type, section):
    """
    Return a single rule section as JSON.

    rule_type: 'cr' or 'tr' (case-insensitive)
    section:   rule number, e.g. '703', '703.4', '703.4.a'
    """
    rt = rule_type.upper()
    if rt not in ("CR", "TR"):
        return JsonResponse({"error": "Invalid rule type. Use 'cr' or 'tr'."}, status=400)

    try:
        section_obj = RuleSection.objects.prefetch_related(
            "children__children__children__children__children__children"
        ).get(rule_type=rt, section=section)
    except RuleSection.DoesNotExist:
        return JsonResponse({"error": f"Section {section} not found."}, status=404)

    data = section_obj.to_dict()
    data["rule_type"] = rt
    if rt == "CR":
        data["url"] = request.build_absolute_uri(f"/core-rules/#rule-{section}")
    else:
        data["url"] = request.build_absolute_uri(f"/trsections/{section}/")
    return JsonResponse(data)


@cache_page(60 * 60)
def api_cards_all(request):
    cards = Card.objects.prefetch_related("domain").all()
    data = []
    for card in cards:
        data.append(
            {
                "card_id": card.card_id,
                "name": card.name,
                "collector_number": card.collector_number,
                "energy": card.energy,
                "power": card.power,
                "card_type": card.card_type,
                "rarity": card.rarity,
                "card_set": card.card_set,
                "image_url": card.image_url,
                "ability": card.ability,
                "errata_text": card.errata_text,
                "domains": [d.name for d in card.domain.all()],
            }
        )
    return JsonResponse(data, safe=False)


# Mapping of rule_type -> (old_dir, new_dir, old_label, new_label)
_RULES_SOURCE = os.path.join(settings.BASE_DIR, "rules_source")

def _get_available_versions(rule_type):
    """Scan rules_source/ for version directories, return list sorted oldest→newest."""
    from datetime import date as _date
    prefix = "trsections" if rule_type == "tr" else "crsections"
    live_dir = prefix  # exact name "trsections" / "crsections" is the live copy — skip it
    versions = []
    for name in os.listdir(_RULES_SOURCE):
        if not name.startswith(prefix) or name == live_dir:
            continue
        dir_path = os.path.join(_RULES_SOURCE, name)
        if not os.path.isdir(dir_path):
            continue
        metadata_path = os.path.join(dir_path, "metadata.json")
        if not os.path.exists(metadata_path):
            continue
        try:
            with open(metadata_path, encoding="utf-8") as f:
                meta = json.load(f)
            d = _date.fromisoformat(meta["last_updated"])
            versions.append({"dir": name, "date": d, "label": d.strftime("%B %Y")})
        except Exception:
            continue
    versions.sort(key=lambda v: v["date"])
    return versions


_TYPOGRAPHIC_NORM = str.maketrans({
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote / apostrophe
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
    "\u2013": "-",  # en dash
    "\u2014": "--", # em dash
    "\ufffd": "",   # replacement character (encoding artefact)
})


def _norm(text):
    """Normalise typographic punctuation so cosmetic encoding differences are ignored."""
    return text.translate(_TYPOGRAPHIC_NORM)


def _section_sort_key(section):
    parts = section.split(".")
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return key


def _load_ordered_rules(directory):
    """Load all rule JSON files in document order, returning [(section, text), ...]."""
    result = []
    if not os.path.isdir(directory):
        return result
    filenames = [f for f in os.listdir(directory) if f.endswith(".json") and f != "metadata.json"]
    filenames.sort(key=lambda f: _section_sort_key(f[:-5]))
    for filename in filenames:
        filepath = os.path.join(directory, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        _flatten_rule_node_ordered(data, result)
    return result


def _flatten_rule_node_ordered(node, result):
    result.append((node["section"], node.get("text", "")))
    for child in node.get("children", []):
        _flatten_rule_node_ordered(child, result)


def _word_diff_html(old_text, new_text):
    """Return (old_html, new_html) with word-level changes highlighted."""
    old_words = old_text.split()
    new_words = new_text.split()
    matcher = SequenceMatcher(None, old_words, new_words)
    old_parts = []
    new_parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            chunk = " ".join(old_words[i1:i2])
            old_parts.append(chunk)
            new_parts.append(chunk)
        elif tag == "replace":
            old_parts.append('<mark class="diff-del">' + " ".join(old_words[i1:i2]) + "</mark>")
            new_parts.append('<mark class="diff-ins">' + " ".join(new_words[j1:j2]) + "</mark>")
        elif tag == "delete":
            old_parts.append('<mark class="diff-del">' + " ".join(old_words[i1:i2]) + "</mark>")
        elif tag == "insert":
            new_parts.append('<mark class="diff-ins">' + " ".join(new_words[j1:j2]) + "</mark>")
    return " ".join(old_parts), " ".join(new_parts)


def rules_diff(request, rule_type):
    """Display a side-by-side diff of two versions of a rules document."""
    rt = rule_type.lower()
    versions = _get_available_versions(rt)
    if len(versions) < 2:
        return render(request, "rules_diff.html", {
            "rule_type": rule_type.upper(),
            "no_diff": True,
        })

    valid_dirs = {v["dir"] for v in versions}
    old_dir_name = request.GET.get("old", versions[-2]["dir"])
    new_dir_name = request.GET.get("new", versions[-1]["dir"])
    if old_dir_name not in valid_dirs:
        old_dir_name = versions[-2]["dir"]
    if new_dir_name not in valid_dirs:
        new_dir_name = versions[-1]["dir"]

    old_label = next(v["label"] for v in versions if v["dir"] == old_dir_name)
    new_label = next(v["label"] for v in versions if v["dir"] == new_dir_name)

    old_items = _load_ordered_rules(os.path.join(_RULES_SOURCE, old_dir_name))
    new_items = _load_ordered_rules(os.path.join(_RULES_SOURCE, new_dir_name))

    old_texts = [_norm(t) for _, t in old_items]
    new_texts = [_norm(t) for _, t in new_items]

    matcher = SequenceMatcher(None, old_texts, new_texts, autojunk=False)
    all_items = []
    n_added = n_removed = n_changed = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for (old_sec, old_text), (new_sec, new_text) in zip(old_items[i1:i2], new_items[j1:j2]):
                all_items.append({
                    "old_section": old_sec,
                    "new_section": new_sec,
                    "kind": "unchanged",
                    "old_html": _norm(old_text),
                    "new_html": _norm(new_text),
                })
        elif tag == "replace":
            old_chunk = old_items[i1:i2]
            new_chunk = new_items[j1:j2]
            for idx in range(max(len(old_chunk), len(new_chunk))):
                if idx < len(old_chunk) and idx < len(new_chunk):
                    old_sec, old_text = old_chunk[idx]
                    new_sec, new_text = new_chunk[idx]
                    old_html, new_html = _word_diff_html(_norm(old_text), _norm(new_text))
                    all_items.append({
                        "old_section": old_sec,
                        "new_section": new_sec,
                        "kind": "changed",
                        "old_html": old_html,
                        "new_html": new_html,
                    })
                    n_changed += 1
                elif idx < len(old_chunk):
                    old_sec, old_text = old_chunk[idx]
                    all_items.append({
                        "old_section": old_sec,
                        "new_section": "",
                        "kind": "removed",
                        "old_html": _norm(old_text),
                        "new_html": "",
                    })
                    n_removed += 1
                else:
                    new_sec, new_text = new_chunk[idx]
                    all_items.append({
                        "old_section": "",
                        "new_section": new_sec,
                        "kind": "added",
                        "old_html": "",
                        "new_html": _norm(new_text),
                    })
                    n_added += 1
        elif tag == "delete":
            for old_sec, old_text in old_items[i1:i2]:
                all_items.append({
                    "old_section": old_sec,
                    "new_section": "",
                    "kind": "removed",
                    "old_html": _norm(old_text),
                    "new_html": "",
                })
                n_removed += 1
        elif tag == "insert":
            for new_sec, new_text in new_items[j1:j2]:
                all_items.append({
                    "old_section": "",
                    "new_section": new_sec,
                    "kind": "added",
                    "old_html": "",
                    "new_html": _norm(new_text),
                })
                n_added += 1

    return render(request, "rules_diff.html", {
        "rule_type": rule_type.upper(),
        "old_label": old_label,
        "new_label": new_label,
        "old_dir_name": old_dir_name,
        "new_dir_name": new_dir_name,
        "versions": versions,
        "all_items": all_items,
        "n_added": n_added,
        "n_removed": n_removed,
        "n_changed": n_changed,
        "no_diff": False,
    })
