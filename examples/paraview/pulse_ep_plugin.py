"""pulse-ep as a ParaView source plugin.

Load it once (Tools → Manage Plugins → Load New…, pick this file, tick
*Auto Load*) and pulse-ep appears under **Sources → pulse-ep Map**. Map,
quantity and interpolation distance become ordinary property widgets, so a
map is chosen by editing a field and pressing *Apply* rather than by editing
source code — and the choice is saved in the ParaView state file.

    export PULSE_EP_BASE_URL="http://127.0.0.1:5000"
    export PULSE_EP_USERNAME="admin"
    export PULSE_EP_PASSWORD="…"
    paraview &

The **password is only ever read from the environment**, never entered in a
property: ParaView writes property values into state files and traces, and a
password does not belong in either.

This file deliberately repeats the small REST/VTK bridge from
``paraview_pulse_ep.py`` instead of importing it. That script's whole point is
that it can be pasted into a Programmable Source box, which rules out
depending on a sibling file; a plugin, in turn, has to stand alone as one
file. Both talk to the same three endpoints.

Only ParaView's own Python is used — it ships without pip, so no external
package can be relied on.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

# ParaView ships Python builds without _ssl (6.1.1 among them), so importing
# ssl unconditionally would make the plugin unloadable. It is only needed to
# reach an https:// server.
try:
    import ssl
except ImportError:  # pragma: no cover - depends on the ParaView build
    ssl = None

from paraview.util.vtkAlgorithm import smdomain, smproperty, smproxy
from vtkmodules.numpy_interface import dataset_adapter as dsa  # noqa: F401  (ParaView needs it)
from vtkmodules.util.vtkAlgorithm import VTKPythonAlgorithmBase
from vtkmodules.vtkCommonCore import vtkFloatArray, vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

_TIMEOUT = 60


def _ssl_context(base_url: str):
    """A TLS context for https:// URLs, or None when none is needed."""
    if not base_url.lower().startswith("https://"):
        return None
    if ssl is None:
        raise RuntimeError(
            "This ParaView build has no ssl module, so it cannot reach an "
            "https:// pulse-ep server. Use an http:// URL, or run ParaView "
            "with a Python that has ssl."
        )
    return ssl.create_default_context()


def _post(base_url: str, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        base_url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_ssl_context(base_url)) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(base_url: str, path: str, token: str) -> dict:
    req = urllib.request.Request(
        base_url + path,
        headers={"Authorization": "Bearer " + token},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_ssl_context(base_url)) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _login(base_url: str, username: str) -> str:
    password = os.environ.get("PULSE_EP_PASSWORD", "")
    if not password:
        raise RuntimeError(
            "PULSE_EP_PASSWORD is not set. Launch ParaView from a shell that "
            "exports PULSE_EP_BASE_URL / PULSE_EP_USERNAME / PULSE_EP_PASSWORD."
        )
    try:
        resp = _post(base_url, "/login_user", {"username": username, "password": password})
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"pulse-ep login failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"cannot reach pulse-ep at {base_url}: {exc.reason}") from exc
    return resp["access_token"]


