import json
import os
import re
from dataclasses import dataclass, field
from typing import List

from pypdf import PdfReader


def get_pdf_text(pdf_path):
    """
    Extracts text from a PDF file.

    Args:
        pdf_path (str): Path to the PDF file

    Returns:
        str: The text content of the PDF
    """
    reader = PdfReader(pdf_path)
    text = ""
    total_pages = len(reader.pages)
    print(f"Extracting from {total_pages} pages...")

    for i, page in enumerate(reader.pages):
        if i % 10 == 0:
            print(f"  Page {i}/{total_pages}...")
        text += page.extract_text() + "\n"

    print("Cleaning text...")
    # Clean up the text - remove extra whitespace but keep lines together
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            lines.append(line)

    # Join lines and normalize spacing
    text = " ".join(lines)
    # Replace multiple spaces with single space
    text = re.sub(r"\s+", " ", text)

    # Protect rule references like "See rule 318." by temporarily replacing them
    # This prevents them from being split into separate sections
    text = re.sub(
        r"See rule (\d+(?:\.\d+)*(?:\.[a-zA-Z])?(?:\.\d+)*)\.",
        r"See_rule_REF_\1_DOT",
        text,
    )
    text = re.sub(
        r"see rule (\d+(?:\.\d+)*(?:\.[a-zA-Z])?(?:\.\d+)*)\.",
        r"see_rule_REF_\1_DOT",
        text,
    )

    # Split back into lines at section numbers
    # Add newlines before section numbers (like 000., 001., 100.1., etc.)
    text = re.sub(r"(\d+(?:\.\d+)*(?:\.[a-zA-Z])?(?:\.\d+)*)\.\s+", r"\n\1. ", text)
    # Clean up any double newlines
    text = re.sub(r"\n+", "\n", text)

    # Restore rule references
    text = re.sub(
        r"See_rule_REF_(\d+(?:_\d+)*(?:_[a-zA-Z])?(?:_\d+)*)_DOT", r"See rule \1.", text
    )
    text = re.sub(
        r"see_rule_REF_(\d+(?:_\d+)*(?:_[a-zA-Z])?(?:_\d+)*)_DOT", r"see rule \1.", text
    )
    # Fix underscores back to dots in section numbers
    text = re.sub(
        r"See rule (\d+(?:_\d+)*(?:_[a-zA-Z])?(?:_\d+)*)\.",
        lambda m: "See rule " + m.group(1).replace("_", ".") + ".",
        text,
    )
    text = re.sub(
        r"see rule (\d+(?:_\d+)*(?:_[a-zA-Z])?(?:_\d+)*)\.",
        lambda m: "see rule " + m.group(1).replace("_", ".") + ".",
        text,
    )

    return text.strip()


def parse_numbered_lines(text):
    r"""
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
            # Single number like "000", "100", "101", "200"
            section_num = int(section)
            if section_num % 100 == 0:
                # Top-level section (000, 100, 200, 300, etc.)
                top_level_lines.append(line_obj)
            else:
                # Subsection of the nearest hundred (e.g., 101 is child of 100)
                parent_num = (section_num // 100) * 100
                # Format parent section with leading zeros (e.g., "000", "100")
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
    lines: List[Line], output_dir: str = "../staticfiles/crsections"
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
    # Only save sections that are true top-level (N00 format: 000, 100, 200, etc.)
    for line in lines:
        # Check if this is a true top-level section (ends in 00)
        if "." not in line.section:  # Single number like "000", "100"
            # Must be 3 digits (000, 100, 200, etc.)
            if len(line.section) != 3:
                continue
            section_num = int(line.section)
            if section_num % 100 != 0:
                # Skip sections like 001, 101, etc. - they should be children
                continue
        else:
            # Skip any section with dots (like 322.5.a) - they should be children
            continue

        line_dict = line_to_dict(line)

        # Save to file named by top-level section number
        filename = f"{line.section}.json"
        filepath = os.path.join(abs_output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(line_dict, f, indent=2, ensure_ascii=False)


def load_line_from_file(
    section: str, input_dir: str = "../staticfiles/crsections"
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


def load_all_lines(input_dir: str = "../staticfiles/crsections") -> List[Line]:
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


if __name__ == "__main__":
    # Get absolute path to PDF
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_path = os.path.join(script_dir, "../staticfiles/Riftbound1.2.pdf")

    # Extract and parse the PDF
    print("Extracting text from PDF...")
    text = get_pdf_text(pdf_path)
    print(f"Extracted {len(text)} characters")

    print("\nParsing sections...")
    lines = parse_lines_to_objects(text)

    # Save to files
    print(f"Saving {len(lines)} top-level sections...")
    save_lines_to_files(lines)
    print("Saved successfully!")

    # Test loading back
    print("\nLoading back from files...")
    loaded_lines = load_all_lines()
    print(f"Loaded {len(loaded_lines)} top-level sections")

    # Show first few sections as examples
    if loaded_lines:
        for i, line in enumerate(loaded_lines[:5]):
            print(f"\nSection {line.section}: {line.text}")
            print(f"  Has {len(line.children)} children")
            if line.children:
                print(
                    f"  First child: {line.children[0].section}. {line.children[0].text[:50]}..."
                )
