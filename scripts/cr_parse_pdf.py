"""
PDF-based parser for Riftbound Core Rules.

Usage:
    python cr_parse_pdf.py --pdf path/to/rules.pdf --output-dir ../staticfiles/crsections_march_2026
    python cr_parse_pdf.py --url https://example.com/rules.pdf
"""

import argparse
import os
import re
import urllib.request

import fitz  # PyMuPDF

# Reuse parsing/save logic from cr_parse
from cr_parse import Line, parse_lines_to_objects, save_lines_to_files

# Reuse text extraction helpers from tr_parse_pdf
from tr_parse_pdf import (
    SECTION_PATTERN,
    NO_PERIOD_SECTION,
    normalise_text,
)

PDF_URL = "https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/861747d1d4d505b7c14d73aba9749d1c3a209a67.pdf"


def _group_rows(page):
    """
    Group a page's text lines into logical rows by vertical-overlap
    clustering, rather than snapping each line's y-position to a fixed
    grid. The CR PDF lays the section number and its title out as
    separate text lines that are visually on the same row but whose
    bounding boxes don't share an identical y-position (number boxes are
    taller than title boxes for bold heading rows) - rounding both to the
    same 2px grid cell can land them in different buckets and silently
    drop the title (see e.g. "197." / "Locations"). Overlap clustering
    merges them correctly since one box's y-range sits inside the other's.

    Returns rows in document order; each row is a dict with "parts": a
    list of (x0, spans, text) sorted left-to-right.
    """
    items = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            spans = line["spans"]
            if not spans:
                continue
            text = normalise_text("".join(s["text"] for s in spans)).rstrip()
            if not text.strip():
                continue
            bbox = line["bbox"]
            items.append((bbox[1], bbox[3], bbox[0], spans, text))

    items.sort(key=lambda t: (t[0], t[2]))

    rows = []
    for y0, y1, x0, spans, text in items:
        for row in rows:
            if y0 < row["y1"] and y1 > row["y0"]:
                row["parts"].append((x0, spans, text))
                row["y0"] = min(row["y0"], y0)
                row["y1"] = max(row["y1"], y1)
                break
        else:
            rows.append({"y0": y0, "y1": y1, "parts": [(x0, spans, text)]})

    rows.sort(key=lambda r: r["y0"])
    for row in rows:
        row["parts"].sort(key=lambda t: t[0])
    return rows


def extract_rows_from_page(page):
    """
    Extract text rows from a CR PDF page.

    The CR PDF is single-column: section number and text appear on the same row,
    with wrapped continuation text on subsequent indented rows.
    There is no strikethrough in the CR PDF.
    """
    rows = []
    for row in _group_rows(page):
        combined = " ".join(t[2].strip() for t in row["parts"] if t[2].strip())
        if combined:
            rows.append(combined)
    return rows


def _is_bold(font):
    return "Bold" in font or "Black" in font


_HEADING_NUM_RE = re.compile(r"^(\d+(?:\.(?:\d+|[a-zA-Z]))*)\.\s*(.*)$")


def detect_headings(doc):
    """
    Classify section numbers as navigation headings from PDF formatting:
      - heading_level 1: title fully bold at 20pt+ (outermost divisions,
        e.g. "100. Game Concepts")
      - heading_level 2: title fully bold at 10-20pt (major section
        headings, e.g. "125. Cards")

    A section only counts as a heading when the text immediately after the
    number is *entirely* bold - this distinguishes real headings from body
    paragraphs that merely bold a lead-in phrase before a colon (e.g.
    "204.1. Base Costs: These costs are...", where only "Base Costs:" is
    bold). Smaller bold titles (~8pt) are a third, finer tier that exists
    in the source but isn't surfaced as a navigation heading here.
    """
    headings = {}
    for page in doc:
        for row in _group_rows(page):
            parts = row["parts"]
            full_text = " ".join(t[2].strip() for t in parts if t[2].strip())
            m = _HEADING_NUM_RE.match(full_text)
            if not m or not m.group(2).strip():
                continue
            section, rest = m.group(1), m.group(2).strip()
            if len(rest) > 60:
                continue

            # Spans making up the title, i.e. everything after the leading
            # number token (which may itself be one or more spans).
            title_spans = []
            consumed_number = False
            for _, spans, _ in parts:
                for s in spans:
                    if not consumed_number:
                        if re.fullmatch(r"[\d.]+\.?\s*", s["text"]):
                            continue
                        consumed_number = True
                    title_spans.append(s)
            if not title_spans or not all(_is_bold(s["font"]) for s in title_spans):
                continue

            size = max(round(s["size"], 1) for s in title_spans)
            if size >= 20:
                headings[section] = 1
            elif size >= 10:
                headings[section] = 2
    return headings