def fetch_polydata(base_url: str, username: str, map_id: int, scalar_name: str, distance: float):
    """The map as a vtkPolyData, plus the quantity the server actually used."""
    token = _login(base_url, username)

    query = {"map_id": str(map_id), "distance": str(distance)}
    # Omitting scalar_name lets the server resolve the map's own primary
    # quantity, which differs by vendor — activation_time for CARTO,
    # voltage_bipolar for EnSiteX. Never guess a field name here.
    if scalar_name:
        query["scalar_name"] = scalar_name
    mesh = _get(base_url, "/get_mesh_data?" + urllib.parse.urlencode(query), token)

    data = mesh["mesh_data"]
    name = scalar_name or mesh.get("scalar_name") or "scalar"

    points = vtkPoints()
    for x, y, z in data["vertices"]:
        points.InsertNextPoint(x, y, z)

    polys = vtkCellArray()
    for tri in data["faces"]:
        polys.InsertNextCell(3)
        for vertex in tri:
            polys.InsertCellPoint(vertex)

    polydata = vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetPolys(polys)

    def _array(values, array_name):
        arr = vtkFloatArray()
        arr.SetName(array_name)
        arr.SetNumberOfComponents(1)
        for v in values:
            # An unmeasured vertex is null in JSON; NaN keeps it out of the
            # colour map instead of dragging the range down to zero.
            arr.InsertNextValue(float("nan") if v is None else float(v))
        return arr

    polydata.GetPointData().AddArray(_array(data["scalar_data"], name))
    polydata.GetPointData().AddArray(_array(data["normalized_scalar_data"], name + "_normalized"))
    polydata.GetPointData().SetActiveScalars(name)
    return polydata, name


@smproxy.source(name="PulseEPMapSource", label="pulse-ep Map")
class PulseEPMapSource(VTKPythonAlgorithmBase):
    """Fetches one electroanatomical map from a pulse-ep server."""

    def __init__(self):
        super().__init__(nInputPorts=0, nOutputPorts=1, outputType="vtkPolyData")
        self._base_url = os.environ.get("PULSE_EP_BASE_URL", "http://127.0.0.1:5000")
        self._username = os.environ.get("PULSE_EP_USERNAME", "admin")
        self._map_id = 1
        self._scalar_name = ""
        self._distance = 5.0

    @smproperty.stringvector(name="ServerURL", default_values="")
    @smdomain.xml("<Documentation>Base URL. Empty: $PULSE_EP_BASE_URL.</Documentation>")
    def SetServerURL(self, value):
        value = (value or "").strip()
        self._base_url = value or os.environ.get("PULSE_EP_BASE_URL", "http://127.0.0.1:5000")
        self.Modified()

    @smproperty.stringvector(name="Username", default_values="")
    @smdomain.xml(
        "<Documentation>Empty: $PULSE_EP_USERNAME. The password is read "
        "from $PULSE_EP_PASSWORD and is never a property.</Documentation>"
    )
    def SetUsername(self, value):
        value = (value or "").strip()
        self._username = value or os.environ.get("PULSE_EP_USERNAME", "admin")
        self.Modified()

    @smproperty.intvector(name="MapID", default_values=1)
    @smdomain.xml(
        "<IntRangeDomain name='range' min='1' />"
        "<Documentation>Map to load; see GET /list_epmaps_in_study/&lt;id&gt;."
        "</Documentation>"
    )
    def SetMapID(self, value):
        self._map_id = int(value)
        self.Modified()

    @smproperty.stringvector(name="ScalarName", default_values="")
    @smdomain.xml(
        "<Documentation>Quantity to load. Empty asks the server for this "
        "map's primary one — activation_time on a CARTO map, "
        "voltage_bipolar on an EnSiteX one. List them with "
        "GET /epmaps/&lt;id&gt;/scalars.</Documentation>"
    )
    def SetScalarName(self, value):
        self._scalar_name = (value or "").strip()
        self.Modified()

    @smproperty.doublevector(name="Distance", default_values=5.0)
    @smdomain.xml(
        "<DoubleRangeDomain name='range' min='0' />"
        "<Documentation>Interpolation radius around catheter points, in mm."
        "</Documentation>"
    )
    def SetDistance(self, value):
        self._distance = float(value)
        self.Modified()

    def RequestData(self, request, in_info, out_info):
        polydata, name = fetch_polydata(
            self._base_url, self._username, self._map_id, self._scalar_name, self._distance
        )
        output = vtkPolyData.GetData(out_info, 0)
        output.ShallowCopy(polydata)
        print(
            f"pulse-ep: map {self._map_id} — {polydata.GetNumberOfPoints()} points, "
            f"{polydata.GetNumberOfCells()} cells, scalar '{name}'"
        )
        return 1
