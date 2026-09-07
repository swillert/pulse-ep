"""Boundary values must belong to one bin of an adjacent partition."""
import numpy as np
import pytest
import pyvista as pv
from pulse_ep import EPMap


def _map():
    # Disconnected equal-area triangles avoid interpolation across bin edges.
    vertices = np.array(
        [[x, y, 0] for base in (0, 2, 4) for x, y in ((base, 0), (base+1, 0), (base, 1))], float)
    faces = np.arange(9).reshape(3, 3)
    values = np.repeat([0.0, 1.0, 2.0], 3)
    m = EPMap('boundaries', 'synthetic', vertices=vertices, triangles=faces)
    m.register_scalar('voltage_bipolar', values, kind='voltage_bipolar', unit='mV')
    m.pv_mesh = pv.PolyData(vertices, np.c_[np.full(3, 3), faces])
    m.pv_mesh.point_data['voltage_bipolar'] = values
    return m


def test_single_half_open_range_excludes_its_upper_edge():
    m = _map()
    assert m.area_of_range(0, 1, 'voltage_bipolar') == pytest.approx(0.005)
    assert m.area_of_range(1, 2, 'voltage_bipolar') == pytest.approx(0.005)
    assert m.area_of_range(1, 2, 'voltage_bipolar', include_upper=True) == pytest.approx(0.010)


def test_adjacent_bins_count_boundary_triangles_once(monkeypatch):
    m = _map()
    monkeypatch.setattr(m, 'generate_anatomical_pv_mesh', lambda **kwargs: m.pv_mesh)
    monkeypatch.setattr(m, 'interpolate_scalar_values', lambda data, **kwargs: (m.pv_mesh, data))
    areas = m.calculate_areas_for_intervals([(0, 1), (1, 2)], 'voltage_bipolar')
    assert areas == pytest.approx([0.005, 0.010])
    assert sum(areas) == pytest.approx(0.015)
    # Endpoint ownership is independent of the supplied bin order.
    assert m.calculate_areas_for_intervals([(1, 2), (0, 1)], 'voltage_bipolar') == pytest.approx(areas[::-1])
