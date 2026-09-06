#!/usr/bin/env python3
"""Derive data-free test fixtures from real vendor exports.

A fixture written from our own idea of a vendor's format would only test the
parser against that idea: if the understanding is wrong, the generator encodes
the same error and the test passes anyway. So this reads a *real* export, keeps
its structure — element names, attributes, section order, column headers — and
replaces only the payload with a synthetic mesh and synthetic values. Every
identifier is dropped.

The real exports stay outside the repository; only the generated fixtures are
committed. This is a development tool, not part of the package.

    python tools/make_synthetic_fixtures.py \
        --ensite "data/ensite/2026_07_09_08_55_30.zip" \
        --carto  /tmp/carto-export \
        --out    tests/fixtures/synthetic
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

import numpy as np
from lxml import etree

from pulse_ep.core.importers.source import source_for


def _fresh(path: Path) -> Path:
    """An empty vendor directory, leaving everything beside it alone.

    Only the vendor subtree is cleared. Wiping the parent instead once took
    the fixture README with it — before it had ever been committed.
    """
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def synthetic_mesh(resolution: int = 32):
    """A closed surface with a scar-like voltage field and a spreading LAT.

    Not a Gaussian blob: a low-voltage region with a border zone on otherwise
    healthy tissue, and an activation time that spreads from one earliest site.
    The numbers are invented, but they occupy the ranges a real map does
    (0.1-2.5 mV, tens of ms), so a figure drawn from this fixture shows what
    the software does with a map rather than with a test pattern.
    """
    from pulse_ep.examples.demo_synthetic import make_synthetic_atrium

    vertices, triangles = make_synthetic_atrium(resolution=resolution)
    vertices = np.asarray(vertices, float)
    rng = np.random.default_rng(20260906)

    # scar centred on one flank, with a graded border zone
    scar = vertices[int(np.argmax(vertices[:, 0]))]
    d_scar = np.linalg.norm(vertices - scar, axis=1)
    healthy, dense_scar = 2.4, 0.12
    voltage = dense_scar + (healthy - dense_scar) / (1.0 + np.exp(-(d_scar - 16.0) / 4.0))
    voltage += rng.normal(0.0, 0.05, size=voltage.shape)
    voltage = np.clip(voltage, 0.05, None)

    # activation spreading from the opposite pole at ~0.7 mm/ms, slowed in scar
    early = vertices[int(np.argmin(vertices[:, 0]))]
    d_early = np.linalg.norm(vertices - early, axis=1)
    slowing = 1.0 + 1.4 * np.exp(-((d_scar / 14.0) ** 2))
    lat = d_early / 0.7 * slowing
    lat = lat - lat.min() + rng.normal(0.0, 0.8, size=lat.shape)

    return vertices, np.asarray(triangles, int), voltage, lat


def _numbers(el, values, per_line: int | None = None) -> None:
    """Replace an element's numeric payload, keeping its formatting style."""
    flat = np.asarray(values).ravel()
    if per_line:
        rows = flat.reshape(-1, per_line)
        el.text = "\n" + "\n".join("  " + "  ".join(f"{v:.4f}" for v in r) for r in rows) + "\n"
    else:
        el.text = " " + " ".join(f"{v:g}" for v in flat) + " "


def build_ensite(real_zip: str, out_dir: Path) -> None:
    """A DIF export whose structure is the real file's, with synthetic content."""
    src = source_for(real_zip)
    dif_name = sorted(src.list("*Contact_Mapping_Model*.xml"))[0]
    root = etree.fromstring(src.open(dif_name).read())

    verts, tris, volts, _lat = synthetic_mesh()
    n_v, n_t = len(verts), len(tris)

    for comment in root.xpath("//comment()"):
        comment.getparent().remove(comment)  # they name the source study

    vol = root.find(".//Volume")
    vol.set("name", "Surface1")

    # The stored camera pose is real: its translation is where that operator
    # had the study's heart on screen. Nothing here needs it, so reset it to
    # the identity rather than ship a number derived from a patient study.
    view = vol.find("AP_MapViewMatrix")
    if view is not None:
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        view.text = " " + " ".join(f"{v:.6f}" for v in identity) + " "

    def put(tag, values, count, per_line=None):
        el = vol.find(tag)
        if el is None:
            return
        el.set("number", str(count))
        _numbers(el, values, per_line)

    put("Vertices", verts, n_v, per_line=3)
    put("Map_data", volts, n_v)
    put("Map_color", np.zeros(n_v), n_v)
    put("Map_status", np.zeros(n_v), n_v)  # 0 = valid
    put("Normals", verts / np.linalg.norm(verts, axis=1, keepdims=True), n_v, per_line=3)
    put("Polygons", tris + 1, n_t * 2, per_line=3)  # DIF indices are 1-based
    put("Surface_of_origin", np.zeros(n_t * 2), n_t * 2)
    put("Color_high_low", [float(volts.max()), float(volts.min())], 2)

    labels = root.find(".//Labels")
    if labels is not None:
        labels.getparent().remove(labels)  # operator annotations

    sig = root.find(".//MD5Signature")
    if sig is not None:
        sig.text = ""

    out = _fresh(out_dir / "ensite" / "synthetic_study")
    (out / "Contact_Mapping_Model.xml").write_bytes(
        etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=False)
    )
    _ensite_points(src, out, verts, volts)
    print(f"  EnSiteX: {n_v} Vertices, {n_t * 2} Dreiecke -> {out}")


