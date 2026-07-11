import csv
import os
import re
import warnings
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from pulse_ep.core import mesh_proc as mesh_proc
from pulse_ep.core import xml_proc as xml_proc
from pulse_ep.core.epmap import EPMap
from pulse_ep.core.importers.carto import populate_carto_mesh
from pulse_ep.core.study import Study


def import_carto_points(path, carto_point_export_filenames):
    pointExport_WOI = []
    pointExport_ReferenceAnnotation = []
    pointExport_MapAnnotation = []
    pointExport_Unipolar = []
    pointExport_Bipolar = []
    pointExport_ImpedanceTime = []
    pointExport_ImpedanceValue = []

    for carto_point_export_filename in carto_point_export_filenames:
        try:
            if not os.path.isfile(os.path.join(path, carto_point_export_filename)):
                print(f"File not found: {carto_point_export_filename}")
                continue  # Skip missing files
            else:
                pointExportTree = xml_proc.process_xml(
                    os.path.join(path, carto_point_export_filename)
                )
                root = pointExportTree.getroot()
                pointExport_WOI.append(
                    [float(root.find("WOI").get("From")), float(root.find("WOI").get("To"))]
                )
                pointExport_ReferenceAnnotation.append(
                    float(root.find("Annotations").get("Reference_Annotation"))
                )
                pointExport_MapAnnotation.append(
                    float(root.find("Annotations").get("Map_Annotation"))
                )
                pointExport_Unipolar.append(float(root.find("Voltages").get("Unipolar")))
                pointExport_Bipolar.append(float(root.find("Voltages").get("Bipolar")))

                try:
                    impedance_time = [
                        float(impedance.get("Time"))
                        for impedance in root.findall("Impedances/Impedance")
                    ]
                    impedance_value = [
                        float(impedance.get("Value"))
                        for impedance in root.findall("Impedances/Impedance")
                    ]
                    pointExport_ImpedanceTime.append(impedance_time)
                    pointExport_ImpedanceValue.append(impedance_value)
                except Exception as impedance_error:
                    print(
                        f"Warning: Failed to import impedance data for {carto_point_export_filename}: {impedance_error}"
                    )
                    pointExport_ImpedanceTime.append([float("nan")])
                    pointExport_ImpedanceValue.append([float("nan")])

        except Exception as point_error:
            print(f"Error processing {carto_point_export_filename}: {point_error}")
            continue  # Skip this file and move on

    return (
        np.array(pointExport_WOI),
        np.array(pointExport_ReferenceAnnotation),
        np.array(pointExport_MapAnnotation),
        np.array(pointExport_Unipolar),
        np.array(pointExport_Bipolar),
        np.array(pointExport_ImpedanceTime, dtype=object),  # Variable-length sequences
        np.array(pointExport_ImpedanceValue, dtype=object),  # Variable-length sequences
    )


def import_studies(file_path, map_filter=None):
    """
    Import a study from Carto data.

    :param file_path: Path to the study file or a single study file path.
    :param map_filter: handed over to import_carto for filtering maps that autoimport
    :return: The imported study object.
    """
    if isinstance(file_path, str):
        study = import_carto(file_path, filter=map_filter)
        return [study]
    elif isinstance(file_path, list):
        studies = []
        for path in file_path:
            study = import_carto(path, filter=map_filter)
            if study is not None:
                studies.append(study)
        return studies
    else:
        raise ValueError("Invalid file_path. Expected a string or a list of strings.")


