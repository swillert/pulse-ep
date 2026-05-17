"""
Point-level importer for CARTO raw data.

For each measurement point within a map, parses:
  - Pn_Point_Export.xml → timestamps, annotations, voltages, connector list
  - *_OnAnnotation_*.txt → catheter electrode positions (CS, 20A, MEC/NAVISTAR)

ECG data is NOT imported (too large for DB storage).
Returns a list of dicts ready to create EPMapPoint rows.
The reference catheter count (single vs double) must be set manually
via EPMapAttributes, as automatic detection from connector types is
not reliable (MAGNETIC_20_POLE may be present but not used as reference).

Strategy for finding files:
  - Connectors: first try XML-referenced paths, then fallback to
    filename-pattern search using {map_name}_{connector}_..._OnAnnotation_{start_time}.txt
"""

import os
import re
import logging
import numpy as np
from lxml import etree

log = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────

def _parse_electrode_positions(filepath: str) -> list[float] | None:
    """
    Parse a CARTO Eleclectrode_Positions file (OnAnnotation or regular).
    Format: header line, column header line, then tab-separated rows:
        Electrode#  Time  X  Y  Z
    Returns flat list [x1,y1,z1, x2,y2,z2, ...] or None if file missing.
    """
    if not os.path.isfile(filepath):
        return None
    try:
        coords = []
        with open(filepath, 'r', encoding='latin-1') as f:
            lines = f.readlines()
        for line in lines[2:]:  # skip header + column names
            parts = line.strip().split('\t')
            if len(parts) >= 5:
                x, y, z = float(parts[2]), float(parts[3]), float(parts[4])
                coords.extend([x, y, z])
        return coords if coords else None
    except Exception as e:
        log.warning(f"Failed to parse electrode positions {filepath}: {e}")
        return None



def _classify_connector(name: str) -> str:
    """Classify a connector attribute name into a category."""
    name_upper = name.upper()
    if 'CS_CONNECTOR' in name_upper:
        return 'CS'
    if 'MAGNETIC_20_POLE_A_CONNECTOR' in name_upper:
        return '20A'
    if 'MEC_CONNECTOR' in name_upper or 'NAVISTAR_CONNECTOR' in name_upper:
        return 'ROVING'
    if 'DX_CONNECTOR' in name_upper:
        return 'DX'
    return 'OTHER'


CONNECTOR_SEARCH_NAMES = [
    ('CS_CONNECTOR', 'CS'),
    ('MAGNETIC_20_POLE_A_CONNECTOR', '20A'),
    ('MEC_CONNECTOR', 'ROVING'),
    ('NAVISTAR_CONNECTOR', 'ROVING'),
]


def _find_on_annotation_by_filename(study_dir: str, map_name: str,
                                     start_time: int) -> dict:
    """
    Fallback: find OnAnnotation Eleclectrode_Positions files by filename pattern.
    Returns dict: {'CS': filepath, '20A': filepath, 'ROVING': filepath}
    """
    result = {}
    for conn_name, category in CONNECTOR_SEARCH_NAMES:
        if category in result:
            continue  # already found
        fname = f"{map_name}_{conn_name}_Eleclectrode_Positions_OnAnnotation_{start_time}.txt"
        fpath = os.path.join(study_dir, fname)
        if os.path.isfile(fpath):
            result[category] = fpath
    return result



# ── Main entry point ──────────────────────────────────────────────────────