def apply_heading_levels(lines, headings):
    """Recursively set heading_level on a Line tree from a {section: level} map."""
    for line in lines:
        line.heading_level = headings.get(line.section)
        apply_heading_levels(line.children, headings)


def join_continuation_lines(rows):
    """Rejoin PDF-wrapped continuation lines to their parent section lines."""
    result = []
    for row in rows:
        stripped = row.strip()
        if not stripped:
            continue
        if SECTION_PATTERN.match(stripped):
            result.append(stripped)
        else:
            m = NO_PERIOD_SECTION.match(stripped)
            if m:
                result.append(f"{m.group(1)}. {m.group(2)}")
            elif result:
                result[-1] = result[-1] + " " + stripped
    return result


def extract_text_from_pdf(doc):
    all_rows = []
    for page in doc:
        all_rows.extend(extract_rows_from_page(page))
    return "\n".join(join_continuation_lines(all_rows))


def save_metadata(output_dir, source_url):
    import json
    from datetime import date

    script_dir = os.path.dirname(os.path.abspath(__file__))
    abs_dir = os.path.join(script_dir, output_dir)
    metadata = {"last_updated": date.today().isoformat(), "source_url": source_url}
    with open(os.path.join(abs_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"Saved metadata: last_updated={metadata['last_updated']}")


def parse_and_save_pdf(pdf_path, output_dir, source_url=""):
    print(f"Parsing CR PDF: {pdf_path}")
    doc = fitz.open(pdf_path)
    text = extract_text_from_pdf(doc)

    print("\nFirst 20 extracted lines:")
    for ln in text.splitlines()[:20]:
        print(f"  {ln[:120]}")

    print("\nParsing into section objects...")
    lines = parse_lines_to_objects(text)

    print("\nDetecting navigation headings from PDF formatting...")
    headings = detect_headings(doc)
    apply_heading_levels(lines, headings)
    tier1 = sorted(s for s, lvl in headings.items() if lvl == 1)
    tier2 = sorted(s for s, lvl in headings.items() if lvl == 2)
    print(f"  Tier 1 (outermost): {tier1}")
    print(f"  Tier 2 (major sections): {len(tier2)} found")

    print(f"\nSaving {len(lines)} top-level sections to: {output_dir}")
    save_lines_to_files(lines, output_dir)

    # save_lines_to_files skips non-×100 orphaned sections (like 649).
    # Save them as standalone files so sync_rules picks them up.
    import json as _json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    abs_out = os.path.join(script_dir, output_dir)

    def line_to_dict(line):
        d = {"section": line.section, "text": line.text,
             "children": [line_to_dict(c) for c in line.children]}
        if line.heading_level is not None:
            d["heading_level"] = line.heading_level
        return d

    for line in lines:
        if "." in line.section:
            continue
        try:
            n = int(line.section)
        except ValueError:
            continue
        if n % 100 == 0:
            continue  # already saved by save_lines_to_files
        filepath = os.path.join(abs_out, f"{line.section}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            _json.dump(line_to_dict(line), f, indent=2, ensure_ascii=False)
        print(f"  Saved orphaned section {line.section}")

    save_metadata(output_dir, source_url)

    print("\nTop-level sections:")
    for line in lines:
        print(f"  {line.section}. {line.text[:60]} ({len(line.children)} children)")

    return lines


def download_pdf(url, dest_path):
    print(f"Downloading PDF from: {url}")
    urllib.request.urlretrieve(url, dest_path)
    print(f"Saved to: {dest_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse Riftbound CR PDF into JSON sections")
    parser.add_argument("--pdf", type=str, help="Path to local PDF file")
    parser.add_argument("--url", type=str, default=PDF_URL, help="URL to download PDF from")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="../rules_source/crsections_march_2026",
        help="Output directory (relative to script location)",
    )
    parser.add_argument("--source-url", type=str, default=PDF_URL)
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    if args.pdf:
        pdf_path = args.pdf
    else:
        pdf_path = os.path.join(script_dir, "new_cr.pdf")
        if not os.path.exists(pdf_path):
            download_pdf(args.url, pdf_path)

    parse_and_save_pdf(pdf_path, args.output_dir, source_url=args.source_url)
