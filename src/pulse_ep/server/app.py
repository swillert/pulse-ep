from flask import Flask, request, jsonify, render_template, redirect, url_for, json as flask_json, send_file
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from pulse_ep.core.models import ReportModel, Base, StudyModel, EPMapModel, UserModel, ColormapModel, EPMapAttributes, AttributeMetadata
from pulse_ep.core.database import get_db_session
from sqlalchemy.orm.attributes import flag_modified
import os
import threading
import configparser
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
import numpy as np

REPORTS_DIR = 'reports'
os.makedirs(REPORTS_DIR, exist_ok=True)
import matplotlib.pyplot as plt
import pyvista as pv
import re

_config = configparser.ConfigParser()
_config.read('config.ini')

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = _config['jwt']['secret_key']
jwt = JWTManager(app)
bcrypt = Bcrypt(app)
CORS(app)

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/register')
def register():
    return render_template('register.html')


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/register_user', methods=['POST'])
def register_user():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'user')  # Default role is 'user'
    if not username or not password or not role:
        return jsonify({"msg": "Username, password, and role are required"}), 400

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    with get_db_session() as session:
        user = UserModel(username=username, password=hashed_password, role=role)
        session.add(user)
        session.commit()

    return jsonify({"msg": "User registered successfully"}), 201

@app.route('/login_user', methods=['POST'])
def login_user():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    with get_db_session() as session:
        user = session.query(UserModel).filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            access_token = create_access_token(identity=username, additional_claims={"role": user.role})
            return jsonify(access_token=access_token), 200
        else:
            return jsonify({"msg": "Bad username or password"}), 401

@app.route('/list_studies', methods=['GET'])
@jwt_required()
def list_studies():
    with get_db_session() as session:
        studies = StudyModel.get_study_list(session)
        studies_serializable = [{'id': study[0], 'study_name': study[1]} for study in studies]
    return jsonify(studies_serializable)

@app.route('/list_epmaps_in_study/<int:study_id>', methods=['GET'])
@jwt_required()
def list_epmaps_in_study(study_id):
    with get_db_session() as session:
        epmaps = StudyModel.get_epmap_list_by_id(session, study_id)
        if epmaps is None:
            return "Study not found", 404

        epmaps_serializable = [{'id': epmap[0], 'study_id': study_id, 'map_name': epmap[1], 'number_of_points': epmap[2]} for epmap in epmaps]
    return jsonify(epmaps_serializable)

def get_epmap_from_db(map_id, include_points=True):
    with get_db_session() as session:
        epmap_model = EPMapModel.retrieve(session, map_id)
        if not epmap_model:
            raise ValueError(f"EPMap with ID {map_id} not found in the database.")
        return epmap_model.to_epmap(include_points=include_points)

@app.route('/get_epmaps', methods=['POST'])
@jwt_required()
def get_epmaps_by_ids():
    """
    Endpoint to retrieve details of one or multiple EPMaps by their IDs.
    Expects a JSON payload with 'epmap_ids' as a list of EPMap IDs.
    """
    data = request.get_json()
    epmap_ids = data.get('epmap_ids', [])

    if not epmap_ids or not isinstance(epmap_ids, list):
        return jsonify({"msg": "A list of EPMap IDs is required."}), 400

    with get_db_session() as session:
        # Query for the specified EPMap IDs
        epmaps = session.query(
            EPMapModel.id,
            EPMapModel.study_id,
            EPMapModel.study_name,
            EPMapModel.map_name,
            EPMapModel.number_of_points
        ).filter(EPMapModel.id.in_(epmap_ids)).all()

        # If no results found for given IDs, return a 404 response
        if not epmaps:
            return jsonify({"msg": "No EPMaps found for the given IDs."}), 404

        # Serialize the EPMaps data
        epmaps_serializable = [
            {
                'id': epmap.id,
                'study_id': epmap.study_id,
                'study_name': epmap.study_name,
                'map_name': epmap.map_name,
                'number_of_points': epmap.number_of_points
            } for epmap in epmaps
        ]

    return jsonify(epmaps_serializable), 200


