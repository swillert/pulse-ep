"""Duo_AutoMarksSummaryList (PFA ablation) parser."""

from __future__ import annotations

import numpy as np

from pulse_ep.core.importers.ensite import parse_ensite_duo_automarks
from pulse_ep.core.placed_point import ABLATION_PFA

_DUO = (
    "Export Data Element: Duo_AutoMarksSummaryList_VoXel\n"
    "t_dws,timepoint as seen in DWS in HH:MM:SS format\n"  # legend line — must be skipped
    "t_dws,t_secs,t_usecs,t_ref,Event ID,ID,Electrode ID,"
    "AutoMark Location X,AutoMark Location Y,AutoMark Location Z,PI,"
    "Expected Burst Count,Actual Burst Count,Average Force,Max Force,Therapy Setting,Duration\n"
    "14:12:06,1,2,3,0,7,1,65.5,-151.1,-53.6,51.8,5,5,10.7,55.4,Nominal,8.4,\n"  # trailing comma
)


def test_duo_parses_pfa_ablation_with_aligned_attributes():
    pts = parse_ensite_duo_automarks(_DUO)
    assert len(pts) == 1
    p = pts[0]
    assert p.type == ABLATION_PFA
    # trailing empty field must not shift columns (index_col=False)
    np.testing.assert_allclose(p.position, [65.5, -151.1, -53.6])
    assert p.source_id == "7"
    assert p.attributes["actual_burst_count"] == 5
    assert p.attributes["avg_force"] == 10.7
    assert p.attributes["max_force"] == 55.4
    assert p.attributes["therapy_setting"] == "Nominal"
    assert p.attributes["duration"] == 8.4


def test_duo_empty_yields_nothing():
    assert parse_ensite_duo_automarks("Export Data Element: Duo\n(no data)\n") == []