def import_carto(filename: str, filter=None):
    """
    Import Carto data and convert it into a format suitable for further analysis.
    """
    if filter == None:  # noqa: E711
        interactive = True
    else:
        interactive = False

    # Skip macOS metadata files (AppleDouble ._* files)
    if os.path.basename(filename).startswith("._"):
        print(f"Skipping macOS metadata file: {filename}")
        return None

    # Load the Carto study file
    try:
        xml_tree = xml_proc.process_xml(filename)
        study_name = xml_proc.get_study_name(xml_tree)
    except Exception as e:
        print(f"Error loading XML file {filename}: {e}")
        return None  # Skip this study if there's a problem with loading the file

    path = os.path.dirname(filename)

    study = Study(extract_subfolder(filename, 4) + "-" + study_name)

    nMaps, names, numPtsPerMap, filenames = xml_proc.get_maps(xml_tree)

    if nMaps == 0:
        print(f"No maps found in {filename}. Skipping.")
        return None
    else:
        print(f"Total Maps found: {nMaps}")

    # Filter map names based on the regular expression
    if filter is not None:
        map_indices = [
            index
            for index, (name, numPts) in enumerate(zip(names, numPtsPerMap))  # noqa: B905
            if re.search(filter, name, re.IGNORECASE) and numPts >= 5
        ]
    else:
        map_indices = [index for index, numPts in enumerate(numPtsPerMap) if numPts >= 5]

    if interactive:
        raise ValueError("Interactive mode is not supported in server mode.")

    nMaps = len(map_indices)
    if nMaps < 1:
        print(f"No valid maps remaining after filtering in {filename}. Skipping.")
        return None
    else:
        print(f"Remaining Maps found: {nMaps}")

    for map_index in map_indices:
        try:
            map_element = xml_proc.get_map_element(xml_tree, map_index)

            # Construct a map
            epmap = EPMap(names[map_index], study.name, numPtsPerMap[map_index])

            # Put coordinates of the Points into the map object
            epmap.xyz = xml_proc.get_xyz(map_element)

            # Import Mesh file into the map (geometry + vendor-neutral scalars)
            carto_mesh_file = os.path.join(path, filenames[map_index])
            populate_carto_mesh(epmap, carto_mesh_file)

            # Import Carto Points
            carto_points_file = os.path.join(path, epmap.map_name + "_Points_Export.xml")
            carto_point_export_filenames = xml_proc.get_point_filenames(carto_points_file)

            # Import the data into EPMap
            (
                epmap.woi,
                epmap.reference_annotation,
                epmap.map_annotation,
                epmap.unipolar,
                epmap.bipolar,
                epmap.impedance_time,
                epmap.impedance_value,
            ) = import_carto_points(path, carto_point_export_filenames)

            # Add map to the Study
            study.add_epmap(epmap)

        except Exception as map_error:
            print(f"Error processing map {names[map_index]} in study {study.name}: {map_error}")
            continue  # Skip the current map and move on to the next one

    return study


def discover_carto_exports(
    directory: str | Path,
    pattern: str = "*.xml",
    recursive: bool = True,
) -> list[str]:
    """
    Discover CARTO study XML files within a directory.

    Replaces the legacy CSV-driven workflow (``get_filenames_from_csv``)
    with a filesystem walk that avoids hard-coded, potentially
    patient-identifiable path lists in a CSV.

    Parameters
    ----------
    directory : str or pathlib.Path
        Root directory to search for CARTO study XML files.
    pattern : str, default ``"*.xml"``
        Glob pattern used to match study XML files.
    recursive : bool, default True
        Whether to recurse into subdirectories.

    Returns
    -------
    list[str]
        Sorted, deduplicated list of absolute paths to candidate
        CARTO study XML files. macOS AppleDouble files (``._*``)
        are skipped automatically.

    Raises
    ------
    FileNotFoundError
        If ``directory`` does not exist or is not a directory.
    """
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    iterator: Iterable[Path] = root.rglob(pattern) if recursive else root.glob(pattern)

    seen: set[str] = set()
    files: list[str] = []
    for p in iterator:
        if not p.is_file():
            continue
        if p.name.startswith("._"):
            continue
        sp = str(p)
        if sp in seen:
            continue
        seen.add(sp)
        files.append(sp)

    files.sort()
    return files


def get_filenames_from_csv(file_with_studies):
    """
    .. deprecated:: 0.1.0
       Use :func:`discover_carto_exports` instead. The CSV-driven flow
       is retained only for backward compatibility with pre-release
       internal scripts and will be removed in a future version.
    """
    warnings.warn(
        "get_filenames_from_csv() is deprecated; use "
        "discover_carto_exports(directory, ...) instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    files = []
    seen = set()

    with open(file_with_studies) as f:
        reader = csv.reader(f)
        next(reader)  # Skip the header row
        for row in reader:
            file_path = row[0].strip()
            # Skip macOS AppleDouble metadata files and duplicates
            if os.path.basename(file_path).startswith("._"):
                continue
            if file_path in seen:
                continue
            seen.add(file_path)
            files.append(file_path)

    if not files:
        raise ValueError("No filenames could be imported from the CSV file.")

    return files


def extract_subfolder(file, n):
    # Normalize the path to ensure correct handling of path separators
    file = os.path.normpath(file)

    # split the file path into a list of directories
    directories = os.path.dirname(file).split(os.sep)

    # check if the desired subfolder index is valid
    if n < len(directories):
        return directories[n]
    else:
        return None
