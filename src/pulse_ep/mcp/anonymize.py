"""Deciding what may leave the deployment.

An MCP tool result is sent to a language model — that is, off the machine the
database sits on. pulse-ep's own rule ("no patient data in the repository")
has the same reasoning behind it, so the same care applies here, and the
identifying part of a study is not hypothetical: an imported study is named
after its export, and a real one has the shape of this invented example

    10054321_XY_AB 01_02_2020 09-15-00

a case number, initials and the time of the procedure. That name is also
embedded in stored file paths (``<study name>/<map>_ECG_Export_….parquet``),
so replacing one field is not enough.

**The alias is the database id** — ``study/12``. No key file to carry around,
no mapping table to keep in sync and to lose: the id is already the handle
every surface uses, and whoever operates the deployment resolves it in one
query. A random token would only add a second secret to store.

What is *not* anonymised, deliberately: map names (``1-LA Sinus``,
``2-1-ReRA Pace posterior``) are anatomy and protocol, they identify a
chamber and not a person — and hiding them would leave the model unable to
say anything useful about a study. Vendor, quantities, geometry and signal
values are likewise measurements, not identifiers.

Anonymisation is **on by default** and is switched by whoever starts the
server (``--no-anonymize``, or ``PULSE_EP_MCP_ANONYMIZE=0``). It is
deliberately *not* exposed as a tool: a model must not be able to turn off
the protection it is subject to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Payload keys whose value is replaced wholesale. Free-text and path fields
#: that no analysis needs, and that are the likeliest place for a name, a
#: note or a directory layout to travel along.
REDACTED_KEYS: frozenset[str] = frozenset(
    {
        "operator",
        "notes",
        "comment",
        "comments",
        "patient",
        "patient_id",
        "patient_name",
        "date_of_birth",
        "dob",
        "source_path",
        "mesh_file",
        "data_uri",
        "file",
        "filename",
        "path",
    }
)

REDACTED = "[redacted]"

#: A study id as it appears in an anonymised payload — the one slash-bearing
#: string that must survive scrubbing, since it is the alias itself.
ALIAS_RE = re.compile(r"^study/(\d+)$")


def _looks_like_a_path(value: str) -> bool:
    return "/" in value or "\\" in value


@dataclass
class Anonymiser:
    """Rewrites tool payloads so they carry no study identity.

    Stateful on purpose: it *learns* each study's name as the server resolves
    it, and then removes that name from every string in every later payload —
    which is what catches the places a name is embedded rather than stored,
    such as a waveform's stored path.
    """

    enabled: bool = True
    #: study id -> the name the export gave it
    _names: dict[int, str] = field(default_factory=dict, repr=False)

    # -- identity ---------------------------------------------------------

    def learn(self, study_id: int | None, study_name: str | None) -> None:
        """Remember a study's real name so it can be removed from payloads."""
        if study_id is not None and study_name:
            self._names[int(study_id)] = str(study_name)

    def alias(self, study_id: int | None, study_name: str | None = None) -> str | None:
        """What a study is called in a tool result."""
        self.learn(study_id, study_name)
        if not self.enabled:
            return study_name
        if study_id is None:
            return REDACTED
        return f"study/{int(study_id)}"

    # -- payloads ---------------------------------------------------------

    def scrub(self, value):
        """Recursively remove study identity from a JSON-ish payload.

        Three passes, because a name reaches a client in three shapes: as a
        field of its own, inside a path, and embedded in some other string.
        """
        if not self.enabled:
            return value
        return self._scrub(value)

    def _scrub(self, value):
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if str(key).strip().casefold() in REDACTED_KEYS:
                    out[key] = REDACTED if item is not None else None
                elif str(key).strip().casefold() in ("study_name", "name") and isinstance(
                    item, str
                ):
                    out[key] = self._replace_names(item)
                else:
                    out[key] = self._scrub(item)
            return out
        if isinstance(value, (list, tuple)):
            return [self._scrub(v) for v in value]
        if isinstance(value, str):
            return self._scrub_text(value)
        return value

    def _scrub_text(self, text: str) -> str:
        """One string, in the order the three rules have to apply.

        The shape test comes *before* the name replacement, or an alias would
        make its own container look like a path: ``study/12`` is not a
        directory, and neither is a sentence that happens to contain a slash
        only because a name was replaced in it.
        """
        if ALIAS_RE.match(text.strip()):
            return text
        # A path that survived the key list still describes the machine's
        # directory layout, which is nobody's business but the operator's —
        # and it is where an export name hides most often.
        if _looks_like_a_path(text):
            return REDACTED
        return self._replace_names(text)

    def _replace_names(self, text: str) -> str:
        for study_id, name in self._names.items():
            if name and name in text:
                text = text.replace(name, f"study/{study_id}")
        return text

    def envelope(self, payload: dict) -> dict:
        """Tag a result with the mode it was produced in.

        Every tool says whether it was anonymised, so neither the reader nor
        the model has to assume — and a session that is *not* anonymised says
        so in every single answer.
        """
        return {**payload, "anonymized": self.enabled}


def anonymiser_from_env(env, override: bool | None = None) -> Anonymiser:
    """Build the anonymiser from ``PULSE_EP_MCP_ANONYMIZE`` (default: on).

    ``override`` is the command-line flag, which wins over the environment.
    Anything other than an explicit off value keeps it on: a typo in the
    configuration must not silently expose a study.
    """
    if override is not None:
        return Anonymiser(enabled=override)
    raw = str(env.get("PULSE_EP_MCP_ANONYMIZE", "")).strip().casefold()
    return Anonymiser(enabled=raw not in {"0", "false", "no", "off"})
