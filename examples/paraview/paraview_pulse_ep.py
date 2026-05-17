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
import ssl
import urllib.error
import urllib.request

import vtk

# ---------------------------------------------------------------------
# User-editable parameters
# ---------------------------------------------------------------------
MAP_ID = 1  # ID of the EPMap to load (see GET /list_epmaps_in_study/<id>)
SCALAR_NAME = "act"  # "act", "voltage", "similarity_score", …
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
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get(path, token):
    req = urllib.request.Request(
        _BASE_URL + path,
        headers={"Authorization": "Bearer " + token},
        method="GET",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _login():
    if not _PASSWORD:
        raise RuntimeError(
            "PULSE_EP_PASSWORD is not set. Launch ParaView from a shell "
            "that exports PULSE_EP_BASE_URL / PULSE_EP_USERNAME / "
            "PULSE_EP_PASSWORD."
        )
    resp = _http_post("/login_user", {"username": _USER, "password": _PASSWORD})
    return resp["access_token"]


def _build_polydata(mesh):
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

    polydata.GetPointData().AddArray(_to_vtk_array(scalars, SCALAR_NAME))
    polydata.GetPointData().AddArray(_to_vtk_array(normalized, SCALAR_NAME + "_normalized"))
    polydata.GetPointData().SetActiveScalars(SCALAR_NAME)
    return polydata


def main():
    try:
        token = _login()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"pulse-ep login failed: HTTP {exc.code}") from exc

    path = (
        "/get_mesh_data"
        "?map_id=" + str(MAP_ID) + "&scalar_name=" + SCALAR_NAME + "&distance=" + str(DISTANCE)
    )
    mesh = _http_get(path, token)
    polydata = _build_polydata(mesh)

    # In the ParaView Programmable Source context, "self" is a
    # vtkProgrammableSource instance whose output we have to populate.
    output = self.GetPolyDataOutput()  # noqa: F821  (provided by ParaView)
    output.ShallowCopy(polydata)


main()