@app.route('/get_mesh_data', methods=['GET'])
@jwt_required()
def get_mesh_data():
    print("Received request for /get_mesh_data")

    map_id = request.args.get('map_id')
    scalar_name = request.args.get('scalar_name', 'act')

    print(f"Received map_id: {map_id}, scalar_name: {scalar_name}")

    try:
        distance = float(request.args.get('distance', default=5))
        print(f"Parsed distance: {distance}")
    except ValueError:
        print("Invalid distance. It must be a number.")
        return jsonify({"error": "Invalid distance. It must be a number."}), 400

    try:
        map_id = int(map_id)
        print(f"Parsed map_id: {map_id}")
    except (TypeError, ValueError):
        print("Invalid map_id. It must be an integer.")
        return jsonify({"error": "Invalid map_id. It must be an integer."}), 400

    try:
        ep_map = get_epmap_from_db(map_id)
        print(f"Retrieved EPMap for map_id {map_id}")
    except ValueError as e:
        print(f"Error retrieving EPMap: {str(e)}")
        return jsonify({"error": str(e)}), 404

    try:
        # Extract the mesh data
        data = ep_map.extract_mesh_data(scalar_name=scalar_name, distance=distance)
        print(f"Extracted mesh data: {data}")

        # Unwrap the dictionary into individual variables
        vertices = data["mesh_data"]["vertices"]
        faces = data["mesh_data"]["faces"]
        scalar_data = data["mesh_data"]["scalar_data"]
        normalized_scalar_data = data["mesh_data"]["normalized_scalar_data"]

        coordinates = data["point_data"]["coordinates"]
        point_scalar_data = data["point_data"]["scalar_data"]
        normalized_point_scalar_data = data["point_data"]["normalized_scalar_data"]

        # Additional validation of the unwrapped data
        if vertices is None or faces is None or scalar_data is None or normalized_scalar_data is None:
            raise KeyError("Missing mesh data in the extracted data.")

        if coordinates is None or point_scalar_data is None:
            raise KeyError("Missing point data in the extracted data.")

    except (ValueError, KeyError) as e:
        print(f"Error extracting mesh data: {str(e)}")
        return jsonify({"error": str(e)}), 400

    # Convert data to a JSON-compatible format
    try:
        mesh_data = {
            "vertices": vertices.tolist(),
            "faces": faces.tolist(),
            "scalar_data": scalar_data.tolist(),
            "normalized_scalar_data": normalized_scalar_data.tolist()
        }
        print("Converted mesh data to JSON-compatible format.")

        point_data = {
            "coordinates": coordinates.tolist(),
            "scalar_data": point_scalar_data.tolist() if point_scalar_data is not None else None,
            "normalized_scalar_data": normalized_point_scalar_data.tolist() if normalized_point_scalar_data is not None else None
        }
        print("Converted point data to JSON-compatible format.")
    except Exception as e:
        print(f"Error converting data to JSON-compatible format: {str(e)}")
        return jsonify({"error": "Error converting data to JSON-compatible format."}), 400

    response_data = {
        "mesh_data": mesh_data,
        "point_data": point_data
    }

    # Convert to JSON string and handle NaN
    try:
        json_raw = flask_json.dumps(response_data)
        json_raw = re.sub(r'\bNaN\b', 'null', json_raw)
        print("Converted response data to JSON string.")
    except Exception as e:
        print(f"Error during JSON conversion: {str(e)}")
        return jsonify({"error": "Error during JSON conversion."}), 400

    print("Successfully processed /get_mesh_data request.")

    return app.response_class(
        response=json_raw,
        status=200,
        mimetype='application/json'
    )