def _ensite_points(src, out: Path, verts, volts) -> None:
    """A Map_PP_bi.csv keeping the real preamble and column header."""
    pp_name = next((n for n in src.list("*Map_PP_*.csv")), None)
    if pp_name is None:
        return
    text = src.open(pp_name).read().decode("utf-8", "ignore")
    lines = text.splitlines()
    data_row = next(
        int(ln.split(",")[1]) for ln in lines[:80] if ln.lower().startswith("data starts in row")
    )
    preamble, header = lines[: data_row - 1], lines[data_row - 1]

    # strip identifiers from the preamble, keep every line and its order
    clean = []
    for ln in preamble:
        ln = re.sub(r"(Export from Study:).*", r"\1 synthetic", ln)
        ln = re.sub(r"(Export files Stored in Dir:).*", r"\1 /synthetic/", ln)
        ln = re.sub(r"(Map name:,).*", r"\1synthetic map", ln)
        clean.append(ln)

    cols = [c.strip() for c in header.split(",")]
    idx = {c: i for i, c in enumerate(cols)}
    rng = np.random.default_rng(20260906)
    take = rng.choice(len(verts), size=min(64, len(verts)), replace=False)

    rows = []
    for k, vi in enumerate(take):
        f = [""] * len(cols)
        for name, val in (
            ("surface x", verts[vi][0]),
            ("surface y", verts[vi][1]),
            ("surface z", verts[vi][2]),
            ("roving x", verts[vi][0]),
            ("roving y", verts[vi][1]),
            ("roving z", verts[vi][2]),
            ("P-P", volts[vi]),
            ("adjTime (ms)", 43.5),
            ("force (g)", 8.0),
        ):
            if name in idx:
                f[idx[name]] = f"{val:.4f}"
        for name, val in (("(Point #)", str(k + 1)), ("P-P valid", "1"), ("Electrodes", "A1 A2")):
            if name in idx:
                f[idx[name]] = val
        rows.append(",".join(f))

    (out / "Contact_Mapping").mkdir(exist_ok=True)
    (out / "Contact_Mapping" / "Map_PP_bi.csv").write_text(
        "\n".join(clean + [header] + rows) + "\n"
    )


