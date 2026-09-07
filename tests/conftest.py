"""Shared fixtures for the pulse-ep test suite."""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def synthetic_atrium_arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Small ellipsoidal mesh + Gaussian score field — array form.

    Matches what the importer would yield, but built from pure NumPy so
    no CARTO files are involved.
    """
    from pulse_ep.examples.demo_synthetic import (
        gaussian_score_field,
        make_synthetic_atrium,
    )

    vertices, triangles = make_synthetic_atrium(resolution=16)
    scores, _ = gaussian_score_field(vertices, sigma_mm=6.0, noise_std=0.0)
    return vertices, triangles, scores


#: One EnSite X waveform export, preamble and all. Here rather than in a test
#: module because four tests need it: importing it across test files worked
#: under ``python -m pytest``, which puts the working directory on the import
#: path, and failed under the bare ``pytest`` the CI runs. Shared test data
#: belongs in a fixture, which is reachable either way.
ENSITE_WAVEFORM_CSV = """Export File Version: 5.2
Export Data Element: EP_Catheter_Bipolar_Waveforms_Filtered
Exported from Software Version: 3.0.1
Export from Study: b180
Export from Segment: Stim LA
Highpass: 30 Hz
Lowpass: 300 Hz
Notch: NT_ON
Number of Catheters: 1
Catheter[0](name, num electrodes): RV,2
   Electrode[0](name, channel): D,130
   Electrode[1](name, channel): 2,131
Number of waves (columns): ,7
Number of samples (rows): ,3
t_dws,t_secs,t_usecs,t_ref,RV(D-2)_c0,RV(D-2)_c0_ds,RV(D-2)_c0_ps,RV(2-3)_c1,RV(2-3)_c1_ds,RV(2-3)_c1_ps
 11:40:50.960,1712835650,960324,0,0.0215,0,0,0.0940,0,0
 11:40:50.961,1712835650,960824,0.0005,0.0351,0,0,0.0483,0,0
 11:40:50.961,1712835650,961324,0.0010,0.0493,0,0,-0.0114,0,0
"""


@pytest.fixture
def ensite_waveform_csv() -> str:
    """The export above, for tests that parse a waveform."""
    return ENSITE_WAVEFORM_CSV