def import_map_points(study_dir: str, map_name: str) -> tuple[list[dict], int]:
    """
    Import all measurement points for a single map.

    Args:
        study_dir: Path to the CARTO export directory
        map_name: Name of the map (e.g. "2-1-IC Pace Map Ra Lateral")

    Returns:
        (point_dicts, ref_count) where:
          point_dicts: list of dicts matching EPMapPoint columns
          ref_count: always 0 (must be set manually via EPMapAttributes)
    """
    points_xml = os.path.join(study_dir, f"{map_name}_Points_Export.xml")
    if not os.path.isfile(points_xml):
        log.warning(f"Points_Export.xml not found: {points_xml}")
        return [], 0

    try:
        tree = etree.parse(points_xml)
    except Exception as e:
        log.warning(f"Failed to parse {points_xml}: {e}")
        return [], 0

    root = tree.getroot()
    point_elements = root.findall('Point')

    point_dicts = []

    for idx, pt_elem in enumerate(point_elements):
        carto_id = int(pt_elem.get('ID', 0))
        pt_filename = pt_elem.get('File_Name', '')

        pd = {
            'point_index': idx,
            'carto_point_id': carto_id,
            'start_time': None,
            'position_x': None, 'position_y': None, 'position_z': None,
            'woi_from': None, 'woi_to': None,
            'reference_annotation': None, 'map_annotation': None,
            'unipolar_voltage': None, 'bipolar_voltage': None,
            'cs_positions': None,
            'magnetic20_positions': None,
            'roving_positions': None,
            'connector_types': [],

        }

        # ── Parse Pn_Point_Export.xml ──
        pt_export_path = os.path.join(study_dir, pt_filename)
        if not os.path.isfile(pt_export_path):
            point_dicts.append(pd)
            continue

        try:
            pt_tree = etree.parse(pt_export_path)
            pt_root = pt_tree.getroot()

            # Annotations
            ann = pt_root.find('Annotations')
            if ann is not None:
                pd['start_time'] = int(ann.get('StartTime', 0))
                ref_ann = ann.get('Reference_Annotation', '')
                map_ann = ann.get('Map_Annotation', '')
                pd['reference_annotation'] = float(ref_ann) if ref_ann else None
                pd['map_annotation'] = float(map_ann) if map_ann else None

            # WOI
            woi = pt_root.find('WOI')
            if woi is not None:
                pd['woi_from'] = float(woi.get('From', 'nan'))
                pd['woi_to'] = float(woi.get('To', 'nan'))

            # Voltages
            volt = pt_root.find('Voltages')
            if volt is not None:
                uni = volt.get('Unipolar', '')
                bip = volt.get('Bipolar', '')
                pd['unipolar_voltage'] = float(uni) if uni else None
                pd['bipolar_voltage'] = float(bip) if bip else None

            # ── Catheter positions ──
            # Strategy: first parse XML connector elements, then fallback
            # to filename search for OnAnnotation files.
            conn_types_seen = []
            found_categories = set()

            # Method 1: Parse connector elements from XML
            positions_elem = pt_root.find('Positions')
            if positions_elem is not None:
                for conn_elem in positions_elem.findall('Connector'):
                    for attr_name, attr_val in conn_elem.attrib.items():
                        # Only OnAnnotation Eleclectrode files
                        if 'OnAnnotation' not in attr_val:
                            continue
                        if 'Sensor_Positions' in attr_val:
                            continue
                        if 'Eleclectrode_Positions' not in attr_val:
                            continue

                        cat = _classify_connector(attr_name)
                        fpath = os.path.join(study_dir, attr_val)
                        coords = _parse_electrode_positions(fpath)

                        if coords is not None:
                            if cat == 'CS':
                                pd['cs_positions'] = coords
                            elif cat == '20A':
                                pd['magnetic20_positions'] = coords
                            elif cat == 'ROVING':
                                pd['roving_positions'] = coords
                            found_categories.add(cat)

                        if attr_name not in conn_types_seen:
                            conn_types_seen.append(attr_name)

            # Method 2: Fallback — search by filename pattern
            if pd['start_time'] is not None:
                fallback = _find_on_annotation_by_filename(
                    study_dir, map_name, pd['start_time'])
                for cat, fpath in fallback.items():
                    if cat in found_categories:
                        continue  # already have from XML
                    coords = _parse_electrode_positions(fpath)
                    if coords is not None:
                        if cat == 'CS':
                            pd['cs_positions'] = coords
                        elif cat == '20A':
                            pd['magnetic20_positions'] = coords
                        elif cat == 'ROVING':
                            pd['roving_positions'] = coords
                        found_categories.add(cat)
                        # Extract connector name from filename
                        basename = os.path.basename(fpath)
                        for conn_name, c in CONNECTOR_SEARCH_NAMES:
                            if conn_name in basename and conn_name not in conn_types_seen:
                                conn_types_seen.append(conn_name)

            pd['connector_types'] = conn_types_seen

        except Exception as e:
            log.warning(f"Failed to parse point {pt_filename}: {e}")

        point_dicts.append(pd)

    ref_count = 0  # must be set manually via EPMapAttributes
    n_with_cs = sum(1 for p in point_dicts if p['cs_positions'] is not None)
    log.info(f"  {map_name}: {len(point_dicts)} points, cs={n_with_cs}")

    return point_dicts, ref_count