@app.route('/epmaps/filter_by_attributes', methods=['POST'])
@jwt_required()
def filter_epmaps_by_attributes():
    """
    Endpoint to filter EPMaps based on attributes stored in the `attributes` JSONB field and return matching map_ids.
    """
    data = request.get_json()
    filters = data.get('filters', {})  # Default to an empty dictionary if 'filters' is not provided

    print("Received filters:", filters)  # Debugging print

    if not isinstance(filters, dict):
        return jsonify({"msg": "Filters must be provided as a dictionary"}), 400

    with get_db_session() as session:
        query = session.query(EPMapAttributes)

        # If filters are empty, return all map_ids from EPMapModel (not EPMapAttributes,
        # which only has entries for maps that have had attributes set)
        if not filters:
            print("No filters provided, returning all map_ids.")
            map_ids = [row.id for row in session.query(EPMapModel.id).all()]
            return jsonify({"map_ids": map_ids}), 200

        # Convert filters into JSONB-compatible format
        def convert_value(value):
            if isinstance(value, str):
                if value.lower() == 'true':
                    return True
                elif value.lower() == 'false':
                    return False
            return value

        converted_filters = {k: convert_value(v) for k, v in filters.items()}
        print("Converted filters:", converted_filters)  # Debugging print

        # Apply filters for JSONB attributes using @> operator
        query = query.filter(EPMapAttributes.attributes.op('@>')(flask_json.dumps(converted_filters)))

        # Retrieve matching map IDs
        map_ids = [entry.map_id for entry in query.all()]
        print("Matching map IDs:", map_ids)  # Debugging print

    return jsonify({"map_ids": map_ids}), 200



@app.route('/epmaps/set_attributes', methods=['POST'])
@jwt_required()
def set_attributes_for_epmaps():
    """
    Endpoint to set or update a list of attributes for a given list of map_ids in EPMapAttributes.
    """
    data = request.get_json()
    map_ids = data.get('map_ids')
    attribute_values = data.get('attribute_values')

    print("Received data:", data)
    print("Map IDs:", map_ids)
    print("Attribute Values:", attribute_values)

    if not map_ids or not isinstance(map_ids, list):
        return jsonify({"msg": "A list of map_ids is required"}), 400
    if not attribute_values or not isinstance(attribute_values, dict):
        return jsonify({"msg": "Attribute values must be provided as a dictionary"}), 400

    with get_db_session() as session:
        for map_id in map_ids:
            entry = session.query(EPMapAttributes).filter_by(map_id=map_id).first()

            if entry is None:
                print(f"Creating new EPMapAttributes entry for map_id {map_id}")
                entry = EPMapAttributes(map_id=map_id)
                session.add(entry)

            # Set attributes
            for key, value in attribute_values.items():
                print(f"Setting attribute {key} to {value} for map_id {map_id}")

            entry.set_attributes(attribute_values)

        try:
            print("Attempting to commit session changes...")
            session.commit()
            print("Session committed successfully.")

            # Verify by re-querying for the first map_id
            test_id = map_ids[0]
            test_entry = session.query(EPMapAttributes).filter_by(map_id=test_id).first()
            print(f"Re-querying after commit for map_id {test_id}: {test_entry.attributes}")  # Check if "a" is set to "sad"

        except Exception as e:
            print("Error during session commit:", e)
            session.rollback()
            return jsonify({"msg": "Failed to commit changes to the database.", "error": str(e)}), 500


    print("Attributes updated successfully.")
    return jsonify({"msg": "Attributes set or updated for the provided map_ids"}), 200


