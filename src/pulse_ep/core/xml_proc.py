import os
import re
from datetime import datetime

import numpy as np
from lxml import etree


def process_xml(filename):
    # Load and parse the XML file.
    parser = etree.XMLParser()
    xml_tree = etree.parse(filename, parser)

    # remove empty leafs as those are of little help
    remove_empty_leaf_elements(xml_tree)

    # Process the text of each node in the XML tree.
    for element in xml_tree.iter():
        if element.text is not None:
            # convert strings into numerical data - if possible
            element.text = str2var(element.text)

    # Return the processed xml_tree.
    return xml_tree


def get_map_element(xml_tree, iMap):
    map_element = xml_tree.find(f".//Maps/Map[{iMap + 1}]")
    return map_element


def get_xyz(map_element):
    points = map_element.find("CartoPoints").findall("Point")
    nPoints = len(points)
    xyz = np.empty((nPoints, 3))
    xyz[:] = np.nan

    for iPoint, point in enumerate(points):
        position_3d = point.get("Position3D")
        x, y, z = map(float, position_3d.split())
        xyz[iPoint, :] = [x, y, z]

    return xyz


def get_maps(xml_tree):
    maps = xml_tree.findall(".//Maps/Map")
    names = []
    numPtsPerMap = []
    filenames = []

    for map_elem in maps:
        names.append(map_elem.get("Name"))
        num_pts = int(map_elem.find("CartoPoints").get("Count"))
        filenames.append(map_elem.get("FileNames"))
        numPtsPerMap.append(num_pts)
        # print(f"Map Name: {names[-1]}, Number of Points: {num_pts}")

    return len(names), names, numPtsPerMap, filenames


def get_study_name(xml_tree):
    return xml_tree.getroot().attrib["name"]


def get_point_filenames(xml_input):
    if isinstance(xml_input, str):
        tree = process_xml(xml_input)
    elif isinstance(xml_input, etree._ElementTree):
        tree = xml_input
    else:
        raise ValueError(
            "Invalid input. Expected either a filename or an lxml.etree._ElementTree object."
        )

    filenames = []
    points_element = tree.xpath("/Points")[0]
    point_elements = points_element.xpath("Point")

    for point_element in point_elements:
        filename = point_element.get("File_Name")
        filenames.append(filename)

    return filenames


def get_connector_filenames(xml_tree, point_file_name):
    root = xml_tree.getroot()

    home_dir = os.path.dirname(point_file_name)
    connectors = root.findall(".//Connector")

    connector_filenames = []
    for connector in connectors:
        attributes = connector.attrib
        for name, position_file in attributes.items():
            if (
                "Eleclectrode_positions_OnAnnotation.txt".lower() in position_file.lower()
            ):  # then it is an Eleclectrode_Positions_OnAnnotation.txt file
                full_file_path = os.path.join(home_dir, position_file)
                connector_filenames.append([name, full_file_path])

    return connector_filenames


def get_tag_names(xml_tree) -> dict[int, str]:
    """The study's tag table as ``{tag id: full name}``.

    Tags are study-specific: the built-in ones (``Location Only``, ``Scar``,
    ``Pacing Site`` …) share ids across studies, but ids from 25 upwards are
    operator-defined labels that mean something different in every export.
    Resolving them here, against the catalogue that defined them, is the only
    reliable way. A catalogue without a table yields ``{}``.
    """
    tags_table = xml_tree.find(".//Maps/TagsTable")
    if tags_table is None:
        return {}
    names: dict[int, str] = {}
    for tag_elem in tags_table.findall("Tag"):
        try:
            tag_id = int(tag_elem.get("ID"))
        except (TypeError, ValueError):
            continue
        names[tag_id] = tag_elem.get("Full_Name") or tag_elem.get("Short_Name") or str(tag_id)
    return names


def get_point_tags(map_element) -> list[list[int]]:
    """The tag ids on every point of a map, in ``CartoPoints`` order.

    A point's ``<Tags Count="n">`` element lists its tag ids, whitespace
    separated; a point without the element, or with ``Count="0"``, gets an
    empty list. Parallel to :func:`get_xyz`, so the two align by index.
    """
    points = map_element.find("CartoPoints").findall("Point")
    tags: list[list[int]] = []
    for point in points:
        elem = point.find("Tags")
        ids: list[int] = []
        if elem is not None and elem.text:
            for token in elem.text.split():
                try:
                    ids.append(int(token))
                except ValueError:
                    continue
        tags.append(ids)
    return tags


def process_tags(xml_tree):
    # Get the tags information
    tags_table = xml_tree.find(".//Maps/TagsTable")
    nTags = int(tags_table.get("Count"))  # noqa: F841

    tagNames = []
    tagID = []

    for tag_elem in tags_table.findall("Tag"):
        tagNames.append(tag_elem.get("Full_Name"))
        tag_id = int(tag_elem.get("ID"))
        tagID.append(tag_id)

    # print(f"Tag Names: {tagNames}")
    return (tagNames, tagID)


def str2var(s):
    """The text of a catalogue element, kept as it is.

    This used to return ``None`` for every non-empty string — a stub of the
    MATLAB ``str2var`` it was ported from — and :func:`process_xml` assigned
    that back, so every element text in a parsed catalogue was discarded.
    Nothing read the texts then; the per-point ``<Tags>`` element does now.
    """
    return s


def process_string(s):
    if len(s) > 10000:  # if string is very long, return the string as is
        return s

    digits = r"(Inf)|(NaN)|(pi)|[\t\n\d\+\-\*\.ei EI\[\]\;\,]"
    remaining_str = re.sub(digits, "", s)  # remove all digits and other allowed characters

    # if nothing left, it is probably a number
    if remaining_str == "":
        s = s.replace("\n", ";")  # parse data tables into 2D arrays, if any

        # try to convert to a date, if not a date then try to convert to a number
        try:
            datetime.strptime(s, "%Y-%m-%d")
            return s
        except ValueError:
            try:
                num = np.array(eval(s))
                # Convert numpy arrays back to string
                if isinstance(num, np.ndarray):
                    return np.array2string(num)
                return num
            except:  # noqa: E722
                return s

    elif s[0] in ["[", "{"] and s[-1] in ["]", "}"]:  # this looks like an array encoded as a string
        try:
            val = eval(s)
            return val
        except:  # noqa: E722
            return s

    else:  # see if it is a boolean array with no [] brackets
        s1 = s.lower()
        s1 = s1.replace("false", "0")
        s1 = s1.replace("true", "1")
        remaining_str = re.sub(
            r"[01 \;\,]", "", s1
        )  # remove all 0/1, spaces, commas and semicolons
        # if nothing left, this is probably a boolean array
        if remaining_str == "":
            try:
                num = np.array(eval(s1))
                return num > 0
            except:  # noqa: E722
                return s

    return s


def remove_empty_leaf_elements(element):
    for child in element.xpath(".//*[not(node()) and not(@*)]"):
        child.getparent().remove(child)
