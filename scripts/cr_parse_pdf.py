"""
PDF-based parser for Riftbound Core Rules.

Usage:
    python cr_parse_pdf.py --pdf path/to/rules.pdf --output-dir ../staticfiles/crsections_march_2026
    python cr_parse_pdf.py --url https://example.com/rules.pdf
"""

import argparse
import os
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


def extract_rows_from_page(page):
    """
    Extract text rows from a CR PDF page.

    The CR PDF is single-column: section number and text appear on the same line,
    with wrapped continuation text on subsequent indented lines.
    There is no strikethrough in the CR PDF.
    """
    y_buckets = {}
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            bbox = line["bbox"]
            line_text = normalise_text("".join(s["text"] for s in line["spans"])).rstrip()
            if not line_text.strip():
                continue
            y_key = round(bbox[1] / 2) * 2
            if y_key not in y_buckets:
                y_buckets[y_key] = []
            y_buckets[y_key].append((bbox[0], line_text))

    rows = []
    for y_key in sorted(y_buckets.keys()):
        spans = sorted(y_buckets[y_key], key=lambda t: t[0])
        combined = " ".join(t[1].strip() for t in spans if t[1].strip())
        if combined:
            rows.append(combined)
    return rows


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


def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
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
    text = extract_text_from_pdf(pdf_path)

    print("\nFirst 20 extracted lines:")
    for ln in text.splitlines()[:20]:
        print(f"  {ln[:120]}")

    print("\nParsing into section objects...")
    lines = parse_lines_to_objects(text)

    print(f"Saving {len(lines)} top-level sections to: {output_dir}")
    save_lines_to_files(lines, output_dir)

    # save_lines_to_files skips non-×100 orphaned sections (like 649).
    # Save them as standalone files so sync_rules picks them up.
    import json as _json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    abs_out = os.path.join(script_dir, output_dir)

    def line_to_dict(line):
        return {"section": line.section, "text": line.text,
                "children": [line_to_dict(c) for c in line.children]}

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
        default="../staticfiles/crsections_march_2026",
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
