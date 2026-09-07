"""What may leave the deployment when a model asks.

A study is named after its export, and a real CARTO one has the shape of
this invented example, ``10054321_XY_AB 01_02_2020 09-15-00`` — a case number, initials and the time
of the procedure. These tests pin that such a name does not reach a tool
result while anonymisation is on, and that turning it off is the operator's
decision and nobody else's.
"""

from __future__ import annotations

from pulse_ep.mcp.anonymize import REDACTED, Anonymiser, anonymiser_from_env

REAL = "10054321_XY_AB 01_02_2020 09-15-00"


def test_the_alias_is_the_database_id():
    """No key file, no mapping table: the id is already everyone's handle."""
    anon = Anonymiser()
    assert anon.alias(12, REAL) == "study/12"


def test_the_name_is_removed_wherever_it_is_embedded():
    """Replacing the one field is not enough — the name is inside paths too."""
    anon = Anonymiser()
    anon.learn(12, REAL)

    scrubbed = anon.scrub(
        {
            "study_name": REAL,
            "note": f"imported from {REAL} on tuesday",
            "waveforms": [{"segment": f"{REAL}/2-RA SR_ECG_Export_13500280"}],
        }
    )
    assert REAL not in repr(scrubbed)
    assert scrubbed["study_name"] == "study/12"
    assert scrubbed["note"] == "imported from study/12 on tuesday"
    # a value shaped like a path goes entirely, name or no name
    assert scrubbed["waveforms"][0]["segment"] == REDACTED


def test_the_alias_survives_scrubbing():
    """It contains a slash, and it is the one such string that must stay."""
    anon = Anonymiser()
    payload = {"study": anon.alias(12, REAL), "maps": [{"study": "study/12"}]}
    assert anon.scrub(payload) == {"study": "study/12", "maps": [{"study": "study/12"}]}


def test_paths_and_free_text_fields_are_redacted():
    """The directory layout of the machine is the operator's business."""
    anon = Anonymiser()
    scrubbed = anon.scrub(
        {
            "mesh_file": "/data/uksh/2024/2-RA SR.mesh",
            "data_uri": "some study/P1_13500280.parquet",
            "operator": "Dr. Someone",
            "notes": "redo case",
            "elsewhere": "/var/lib/pulse/exports/case-4711",
        }
    )
    assert scrubbed["mesh_file"] == REDACTED
    assert scrubbed["data_uri"] == REDACTED
    assert scrubbed["operator"] == REDACTED
    assert scrubbed["notes"] == REDACTED
    # a path that no key list anticipated is caught by its shape
    assert scrubbed["elsewhere"] == REDACTED


def test_measurements_pass_through_untouched():
    """Anonymising must not cost the model the data it is there to reason about."""
    anon = Anonymiser()
    anon.learn(12, REAL)
    payload = {
        "map_name": "2-1-ReRA Pace posterior",  # anatomy and protocol, not a person
        "scalars": [{"name": "voltage_bipolar", "unit": "mV", "min": 0.05, "max": 4.2}],
        "series": {"CS1-CS2": [-0.228, 0.11, 0.42]},
        "vendor": "carto",
    }
    assert anon.scrub(payload) == payload


def test_switching_it_off_returns_the_real_identity():
    anon = Anonymiser(enabled=False)
    assert anon.alias(12, REAL) == REAL
    assert anon.scrub({"study_name": REAL})["study_name"] == REAL


def test_every_answer_says_which_mode_it_came_from():
    assert Anonymiser().envelope({"count": 1})["anonymized"] is True
    assert Anonymiser(enabled=False).envelope({"count": 1})["anonymized"] is False


def test_a_study_with_no_id_is_redacted_rather_than_named():
    """Failing closed: no id to alias to is not a reason to send the name."""
    assert Anonymiser().alias(None, REAL) == REDACTED


def test_the_default_is_on_and_only_an_explicit_value_turns_it_off():
    """A typo in the configuration must not quietly expose a study."""
    assert anonymiser_from_env({}).enabled is True
    assert anonymiser_from_env({"PULSE_EP_MCP_ANONYMIZE": "1"}).enabled is True
    assert anonymiser_from_env({"PULSE_EP_MCP_ANONYMIZE": "yes"}).enabled is True
    assert anonymiser_from_env({"PULSE_EP_MCP_ANONYMIZE": "flase"}).enabled is True  # typo
    for off in ("0", "false", "no", "off", "OFF"):
        assert anonymiser_from_env({"PULSE_EP_MCP_ANONYMIZE": off}).enabled is False


def test_the_command_line_flag_wins_over_the_environment():
    env = {"PULSE_EP_MCP_ANONYMIZE": "0"}
    assert anonymiser_from_env(env, override=True).enabled is True
    assert anonymiser_from_env({}, override=False).enabled is False
