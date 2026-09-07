"""ParaView Programmable Source: load a pulse-ep map via REST.

Usage
-----
1. In ParaView: ``Sources → Programmable Source``.
2. Set ``Output DataSet Type`` to ``vtkPolyData``.
3. Paste the **entire content of this file** into the *Script* box.
4. Edit ``MAP_ID`` (and optionally ``SCALAR_NAME`` / ``DISTANCE``) below.
5. Press *Apply*. ParaView fetches the mesh from the pulse-ep server
   every time you re-apply, so you can browse studies live.

The script reads credentials from environment variables. Launch ParaView
from a shell that exports them::

    export PULSE_EP_BASE_URL="http://127.0.0.1:5000"
    export PULSE_EP_USERNAME="admin"
    export PULSE_EP_PASSWORD="..."
    paraview &

Only standard-library Python is used; ParaView ships its own Python so
external packages cannot be relied on.
"""

import json
import os
import urllib.error
import urllib.request

# ParaView ships a Python built without _ssl (6.1.1 among them), so importing
# ssl unconditionally makes this script unusable inside ParaView. It is only
# needed to talk to an HTTPS server; over plain HTTP urllib needs no context.
try:
    import ssl
except ImportError:  # pragma: no cover - depends on the ParaView build
    ssl = None

import vtk

# ---------------------------------------------------------------------
# User-editable parameters
# ---------------------------------------------------------------------
MAP_ID = 1  # ID of the EPMap to load (see GET /list_epmaps_in_study/<id>)
# None asks the server for the map's own primary quantity, which differs
# between vendors — a CARTO map has activation_time, an EnSite X one
# voltage_bipolar. List a map's fields with GET /epmaps/<id>/scalars.
SCALAR_NAME = None  # or e.g. "voltage_bipolar", "activation_time"
DISTANCE = 5.0  # interpolation radius around catheter points [mm]

# ---------------------------------------------------------------------
# Implementation — no edits required below this line
# ---------------------------------------------------------------------

_BASE_URL = os.environ.get("PULSE_EP_BASE_URL", "http://127.0.0.1:5000")
_USER = os.environ.get("PULSE_EP_USERNAME", "admin")
_PASSWORD = os.environ.get("PULSE_EP_PASSWORD", "")


def _http_post(path, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _BASE_URL + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=_ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get(path, token):
    req = urllib.request.Request(
        _BASE_URL + path,
        headers={"Authorization": "Bearer " + token},
        method="GET",
    )
    with urllib.request.urlopen(req, context=_ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ssl_context():
    """A TLS context for https:// URLs, or None when none is needed.

    Returns None over plain HTTP, and raises a clear message rather than an
    ImportError when a ParaView build without ssl is asked for HTTPS.
    """
    if not _BASE_URL.lower().startswith("https://"):
        return None
    if ssl is None:
        raise RuntimeError(
            "This ParaView build has no ssl module, so it cannot reach an "
            "https:// pulse-ep server. Use an http:// URL, or run the script "
            "with a Python that has ssl."
        )
    return ssl.create_default_context()


def _login():
    if not _PASSWORD:
        raise RuntimeError(
            "PULSE_EP_PASSWORD is not set. Launch ParaView from a shell "
            "that exports PULSE_EP_BASE_URL / PULSE_EP_USERNAME / "
            "PULSE_EP_PASSWORD."
        )
    resp = _http_post("/login_user", {"username": _USER, "password": _PASSWORD})
    return resp["access_token"]


def _build_polydata(mesh, scalar_name):
    """Translate the /get_mesh_data response into a vtkPolyData."""
    vertices = mesh["mesh_data"]["vertices"]
    faces = mesh["mesh_data"]["faces"]
    scalars = mesh["mesh_data"]["scalar_data"]
    normalized = mesh["mesh_data"]["normalized_scalar_data"]

    points = vtk.vtkPoints()
    for x, y, z in vertices:
        points.InsertNextPoint(x, y, z)

    triangles = vtk.vtkCellArray()
    for tri in faces:
        triangles.InsertNextCell(3)
        for vi in tri:
            triangles.InsertCellPoint(vi)

    polydata = vtk.vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetPolys(triangles)

    def _to_vtk_array(values, name):
        arr = vtk.vtkFloatArray()
        arr.SetName(name)
        arr.SetNumberOfComponents(1)
        for v in values:
            arr.InsertNextValue(float("nan") if v is None else float(v))
        return arr

    polydata.GetPointData().AddArray(_to_vtk_array(scalars, scalar_name))
    polydata.GetPointData().AddArray(_to_vtk_array(normalized, scalar_name + "_normalized"))
    polydata.GetPointData().SetActiveScalars(scalar_name)
    return polydata


def main():
    try:
        token = _login()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"pulse-ep login failed: HTTP {exc.code}") from exc

    # Omit scalar_name entirely when unset, so the server resolves the map's
    # own primary quantity; the response tells us which one it used.
    path = "/get_mesh_data?map_id=" + str(MAP_ID) + "&distance=" + str(DISTANCE)
    if SCALAR_NAME:
        path += "&scalar_name=" + SCALAR_NAME
    mesh = _http_get(path, token)
    scalar_name = SCALAR_NAME or mesh.get("scalar_name") or "scalar"
    polydata = _build_polydata(mesh, scalar_name)

    # In the ParaView Programmable Source context, "self" is a
    # vtkProgrammableSource instance whose output we have to populate.
    output = self.GetPolyDataOutput()  # noqa: F821  (provided by ParaView)
    output.ShallowCopy(polydata)


main()