def build_carto(real_dir: str, out_dir: Path) -> None:
    """A CARTO export whose section headers are copied from the real file.

    The section preambles are taken verbatim — they are format documentation,
    not study data — because guessing them gets the layout subtly wrong: the
    colours section carries *two* comment lines and thirteen columns in a fixed
    order, and a hand-written approximation shifted the reader by one row.
    """
    real = Path(real_dir)
    # Real CARTO map names carry spaces and dash-separated indices
    # ("1-1-1-ReLA PaceMap anterior"). A fixture named "1-Synthetic" would
    # never exercise a path with a space in it, which is every real export.
    MAP = "1-1-1-Synthetic Left Atrium"  # noqa: N806
    real_lines = next(real.glob("*.mesh")).read_text(errors="ignore").splitlines()
    verts, tris, volts, lat = synthetic_mesh()
    normals = verts / np.linalg.norm(verts, axis=1, keepdims=True)

    def section(name):
        """The real file's header line plus its comment lines, verbatim."""
        i = next(k for k, ln in enumerate(real_lines) if ln.startswith(name))
        out = [real_lines[i]]
        j = i + 1
        while j < len(real_lines) and (real_lines[j].startswith(";") or not real_lines[j].strip()):
            out.append(real_lines[j])
            j += 1
        return out

    head = []
    for ln in real_lines:
        if ln.startswith("[VerticesSection]"):
            break
        ln = re.sub(r"(MeshID\s*=).*", r"\1 1", ln)
        ln = re.sub(r"(MeshName\s*=).*", r"\1 ", ln)
        ln = re.sub(r"(NumVertex\s*=).*", rf"\1 {len(verts)}", ln)
        ln = re.sub(r"(NumTriangle\s*=).*", rf"\1 {len(tris)}", ln)
        head.append(ln)

    # how many colour columns the real file declares, and in which order
    names_line = next((ln for ln in head if ln.startswith("ColorsNames")), "")
    colour_names = names_line.split("=", 1)[1].split() if "=" in names_line else []
    n_colours = len(colour_names) or 3
    by_name = {"LAT": lat, "Bipolar": volts, "Unipolar": volts * 2.0}

    body = section("[VerticesSection]")
    for i, (v, n) in enumerate(zip(verts, normals)):  # noqa: B905
        body.append(
            f"{i:8d} = {v[0]:13.3f} {v[1]:13.3f} {v[2]:13.3f} "
            f"{n[0]:10.5f} {n[1]:10.5f} {n[2]:10.5f} {0:8d}"
        )
    body += [""] + section("[TrianglesSection]")
    for i, t in enumerate(tris):
        body.append(
            f"{i:8d} = {t[0]:9d} {t[1]:9d} {t[2]:9d} {0.0:10.5f} {0.0:10.5f} {1.0:10.5f} {0:8d}"
        )
    body += [""] + section("[VerticesColorsSection]")
    for i in range(len(verts)):
        # -10000 is the export's own "no value here" marker for the columns
        # this synthetic study does not carry.
        cols = [by_name.get(nm, None) for nm in colour_names] or [lat, volts, volts * 2]
        vals = [(-10000.0 if c is None else float(c[i])) for c in cols]
        body.append(f"{i:8d} = " + " ".join(f"{v:13.4f}" for v in vals))

    out = _fresh(out_dir / "carto" / "synthetic_study")
    (out / f"{MAP}.mesh").write_text("\n".join(head + body) + "\n")

    # ── Punkte: Points_Export.xml + je ein Point_Export.xml + Elektrodendatei ──
    # Die erste Zeile der Elektrodendatei ist eine Formatkennung ("…_2.0"),
    # die zweite die Spaltenüberschrift; beide werden aus der echten Datei
    # übernommen, damit der Zeilen-Offset im Parser stimmt.
    elec_real = next(real.glob("*_Eleclectrode_Positions_*.txt"), None)
    elec_head = (
        elec_real.read_text(encoding="latin-1").splitlines()[:2]
        if elec_real
        else ["Eleclectrode_Positions_2.0", "Electrode#\tTime\tX\tY\tZ"]
    )

    pts = etree.Element("Points", Map_Name=MAP, Map_Index="1", Date="01/01/26", Time="00:00:00")
    rng = np.random.default_rng(20260101)
    idx = rng.choice(len(verts), size=64, replace=False)
    for k, vi in enumerate(idx):
        pid, start = 1000 + k, 10000000 + k * 1000
        pfile = f"{MAP}_P{pid}_Point_Export.xml"
        etree.SubElement(pts, "Point", ID=str(pid), File_Name=pfile)

        pt = etree.Element("Point", ID=str(pid), Date="01/01/26", Time="00:00:00")
        etree.SubElement(
            pt,
            "Annotations",
            StartTime=str(start),
            Reference_Annotation="2000",
            Map_Annotation=f"{2000 + lat[vi]:.0f}",
        )
        etree.SubElement(pt, "WOI", From="-170", To="146")
        etree.SubElement(
            pt,
            "Voltages",
            Unipolar=f"{abs(volts[vi]) * 2:.3f}",
            Bipolar=f"{abs(volts[vi]):.3f}",
        )
        pos = etree.SubElement(pt, "Positions")
        elec = f"{MAP}_MEC_CONNECTOR_Eleclectrode_Positions_OnAnnotation_{start}.txt"
        etree.SubElement(pos, "Connector", MEC_CONNECTOR=elec)
        (out / pfile).write_bytes(
            etree.tostring(pt, xml_declaration=True, encoding="UTF-8", pretty_print=True)
        )

        # vier Elektroden entlang der Oberflächennormale am Vertex
        rows = [
            f"{e + 1}\t{e * 16}\t"
            + "\t".join(f"{c:.5f}" for c in verts[vi] + normals[vi] * e * 0.4)
            for e in range(4)
        ]
        (out / elec).write_text("\n".join(elec_head + rows) + "\n", encoding="latin-1")

    (out / f"{MAP}_Points_Export.xml").write_bytes(
        etree.tostring(pts, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    )

    study = etree.Element("Study", name="synthetic-study")
    maps = etree.SubElement(study, "Maps")
    m = etree.SubElement(maps, "Map", Name=MAP, FileNames=f"{MAP}.mesh")
    # The catalogue is where a point's coordinates live; the per-point export
    # carries only its measurements. Same order as Points_Export.xml.
    cp = etree.SubElement(m, "CartoPoints", Count=str(len(idx)))
    for k, vi in enumerate(idx):
        etree.SubElement(
            cp,
            "Point",
            Id=str(1000 + k),
            Position3D=" ".join(f"{c:.5f}" for c in verts[vi]),
        )
    (out / "Study.xml").write_bytes(
        etree.tostring(study, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    )
    print(
        f"  CARTO:   {len(verts)} Vertices, {len(tris)} Dreiecke, {n_colours} Farbspalten -> {out}"
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ensite", required=True, help="A real EnSiteX export (folder or archive).")
    p.add_argument("--carto", required=True, help="An unpacked real CARTO export.")
    p.add_argument("--out", type=Path, default=Path("tests/fixtures/synthetic"))
    args = p.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    build_ensite(args.ensite, args.out)
    build_carto(args.carto, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