@app.route('/epmaps/get_attributes', methods=['POST'])
@jwt_required()
def get_attributes_for_epmaps():
    """
    Endpoint to retrieve a list of attributes and their values for a given map_id or a list of map_ids in EPMapAttributes.
    """
    data = request.get_json()
    map_ids = data.get('map_ids')
    attributes = data.get('attributes')

    if not map_ids or not isinstance(map_ids, list):
        return jsonify({"msg": "A list of map_ids is required"}), 400

    with get_db_session() as session:
        results = {}
        for map_id in map_ids:
            entry = session.query(EPMapAttributes).filter_by(map_id=map_id).first()
            if entry:
                entry_dict = entry.get_all_attributes()

                # Filter for specific attributes if requested
                if attributes:
                    entry_dict = {attr: entry_dict.get(attr) for attr in attributes}

                results[map_id] = entry_dict
            else:
                # If map_id does not exist, insert None
                results[map_id] = None

    return jsonify({"attributes": results}), 200

@app.route('/epmaps/distinct_attributes', methods=['GET'])
@jwt_required()
def get_distinct_attributes():
    """
    Endpoint to retrieve all distinct attribute names and types from the AttributeMetadata table.
    """
    try:
        with get_db_session() as session:
            # Fetch all attributes with their types from the AttributeMetadata table
            metadata_entries = session.query(AttributeMetadata.name, AttributeMetadata.data_type, AttributeMetadata.default_value).all()
            distinct_attributes = [{"name": entry[0], "type": entry[1], "default_value": entry[1]} for entry in metadata_entries]

        return jsonify({"distinct_attributes": distinct_attributes}), 200
    except Exception as e:
        print(f"Error retrieving distinct attributes: {e}")
        return jsonify({"error": "Failed to retrieve distinct attributes"}), 500


