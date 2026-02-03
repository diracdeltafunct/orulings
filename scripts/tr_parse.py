import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import List

import requests
from bs4 import BeautifulSoup

# Original tournament rules URL
ORIGINAL_URL = "https://riftbound.leagueoflegends.com/en-us/news/organizedplay/riftbound-tournament-rules/"

# January 2026 update URL
JANUARY_UPDATE_URL = "https://riftbound.leagueoflegends.com/en-us/news/announcements/tournament-rules-january-update/"

# Default URL for backwards compatibility
url = ORIGINAL_URL


def get_webpage_text(url):
    """
    Fetches a webpage and parses it to text.

    Args:
        url (str): The URL of the webpage to fetch

    Returns:
        str: The text content of the webpage
    """
    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()

    # Get text and clean it up
    text = soup.get_text()

    # Break into lines and remove leading/trailing space
    lines = (line.strip() for line in text.splitlines())

    # Break multi-headlines into a line each
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))

    # Remove blank lines
    text = "\n".join(chunk for chunk in chunks if chunk)

    # Split on section numbers that might be concatenated (e.g., "text100. Introduction")
    # Need to handle both top-level (100.) and subsections (601.1., 601.1.a., 601.1.a.1.)
    # BUT: Don't split if preceded by "CR ", "section ", or "See " (references)

    # First, protect references by temporarily replacing them
    # CR references like "CR 127. Privacy"
    text = re.sub(r"CR\s+(\d{3})\.", r"CR_REF_\1_DOT", text)
    # "section 700." references
    text = re.sub(r"section\s+(\d{3})\.", r"section_REF_\1_DOT", text)
    # "See 602.3.d." or "see 602.3.d." references (with optional subsections)
    text = re.sub(
        r"[Ss]ee\s+(\d{3}(?:\.\d+)*(?:\.[a-z])?(?:\.\d+)*)\.",
        r"see_REF_\1_DOT",
        text,
    )

    # Split on subsection numbers like 601.1. or 601.1.a. or 601.1.a.1.
    # Pattern: 3 digits, then zero or more (.digit or .letter) groups, then ". " and content
    # Use word boundary or non-digit to avoid splitting mid-number, but allow after short numbers like "2v2"
    # First pass: split where preceded by non-digit
    text = re.sub(
        r"(\D)(\d{3}(?:\.\d+)*(?:\.[a-z])?(?:\.\d+)*)\.\s+", r"\1\n\2. ", text
    )
    # Second pass: split concatenated sections like "2v2603.1." where a single digit precedes a 3-digit section
    # Only match if it's clearly a new section (3 digits starting with pattern like X00 or has dots)
    text = re.sub(r"(\d)(\d{3}\.\d+(?:\.[a-z])?(?:\.\d+)*)\.\s+", r"\1\n\2. ", text)
    # Third pass: handle top-level sections after patterns like ".5.603." (subsection ending, new section starting)
    # The source sometimes has "602.4.b.5.603." where 603 should be a new section
    # Match: .digit. followed by 3-digit section number (the extra dot before the section)
    text = re.sub(r"(\.\d)\.(\d{3})\.\s+", r"\1\n\2. ", text)

    # Restore protected references
    text = re.sub(r"CR_REF_(\d{3})_DOT", r"CR \1.", text)
    text = re.sub(r"section_REF_(\d{3})_DOT", r"section \1.", text)
    text = re.sub(
        r"see_REF_(\d{3}(?:\.\d+)*(?:\.[a-z])?(?:\.\d+)*)_DOT",
        r"see \1.",
        text,
    )

    # Join continuation lines (lines starting with lowercase) with previous line
    lines = text.splitlines()
    joined_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and i > 0 and stripped[0].islower():
            # This is a continuation line, append to previous
            if joined_lines:
                joined_lines[-1] = joined_lines[-1] + " " + stripped
        else:
            joined_lines.append(line)
    text = "\n".join(joined_lines)

    return text


def parse_numbered_lines(text):
    """
    Parses text to find lines matching the pattern \d\d\d. (three digits followed by a period).

    Args:
        text (str): The text blob to parse

    Returns:
        dict: Dictionary with the rule number as key and the line content as value
    """
    numbered_lines = {}
    pattern = re.compile(r"^(\d{3})\.\s*(.*)$")

    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            rule_number = match.group(1)
            content = match.group(2)
            numbered_lines[rule_number] = content

    return numbered_lines


