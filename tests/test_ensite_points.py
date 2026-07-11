"""EnSite map_*_points.csv -> vendor-neutral MeasurementPoints."""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.ensite import parse_ensite_points

_POINTS = (
    "x,y,z,locChA_x,locChA_y,locChA_z,locChB_x,locChB_y,locChB_z,"
    "pp,ppVmax,unipoleMaxPP,lat,correctedLAT,force,score,snr,correlationCoefficient\n"
    "1,2,3, 1.1,2.1,3.1, 0.9,1.9,2.9, 0.71,0.71,0.66, 182.4,182.4, -1, 100, 70.6, 0.16\n"
    "4,5,6, 4.1,5.1,6.1, 3.9,4.9,5.9, 0.61,0.61,0.66, 193.9,193.9, 12.5, 100, 77.9, 0.88\n"
)


def test_parses_position_measurements_and_electrodes():
    pts = parse_ensite_points(_POINTS)
    assert len(pts) == 2

    p0 = pts[0]
    np.testing.assert_array_equal(p0.position, [1, 2, 3])
    # open measurements, keyed by kind name
    assert p0.get("voltage_bipolar") == 0.71
    assert p0.get("voltage_unipolar") == 0.66
    assert p0.get("activation_time") == 182.4
    assert p0.get("correlation") == 0.16
    assert p0.get("snr") == 70.6
    # electrodes as an open map
    np.testing.assert_allclose(p0.electrodes["A"], [1.1, 2.1, 3.1])
    np.testing.assert_allclose(p0.electrodes["B"], [0.9, 1.9, 2.9])


def test_force_sentinel_dropped_but_kept_when_real():
    pts = parse_ensite_points(_POINTS)
    assert "contact_force" not in pts[0].measurements  # force == -1 → no sensor
    assert pts[1].get("contact_force") == 12.5


def test_measurement_units_from_kind():
    p = parse_ensite_points(_POINTS)[0]
    assert p.measurements["voltage_bipolar"].unit == "mV"
    assert p.measurements["activation_time"].unit == "ms"
    assert p.measurements["contact_force" if False else "correlation"].unit == ""