@app.route('/calculate_areas_for_intervals', methods=['POST'])
@jwt_required()
def calculate_areas_for_intervals_endpoint():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No input data provided"}), 400

    map_id = data.get('map_id')
    scalar_name = data.get('scalar_name', 'act')
    distance = data.get('distance', 5)
    intervals = data.get('intervals')

    if not intervals:
        return jsonify({"error": "Intervals must be provided."}), 400

    try:
        map_id = int(map_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid map_id. It must be an integer."}), 400

    try:
        ep_map = get_epmap_from_db(map_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    # Ensure intervals are iterable pairs
    try:
        areas = ep_map.calculate_areas_for_intervals(intervals, scalar_name=scalar_name, distance=distance)
    except TypeError:
        return jsonify({"error": "Intervals should be pairs of min and max values."}), 400

    # Convert areas to JSON-compatible format, replacing NaN with None
    areas = [None if np.isnan(area) else area for area in areas]

    mesh_data = {
        "areas": areas
    }

    # Convert mesh_data to JSON string
    json_raw = flask_json.dumps(mesh_data)

    # Replace NaN with null in the JSON string (just a safeguard, should be redundant now)
    json_raw = re.sub(r'\bNaN\b', 'null', json_raw)

    return app.response_class(
        response=json_raw,
        status=200,
        mimetype='application/json'
    )


@app.route('/colormaps', methods=['POST'])
@jwt_required()
def create_colormap():
    data = request.get_json()
    name = data.get('name')
    colors = data.get('colors')
    intervals = data.get('intervals')
    use_gradient = data.get('use_gradient', True)
    annotations = data.get('annotations')
    is_relative = data.get('is_relative', False)
    clipping = data.get('clipping', True)  # Add clipping

    if not name or not colors:
        return jsonify({"msg": "Name and colors are required"}), 400

    if intervals and len(intervals) != len(colors):
        return jsonify({"msg": "Intervals length must match colors length"}), 400

    if annotations and len(annotations) != len(intervals):
        return jsonify({"msg": "Annotations length must match intervals length"}), 400

    with get_db_session() as session:
        existing_colormap = ColormapModel.find_by_name(name, session)
        if existing_colormap:
            return jsonify({"msg": "Colormap with this name already exists"}), 400

        colormap = ColormapModel(
            name=name,
            colors=colors,
            intervals=intervals,
            use_gradient=use_gradient,
            annotations=annotations,
            is_relative=is_relative,
            clipping=clipping  # Set clipping
        )
        colormap.create(session)
        colormap_serializable = colormap.to_dict()

    return jsonify(colormap_serializable), 201


@app.route('/colormaps', methods=['GET'])
@jwt_required()
def list_colormaps():
    with get_db_session() as session:
        colormaps = session.query(ColormapModel).all()
        colormaps_serializable = [colormap.to_dict() for colormap in colormaps]
    return jsonify(colormaps_serializable)

@app.route('/colormaps/<string:name>', methods=['GET'])
@jwt_required()
def get_colormap_by_name(name):
    with get_db_session() as session:
        colormap = ColormapModel.find_by_name(name, session)
        if not colormap:
            return jsonify({"msg": "Colormap not found"}), 404
        return jsonify(colormap.to_dict())

@app.route('/colormaps/<int:id>', methods=['PUT'])
@jwt_required()
def update_colormap(id):
    data = request.get_json()
    name = data.get('name')
    colors = data.get('colors')
    intervals = data.get('intervals')
    use_gradient = data.get('use_gradient', True)
    annotations = data.get('annotations')
    is_relative = data.get('is_relative', False)
    clipping = data.get('clipping', True)  # Add clipping

    if not name or not colors:
        return jsonify({"msg": "Name and colors are required"}), 400

    if intervals and len(intervals) != len(colors):
        return jsonify({"msg": "Intervals length must match colors length"}), 400

    if annotations and len(annotations) != len(intervals):
        return jsonify({"msg": "Annotations length must match intervals length"}), 400

    with get_db_session() as session:
        colormap = ColormapModel.find_by_id(id, session)
        if not colormap:
            return jsonify({"msg": "Colormap not found"}), 404

        colormap.update(session, name=name, colors=colors, intervals=intervals,
                        use_gradient=use_gradient, annotations=annotations, is_relative=is_relative, clipping=clipping)
        return jsonify(colormap.to_dict())


@app.route('/colormaps/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_colormap(id):
    with get_db_session() as session:
        colormap = ColormapModel.find_by_id(id, session)
        if not colormap:
            return jsonify({"msg": "Colormap not found"}), 404
        colormap.delete(session)
    return jsonify({"msg": "Colormap deleted successfully"}), 200

@app.route('/reports', methods=['GET'])
@jwt_required()
def get_reports():
    """
    Fetch all reports from the database.
    """
    with get_db_session() as session:
        reports = session.query(ReportModel).all()

        # Use the to_dict method for serialization
        reports_serializable = [report.to_dict() for report in reports]

        return jsonify(reports_serializable), 200


@app.route('/reports/<int:report_id>', methods=['DELETE'])
@jwt_required()
def delete_report(report_id):
    """
    Delete a report by ID.
    """
    with get_db_session() as session:
        report = session.query(ReportModel).filter_by(id=report_id).first()
        if not report:
            return jsonify({"error": "Report not found"}), 404

        session.delete(report)
        session.commit()
        return jsonify({"message": "Report deleted successfully"}), 200


@app.route('/save_report', methods=['POST'])
@jwt_required()
def save_report():
    """
    Save a new report with the provided data.
    """
    data = request.json

    # Extract data from the payload
    report_name   = data.get('report_name')
    colormap_id   = data.get('colormap_id')
    colormap_name = data.get('colormap_name')
    datatype      = data.get('datatype', 'act')
    distance      = data.get('distance', 5.0)
    map_ids       = data.get('map_ids', [])
    additional_data = data.get('additional_data', {})

    # Validate input
    if not report_name:
        return jsonify({"error": "Report name is required."}), 400
    if not isinstance(map_ids, list) or not map_ids:
        return jsonify({"error": "Map IDs must be a non-empty list."}), 400

    # Ensure additional_data contains required information
    additional_data.update({
        "report_name":   report_name,
        "colormap_id":   colormap_id,
        "colormap_name": colormap_name,
        "datatype":      datatype,
        "distance":      distance,
    })

    with get_db_session() as session:
        try:
            # Create and save the report
            new_report = ReportModel(
                map_ids=map_ids,
                additional_data=additional_data
            )
            new_report.create(session)
            return jsonify({"message": "Report saved successfully."}), 200
        except Exception as e:
            return jsonify({"error": f"Failed to save report: {str(e)}"}), 500


def _build_report_excel(report_id):
    """
    Background worker: loads map data, computes areas, writes Excel to disk,
    and updates the report status in the DB.
    """
    def _set_status(status, extra=None):
        with get_db_session() as s:
            r = s.query(ReportModel).filter_by(id=report_id).first()
            if r:
                d = dict(r.additional_data or {})
                d['status'] = status
                if extra:
                    d.update(extra)
                r.additional_data = d
                flag_modified(r, 'additional_data')

    try:
        # --- load everything from DB ---
        with get_db_session() as session:
            report = session.query(ReportModel).filter_by(id=report_id).first()
            if not report:
                return

            additional  = dict(report.additional_data or {})
            report_name = additional.get('report_name', f'report_{report_id}')
            datatype    = additional.get('datatype', 'act')
            distance    = float(additional.get('distance', 5.0))
            colormap_id = additional.get('colormap_id')
            map_ids     = list(report.map_ids)

            interval_pairs  = []
            interval_labels = []
            if colormap_id:
                cm = session.query(ColormapModel).filter_by(id=int(colormap_id)).first()
                if cm and cm.intervals and len(cm.intervals) >= 2:
                    ivs = list(cm.intervals)
                    interval_pairs  = [(ivs[i], ivs[i + 1]) for i in range(len(ivs) - 1)]
                    interval_labels = [f"{ivs[i]:.1f}–{ivs[i + 1]:.1f}" for i in range(len(ivs) - 1)]

            ep_maps    = {}
            meta_info  = {}
            attr_data  = {}
            for mid in map_ids:
                m = session.query(EPMapModel).filter_by(id=mid).first()
                if m is not None:
                    ep_maps[mid]   = m.to_epmap(include_points=True)
                    meta_info[mid] = {'study': m.study_name, 'name': m.map_name}
                epa = session.query(EPMapAttributes).filter_by(map_id=mid).first()
                attr_data[mid] = epa.get_all_attributes() if epa else {}

            # collect all attribute keys in stable order
            attr_keys = list(dict.fromkeys(
                k for mid in map_ids for k in attr_data.get(mid, {})))

        # --- heavy computation (outside DB session) ---
        rows = []
        for mid in map_ids:
            if mid not in ep_maps:
                rows.append({'ID': mid, 'Study': '—', 'Map Name': 'Not found',
                             'Total Area (cm²)': None, 'Min': None, 'Max': None,
                             'Mean': None, 'Std': None})
                continue
            try:
                ep          = ep_maps[mid]
                area_values = ep.calculate_areas_for_intervals(
                    interval_pairs, scalar_name=datatype, distance=distance)
                total_area  = ep.area_of_surface()
                min_s, max_s, avg_s, std_s = ep.get_scalar_statistics(scalar_name=datatype)

                # ── relative interval areas ──
                # Same colormap intervals, but boundaries interpreted as
                # fractions of this map's max score
                rel_pairs = [(lo / 100.0 * float(max_s), hi / 100.0 * float(max_s))
                             for lo, hi in interval_pairs]
                rel_area_values = ep.calculate_areas_for_intervals(
                    rel_pairs, scalar_name=datatype, distance=distance)

                row = {
                    'ID':               mid,
                    'Study':            ep.study_name,
                    'Map Name':         ep.map_name,
                    'Total Area (cm²)': round(float(total_area), 4),
                    'Min':              round(float(min_s), 4),
                    'Max':              round(float(max_s), 4),
                    'Mean':             round(float(avg_s), 4),
                    'Std':              round(float(std_s), 4),
                }
                for label, a_abs, a_rel in zip(interval_labels, area_values, rel_area_values):
                    row[f'{label} (abs)'] = (round(float(a_abs), 4)
                                             if a_abs is not None and not np.isnan(a_abs) else None)
                    row[f'{label} (rel)'] = (round(float(a_rel), 4)
                                             if a_rel is not None and not np.isnan(a_rel) else None)
                for ak in attr_keys:
                    row[ak] = attr_data.get(mid, {}).get(ak)
                rows.append(row)
            except Exception as e:
                print(f"[report {report_id}] Error on map {mid}: {e}")
                rows.append({
                    'ID':       mid,
                    'Study':    meta_info.get(mid, {}).get('study', '—'),
                    'Map Name': meta_info.get(mid, {}).get('name', '—'),
                    'Error':    str(e),
                })

        # --- build Excel ---
        paired_labels = []
        for label in interval_labels:
            paired_labels.append(f'{label} (abs)')
            paired_labels.append(f'{label} (rel)')
        headers = (['ID', 'Study', 'Map Name', 'Total Area (cm²)', 'Min', 'Max', 'Mean', 'Std']
                   + paired_labels + attr_keys)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = report_name[:31]

        header_fill = PatternFill('solid', fgColor='1A1D2E')
        for col, h in enumerate(headers, start=1):
            cell           = ws.cell(row=1, column=col, value=h)
            cell.font      = Font(bold=True, color='FFFFFF')
            cell.fill      = header_fill
            cell.alignment = Alignment(horizontal='center')

        for row in rows:
            ws.append([row.get(h) for h in headers])

        for col in ws.columns:
            width = max((len(str(c.value)) if c.value is not None else 0) for c in col)
            ws.column_dimensions[col[0].column_letter].width = min(width + 4, 40)

        safe_name = report_name.replace(' ', '_')
        filename  = f"{report_id}_{safe_name}.xlsx"
        filepath  = os.path.join(REPORTS_DIR, filename)
        wb.save(filepath)

        _set_status('ready', {'excel_file': filename})
        print(f"[report {report_id}] Done → {filepath}")

    except Exception as e:
        print(f"[report {report_id}] Failed: {e}")
        _set_status('error', {'error': str(e)})


@app.route('/reports/<int:report_id>/generate', methods=['POST'])
@jwt_required()
def generate_report(report_id):
    """Start background Excel generation; returns 202 immediately."""
    with get_db_session() as session:
        report = session.query(ReportModel).filter_by(id=report_id).first()
        if not report:
            return jsonify({"error": "Report not found."}), 404
        # Mark as generating right away
        data = dict(report.additional_data or {})
        data['status'] = 'generating'
        data.pop('error', None)
        report.additional_data = data
        flag_modified(report, 'additional_data')

    threading.Thread(target=_build_report_excel, args=(report_id,), daemon=True).start()
    return jsonify({"message": "Report generation started."}), 202


@app.route('/reports/<int:report_id>/status', methods=['GET'])
@jwt_required()
def report_status(report_id):
    """Return the generation status and, if ready, the filename."""
    with get_db_session() as session:
        report = session.query(ReportModel).filter_by(id=report_id).first()
        if not report:
            return jsonify({"error": "Report not found."}), 404
        additional = report.additional_data or {}
        return jsonify({
            "status":     additional.get('status'),        # generating | ready | error | None
            "excel_file": additional.get('excel_file'),
            "error":      additional.get('error'),
        })


@app.route('/reports/<int:report_id>/download', methods=['GET'])
@jwt_required()
def download_report(report_id):
    """Serve a previously generated report Excel file."""
    with get_db_session() as session:
        report = session.query(ReportModel).filter_by(id=report_id).first()
        if not report:
            return jsonify({"error": "Report not found."}), 404
        filename = (report.additional_data or {}).get('excel_file')

    if not filename:
        return jsonify({"error": "Report has not been generated yet."}), 404

    filepath = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "Report file missing on disk."}), 404

    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