@dataclass
class Line:
    section: str
    text: str
    children: list = field(default_factory=list)


def parse_lines_to_objects(text):
    """
    Parses text into a list of Line objects with hierarchical section numbering.
    Only sections ending in 00 (100, 200, 300, etc.) are top-level.
    Other sections in the same hundred (101-199, 201-299, etc.) are children.
    Handles patterns like: 204, 204.1, 204.1.a, 204.1.a.1

    Args:
        text (str): The text blob to parse

    Returns:
        list: List of top-level Line objects with nested children
    """
    top_level_lines = []
    section_map = {}  # Maps section number to Line object

    # Pattern matches: digits, letters, and combinations with periods
    # Examples: 100, 204, 204.1, 204.1.a, 204.1.a.1
    # Matches: number or letter, optionally followed by .number or .letter repeated
    pattern = re.compile(r"^((?:\d+|[a-zA-Z])(?:\.(?:\d+|[a-zA-Z]))*)\.\s+(.*)$")

    all_sections = []  # List of (section, content) tuples in order

    # First pass: Create all Line objects
    # Skip duplicates - only keep first occurrence of each section
    for line in text.splitlines():
        stripped = line.strip()
        match = pattern.match(stripped)
        if match:
            section = match.group(1)
            content = match.group(2)
            # Only add if we haven't seen this section before
            if section not in section_map:
                line_obj = Line(section=section, text=content)
                section_map[section] = line_obj
                all_sections.append(section)

    # Second pass: Build hierarchy
    for section in all_sections:
        line_obj = section_map[section]
        parts = section.split(".")

        if len(parts) == 1:
            # Single number like "000", "001", "100", "101", "200"
            section_num = int(section)
            if section_num % 100 == 0:
                # Top-level section (000, 100, 200, 300, etc.)
                top_level_lines.append(line_obj)
            else:
                # Subsection of the nearest hundred (e.g., 001 is child of 000, 101 is child of 100)
                parent_num = (section_num // 100) * 100
                # Preserve leading zeros (e.g., 0 -> "000", 100 -> "100")
                parent_section = f"{parent_num:03d}"
                if parent_section in section_map:
                    section_map[parent_section].children.append(line_obj)
                else:
                    # Parent not found, add to top level
                    top_level_lines.append(line_obj)
        else:
            # Has dots, so find parent by removing last component
            parent_section = ".".join(parts[:-1])
            if parent_section in section_map:
                section_map[parent_section].children.append(line_obj)
            else:
                # Parent not found, add to top level (orphaned section)
                top_level_lines.append(line_obj)

    return top_level_lines


def save_lines_to_files(
    lines: List[Line], output_dir: str = "../staticfiles/trsections"
):
    """
    Saves each top-level Line object (with all its children) to a separate JSON file.
    Files are named by section number (e.g., "104.json").

    Args:
        lines: List of top-level Line objects to save
        output_dir: Directory path relative to script location
    """
    # Get absolute path relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    abs_output_dir = os.path.join(script_dir, output_dir)

    # Create directory if it doesn't exist
    os.makedirs(abs_output_dir, exist_ok=True)

    def line_to_dict(line: Line) -> dict:
        """Recursively convert a Line and all its children to a dict."""
        return {
            "section": line.section,
            "text": line.text,
            "children": [line_to_dict(child) for child in line.children],
        }

    # Save each top-level line with all its children to one file
    # Only save true top-level sections (3-digit numbers ending in 00, like 000, 100, 200)
    for line in lines:
        # Skip orphaned sections that aren't true top-level
        if "." in line.section:
            continue  # Has dots, not a top-level section
        try:
            section_num = int(line.section)
            if section_num % 100 != 0:
                continue  # Not ending in 00, skip
        except ValueError:
            continue  # Not a number, skip

        line_dict = line_to_dict(line)

        # Save to file named by top-level section number
        filename = f"{line.section}.json"
        filepath = os.path.join(abs_output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(line_dict, f, indent=2, ensure_ascii=False)


def load_line_from_file(
    section: str, input_dir: str = "../staticfiles/trsections"
) -> Line:
    """
    Loads a Line object from a JSON file.
    Recursively loads children.

    Args:
        section: Section number (e.g., "104", "104.1")
        input_dir: Directory path relative to script location

    Returns:
        Line object with all children loaded
    """
    # Get absolute path relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    abs_input_dir = os.path.join(script_dir, input_dir)

    filename = f"{section}.json"
    filepath = os.path.join(abs_input_dir, filename)

    with open(filepath, "r", encoding="utf-8") as f:
        line_dict = json.load(f)

    def dict_to_line(d: dict) -> Line:
        """Recursively convert dict to Line object."""
        children = [dict_to_line(child) for child in d["children"]]
        return Line(section=d["section"], text=d["text"], children=children)

    return dict_to_line(line_dict)


def load_all_lines(input_dir: str = "../staticfiles/trsections") -> List[Line]:
    """
    Loads all top-level Line objects from the directory.

    Args:
        input_dir: Directory path relative to script location

    Returns:
        List of top-level Line objects with all children loaded
    """
    # Get absolute path relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    abs_input_dir = os.path.join(script_dir, input_dir)

    # Find all JSON files
    if not os.path.exists(abs_input_dir):
        return []

    json_files = [f for f in os.listdir(abs_input_dir) if f.endswith(".json")]

    # Extract section numbers and identify top-level (no dots in section number)
    top_level_sections = []
    for filename in json_files:
        section = filename.replace(".json", "")
        # Skip metadata file
        if section == "metadata":
            continue
        # Top-level sections have no dots (e.g., "100", "200") or only digits before first dot
        if "." not in section:
            top_level_sections.append(section)

    # Sort numerically
    top_level_sections.sort(key=lambda x: int(x))

    # Load each top-level section
    lines = []
    for section in top_level_sections:
        line = load_line_from_file(section, input_dir)
        lines.append(line)

    return lines


def save_metadata(output_dir: str, url: str):
    """
    Saves metadata including the current date and source URL.

    Args:
        output_dir: Directory path relative to script location
        url: The source URL that was parsed
    """
    from datetime import date

    script_dir = os.path.dirname(os.path.abspath(__file__))
    abs_output_dir = os.path.join(script_dir, output_dir)

    metadata = {
        "last_updated": date.today().isoformat(),
        "source_url": url,
    }

    filepath = os.path.join(abs_output_dir, "metadata.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"Saved metadata: last_updated={metadata['last_updated']}")


def parse_and_save(url: str, output_dir: str, description: str = ""):
    """
    Fetches, parses, and saves tournament rules from a URL.

    Args:
        url: The URL to fetch rules from
        output_dir: Directory path relative to script location to save JSON files
        description: Optional description for logging
    """
    print(f"Fetching rules from: {url}")
    if description:
        print(f"Description: {description}")

    text = get_webpage_text(url)
    lines = parse_lines_to_objects(text)

    print(f"Saving {len(lines)} top-level sections to {output_dir}...")
    save_lines_to_files(lines, output_dir)
    save_metadata(output_dir, url)
    print("Saved successfully!")

    # Show summary
    print(f"\nParsed sections:")
    for line in lines:
        child_count = len(line.children)
        print(
            f"  {line.section}. {line.text[:50]}{'...' if len(line.text) > 50 else ''} ({child_count} children)"
        )

    return lines


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse Riftbound Tournament Rules")
    parser.add_argument(
        "--january-update",
        action="store_true",
        help="Parse the January 2026 update instead of the original rules",
    )
    parser.add_argument(
        "--url", type=str, help="Custom URL to parse (overrides other options)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Custom output directory (relative to script location)",
    )

    args = parser.parse_args()

    # Determine URL and output directory
    if args.url:
        target_url = args.url
        output_dir = args.output_dir or "../staticfiles/trsections_custom"
        description = "Custom URL"
    elif args.january_update:
        target_url = JANUARY_UPDATE_URL
        output_dir = args.output_dir or "../staticfiles/trsections_january_2026"
        description = "January 2026 Tournament Rules Update"
    else:
        target_url = ORIGINAL_URL
        output_dir = args.output_dir or "../staticfiles/trsections"
        description = "Original Tournament Rules"

    # Parse and save
    lines = parse_and_save(target_url, output_dir, description)

    # Test loading back
    print("\nLoading back from files...")
    loaded_lines = load_all_lines(output_dir)
    print(f"Loaded {len(loaded_lines)} top-level sections")

    # Show first section as example
    if loaded_lines:
        first = loaded_lines[0]
        print(f"\nFirst section: {first.section}. {first.text}")
        print(f"  Has {len(first.children)} children")
