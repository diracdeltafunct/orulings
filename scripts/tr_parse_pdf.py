"""
PDF-based parser for Riftbound Tournament Rules.

Extracts rule sections from a PDF, skipping any strikethrough text
(which represents removed/replaced rules in change-tracked documents).

Usage:
    python tr_parse_pdf.py --pdf path/to/rules.pdf --output-dir ../staticfiles/trsections_march_2026
    python tr_parse_pdf.py --url https://example.com/rules.pdf --output-dir ../staticfiles/trsections_march_2026
"""

import argparse
import json
import os
import re
import urllib.request

import fitz  # PyMuPDF

# Reuse data structures and save logic from tr_parse
from tr_parse import Line, parse_lines_to_objects, save_lines_to_files, save_metadata

PDF_URL = "https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/d77651bcaa7ca5a5b41a0ac0ea8112725a635680.pdf"

# Section number pattern: "703.4.a.1. text" or "100. text"
SECTION_PATTERN = re.compile(r"^(?:\d+|[a-zA-Z])(?:\.(?:\d+|[a-zA-Z]))*\.\s")

# Some PDF sections omit the trailing period: "602.1.a.1 text" → needs normalising.
# Require at least 3 components (2 dots) to avoid false positives on bare numbers.
NO_PERIOD_SECTION = re.compile(r"^((?:\d+|[a-zA-Z])(?:\.(?:\d+|[a-zA-Z])){2,})\s+(.+)$")

# Characters to normalise (PDF ligatures / special encodings)
CHAR_REPLACEMENTS = {
    "\ufb01": "fi",  # fi ligature
    "\ufb02": "fl",  # fl ligature
    "\u2019": "'",
    "\u2018": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "--",
    "\ufffd": "",    # replacement char from encoding issues
    "\u00e2\u0080\u0099": "'",  # multi-byte artefact
}


def normalise_text(text):
    for char, replacement in CHAR_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    return text


def is_strikethrough(line_bbox, st_rects):
    """Return True if any strikethrough rect overlaps this text line."""
    x0, y0, x1, y1 = line_bbox
    for sr in st_rects:
        if (y0 - 1 <= sr.y0 <= y1 + 1          # y of line crosses the strike line
                and sr.x0 < x1 and sr.x1 > x0):  # x ranges overlap
            return True
    return False


def get_strikethrough_rects(page):
    """
    Return thin black horizontal lines that are NOT full-page-width separators.
    Full-width separators run from ~x=36 to ~x=575 (width ~539).
    Strikethrough lines are narrower and positioned over specific text spans.
    """
    st_rects = []
    for d in page.get_drawings():
        r = d["rect"]
        is_thin = r.height < 1.5
        is_wide_enough = r.width > 5
        is_full_width = r.x0 <= 40 and r.x1 >= 570
        is_black = d.get("color") == (0.0, 0.0, 0.0)
        if is_thin and is_wide_enough and not is_full_width and is_black:
            st_rects.append(r)
    return st_rects


def extract_rows_from_page(page):
    """
    Extract text rows from a PDF page, skipping struck-through content.

    The PDF uses a 2-column table layout:
      - Left column (x ≈ 36–130): section number (e.g. "703.4.a.1.")
      - Right column (x ≈ 130+): rule text

    Lines at the same y-position belong to the same logical row and are
    combined in left-to-right order.

    Returns a list of non-empty combined row strings.
    """
    st_rects = get_strikethrough_rects(page)

    # Group spans by y-bucket (round to nearest 2px to handle micro-offsets)
    y_buckets = {}
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            bbox = line["bbox"]
            line_text = "".join(s["text"] for s in line["spans"])
            line_text = normalise_text(line_text).rstrip()
            if not line_text.strip():
                continue

            if is_strikethrough(bbox, st_rects):
                continue

            y_key = round(bbox[1] / 2) * 2
            if y_key not in y_buckets:
                y_buckets[y_key] = []
            y_buckets[y_key].append((bbox[0], line_text))

    rows = []
    for y_key in sorted(y_buckets.keys()):
        spans = sorted(y_buckets[y_key], key=lambda t: t[0])
        combined = " ".join(t[1].strip() for t in spans if t[1].strip())
        if not combined:
            continue
        # If the leftmost span is in the text column (x > 80), not the section-number
        # column (x ≈ 36-80), this row is a continuation line even if it starts with
        # something that looks like a section number (e.g. a cross-reference like "702.10.").
        # Prepend a space so join_continuation_lines won't treat it as a new section.
        leftmost_x = spans[0][0]
        if leftmost_x > 80:
            combined = " " + combined
        rows.append(combined)

    return rows


def join_continuation_lines(rows):
    """
    PDF wraps long rule text across multiple physical lines.  Rejoin them:
    a continuation line is one that does NOT start with a section-number pattern.

    Also normalises sections that are missing their trailing period
    (e.g. "602.1.a.1 text" → "602.1.a.1. text").
    """
    result = []
    for row in rows:
        # A leading space means this row originated in the text column (not the
        # section-number column), so treat it as a continuation regardless of content.
        is_text_column = row.startswith(" ")
        stripped = row.strip()
        if not stripped:
            continue
        if not is_text_column and SECTION_PATTERN.match(stripped):
            result.append(stripped)
        else:
            # Check for multi-component section number without trailing period
            m = NO_PERIOD_SECTION.match(stripped)
            if m and not is_text_column:
                result.append(f"{m.group(1)}. {m.group(2)}")
            elif result:
                result[-1] = result[-1] + " " + stripped
            # else: pre-section header text (title, "Last Updated") — discard
    return result


def extract_text_from_pdf(pdf_path):
    """Open PDF and return a single text string ready for parse_lines_to_objects()."""
    doc = fitz.open(pdf_path)
    all_rows = []
    for page in doc:
        all_rows.extend(extract_rows_from_page(page))

    joined = join_continuation_lines(all_rows)
    return "\n".join(joined)


def download_pdf(url, dest_path):
    print(f"Downloading PDF from: {url}")
    urllib.request.urlretrieve(url, dest_path)
    print(f"Saved to: {dest_path}")


def parse_and_save_pdf(pdf_path, output_dir, source_url=""):
    print(f"Parsing PDF: {pdf_path}")
    text = extract_text_from_pdf(pdf_path)

    # Debug: show first 20 parsed lines
    lines_preview = text.splitlines()[:20]
    print("\nFirst 20 extracted lines:")
    for ln in lines_preview:
        print(f"  {ln[:120]}")

    print(f"\nParsing into section objects...")
    lines = parse_lines_to_objects(text)

    print(f"Saving {len(lines)} top-level sections to: {output_dir}")
    save_lines_to_files(lines, output_dir)
    save_metadata(output_dir, source_url)

    print("\nTop-level sections:")
    for line in lines:
        print(f"  {line.section}. {line.text[:60]} ({len(line.children)} children)")

    return lines


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse Riftbound TR PDF into JSON sections")
    parser.add_argument("--pdf", type=str, help="Path to local PDF file")
    parser.add_argument("--url", type=str, default=PDF_URL, help="URL to download PDF from")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="../rules_source/trsections_march_2026",
        help="Output directory (relative to script location)",
    )
    parser.add_argument(
        "--source-url",
        type=str,
        default=PDF_URL,
        help="Source URL to store in metadata",
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    if args.pdf:
        pdf_path = args.pdf
    else:
        pdf_path = os.path.join(script_dir, "new_tr.pdf")
        if not os.path.exists(pdf_path):
            download_pdf(args.url, pdf_path)

    parse_and_save_pdf(pdf_path, args.output_dir, source_url=args.source_url)
