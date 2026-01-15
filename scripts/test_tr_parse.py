import pytest
from tr_parse import parse_lines_to_objects


@pytest.fixture
def sample_text():
    """Fixture providing sample tournament rules text."""
    return """100. Introduction
101. Purpose: This document provides the frameworks and structures for Riftbound competitions by defining rules, responsibilities and procedures to be followed in all Riftbound competitions.
102. Consistency: All Riftbound competitions must be run consistently regardless of their organizer or location to ensure equal treatment of players and interchangeability of events no matter the region or level.
103. Responsibility:
103.1. Attendees: All competitors AND all competition officials are expected to be responsible for following the rules as written and in the spirit in which they were written. This includes respecting all people at competitions.
103.2. Spectators: Spectators have their own set of responsibilities and expectations. See 204.8 for more information on spectators.
103.3. Penalties: Individuals who violate the frameworks and structures in this document are subject to penalties at the appropriate Organized Play Level (OPL). See 205 for more information on Organized Play Levels.
104. Precedence:
104.1. vs. Core Rules: In some cases, information in this document may contradict, or provide information not contained in, the Riftbound Core Rules. In all such cases, this document takes precedence for competitions.
104.2. vs. Official Local Language Translations: The English language version of this document will supersede any translation.
104.3. vs. Specific Event Addenda: In some cases, information in this document may be contradicted by alternate or additional policies or procedures in official addenda for specific competitions. In all such cases, those addenda take precedence.
105. Alteration: Riot Games or its official Riftbound partners reserve the right to alter this document, or any subsequent competition-specific addenda, at any time without prior notice.
200. Definitions
201. Competition Types: Riftbound competitions come in three types.
201.1. Premier: A competition that is run by Riot Games or an official competition organizer and has a unique name and features.
201.2. Qualifier: Any competition where rewards include access or advantages for premier events. (Premier events can themselves be qualifiers.)
201.3. Local: Any competition that is neither premier nor qualifier."""


@pytest.fixture
def parsed_result(sample_text):
    """Fixture providing parsed Line objects."""
    return parse_lines_to_objects(sample_text)


def test_top_level_sections_count(parsed_result):
    """Test that correct number of top-level sections are parsed."""
    assert len(parsed_result) == 8


def test_top_level_sections_order(parsed_result):
    """Test that top-level sections are in correct order."""
    top_level_sections = [line.section for line in parsed_result]
    expected = ["100", "101", "102", "103", "104", "105", "200", "201"]
    assert top_level_sections == expected


@pytest.mark.parametrize(
    "section_id,expected_children",
    [
        ("103", ["103.1", "103.2", "103.3"]),
        ("104", ["104.1", "104.2", "104.3"]),
        ("201", ["201.1", "201.2", "201.3"]),
    ],
)
def test_section_children(parsed_result, section_id, expected_children):
    """Test that sections have correct children."""
    section = next(line for line in parsed_result if line.section == section_id)
    assert len(section.children) == len(expected_children)
    assert [child.section for child in section.children] == expected_children


def test_section_text_content(parsed_result):
    """Test that section text content is parsed correctly."""
    section_103 = next(line for line in parsed_result if line.section == "103")
    assert section_103.text == "Responsibility:"

    section_200 = next(line for line in parsed_result if line.section == "200")
    assert section_200.text == "Definitions"


def test_subsection_text_content(parsed_result):
    """Test that subsection text content is parsed correctly."""
    section_103 = next(line for line in parsed_result if line.section == "103")
    expected_text = "Attendees: All competitors AND all competition officials are expected to be responsible for following the rules as written and in the spirit in which they were written. This includes respecting all people at competitions."
    assert section_103.children[0].text == expected_text


def test_leaf_sections_have_no_children(parsed_result):
    """Test that leaf sections have no children."""
    section_200 = next(line for line in parsed_result if line.section == "200")
    assert len(section_200.children) == 0
