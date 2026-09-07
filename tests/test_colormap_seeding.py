"""Re-seeding must correct a shipped default without overwriting an operator.

The seeder skipped every colormap it already found, so a corrected definition
never reached a database seeded once — then it learned to bring `is_relative`
in step, and only that one. `clipping` and `use_gradient` are the same kind of
setting, and `viridis_0_3_mV`'s fixed 0–3 mV scale depends on clipping being
on, so a database seeded before that definition existed would keep the wrong
one for good.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pulse_ep.cli.populate_colormaps import (
    SYNCED_FLAGS,
    flags_to_sync,
    predefined_colormaps,
)


def _stored(**flags):
    return SimpleNamespace(
        **{"is_relative": False, "clipping": False, "use_gradient": True, **flags}
    )


def test_nothing_to_do_when_the_stored_flags_already_match():
    assert flags_to_sync(_stored(), {"name": "x"}) == {}


def test_every_display_flag_is_brought_in_step():
    definition = {"name": "viridis_0_3_mV", "is_relative": False, "clipping": True}
    assert flags_to_sync(_stored(clipping=False), definition) == {"clipping": True}

    stored = _stored(is_relative=True, clipping=False, use_gradient=False)
    assert flags_to_sync(stored, definition) == {
        "is_relative": False,
        "clipping": True,
        "use_gradient": True,
    }


def test_a_definition_that_omits_a_flag_falls_back_to_its_default():
    """The seeder's own defaults, so an omission is not read as a change."""
    assert flags_to_sync(_stored(), {"name": "x"}) == {}
    assert flags_to_sync(_stored(use_gradient=False), {"name": "x"}) == {"use_gradient": True}


def test_colours_and_intervals_are_never_touched():
    """What an operator edited in the viewer stays theirs."""
    assert "colors" not in SYNCED_FLAGS and "intervals" not in SYNCED_FLAGS
    stored = _stored()
    stored.colors, stored.intervals = ["#000000"], [0.0]
    flags_to_sync(stored, {"name": "x", "colors": ["#ffffff"], "intervals": [1.0]})
    assert stored.colors == ["#000000"] and stored.intervals == [0.0]


# --- the shipped definitions themselves --------------------------------------


@pytest.mark.parametrize("colormap", predefined_colormaps, ids=lambda c: c["name"])
def test_a_shipped_colormap_is_one_the_viewer_can_render(colormap):
    """The viewer requires one interval per colour, and refuses anything else."""
    assert len(colormap["colors"]) == len(colormap["intervals"])
    annotations = colormap.get("annotations")
    if annotations:
        assert len(annotations) == len(colormap["intervals"])
    for colour in colormap["colors"]:
        assert len(colour) == 7 and colour.startswith("#")
        int(colour[1:], 16)


def test_the_fixed_millivolt_scale_is_absolute_and_clipped():
    """It exists to be a fixed 0-3 mV scale; both flags are what make it one."""
    (fixed,) = [c for c in predefined_colormaps if c["name"] == "viridis_0_3_mV"]
    assert fixed["is_relative"] is False  # not renormalised per map
    assert fixed["clipping"] is True  # values outside 0-3 keep the end colours
    assert fixed["intervals"][0] == 0 and fixed["intervals"][-1] == 3
