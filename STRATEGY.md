# pulse-ep — Open-Source-Strategie

Stand: 2026-05-17
Autor: Sven Willert
Zweck: Steuerdokument für den Open-Source-Refactor von `pulse-ultimate` in `pulse-ep` + `pulse-ep-decay`. Alle TODOs/Tasks leiten sich aus diesem Dokument ab.

---

## 1 Ziele

1. **Reproduzierbarkeit für die Doktorarbeit**: Der Code zu Method-, Software- und Clinical-Paper muss dauerhaft zitierbar und nachvollziehbar sein.
2. **Open-Source-Qualität**: Andere EP-Forschungsgruppen müssen `pip install pulse-ep` ausführen können, ohne UKSH-internes Wissen.
3. **Saubere wissenschaftliche Trennung**: Plattform (CARTO-Anbindung, DB, Viewer) und wissenschaftliche Methode (Heat-Method-Geodäsik, σ-Decay-Fit) als getrennte Artefakte — getrennt zitierbar.
4. **Zwei Q1-Veröffentlichungen** als Voraussetzung für *summa cum laude* (Prof. Frank, 2026-04-16): Method-Paper (CMPB, unter Review) + Software-Paper (SoftwareX). pulse-ep ist der Code zum Software-Paper, pulse-ep-decay zum Method-Paper.

## 2 Architektur-Entscheidung

### Zwei eigenständige Pakete, zwei Repos

| Aspekt | `pulse-ep` | `pulse-ep-decay` |
|---|---|---|
| Rolle | Platform / CARTO-Toolkit | Wissenschaftliche Methode |
| Paper | Software-Paper (SoftwareX) | Method-Paper (CMPB) |
| Repo (primary) | gitlab.willert.net/sw/pulse-ep | gitlab.willert.net/sw/pulse-ep-decay |
| Mirror (geplant) | github.com/<tbd>/pulse-ep | github.com/<tbd>/pulse-ep-decay |
| Sichtbarkeit | private bis Submission, dann public | private bis Submission, dann public |
| PyPI | `pulse-ep` | `pulse-ep-decay` |
| Lizenz | MIT | MIT |
| Min Python | 3.10 | 3.10 |
| Abhängigkeit | — | `pulse-ep>=0.1` *als Optional-Extra*, nicht als harter Default |
| CI | GitLab CI (`.gitlab-ci.yml`) | GitLab CI |
| Zitierbarkeit | CITATION.cff + Zenodo-DOI via GitHub-Mirror (vor Submission) | dito |

**Rationale**: Klare Zitate (Software-Paper zitiert pulse-ep, Method-Paper zitiert pulse-ep-decay), getrennte Issue-Tracker, eigene Versionierung. Aufwand für CI/Release ist überschaubar, da beide Pakete dasselbe Template benutzen.

### Was bleibt in `pulse-ep`

- `pulse_ep.core` — Domänenmodelle (EPMap, Study), CARTO-XML/Mesh-Parsing, DB-Modelle, Importer
- `pulse_ep.server` — Flask-App, JWT-Auth, REST-API, statisches Frontend (Three.js)
- `pulse_ep.cli` — Datenfluss-Kommandos: `pulse-ep-import-carto`, `pulse-ep-populate-colormaps`, `pulse-ep-tag-maps`, `pulse-ep-server`, `pulse-ep-demo`
- `pulse_ep.figures` — Standard-Heatmap-Generatoren (für klinische Reports)
- `pulse_ep.examples.demo_synthetic` — End-to-End-Walkthrough mit synthetischem Mesh

### Was geht nach `pulse-ep-decay`

**Designprinzip: Array-First, Adapter-Second.** Der wissenschaftliche Kern arbeitet ausschließlich auf Numpy-Arrays (Vertices, Triangles, Per-Vertex-Score-Feld, Origin-Index). Das macht das Method-Paper unabhängig reproduzierbar — andere Forschungsgruppen brauchen keine Postgres-DB und kein CARTO-Wissen, sondern können `pulse-ep-decay` direkt auf ihren eigenen Meshes anwenden.

- `pulse_ep_decay.geodesic` — Mesh-Adjazenzgraph, Dijkstra-Distanzen (Baseline). Signatur: `geodesic_distances(vertices, triangles, origin_idx) -> np.ndarray`
- `pulse_ep_decay.heatmethod` — Wrapper um `potpourri3d`/geometry-central (Crane et al. 2017). Gleiche Signatur wie oben.
- `pulse_ep_decay.decay_fit` — Gauß-Decay-Modell, σ-Schätzung via `scipy.optimize.curve_fit`. Signatur: `fit_gaussian_decay(distances, scores) -> DecayFitResult`
- `pulse_ep_decay.validation` — synthetische Score-Felder, σ-Recovery-Test, Bias-Statistik. Arbeitet komplett ohne externe Daten.
- `pulse_ep_decay.integration.pulse_ep` — **optionaler** Adapter: extrahiert Vertices/Triangles/Scores aus `pulse_ep.core.models.EPMapModel`. Wird nur importiert, wenn das Extra `pulse-ep` installiert ist; saubere `ImportError`-Meldung mit Installationshinweis sonst.
- `pulse_ep_decay.cli` — `pulse-ep-decay-spatial`, `pulse-ep-decay-validate-sigma`, `pulse-ep-decay-compare-geodesic`, `pulse-ep-decay-full-validation`. CLI-Skripte können wahlweise auf NPZ-Dateien (array-basiert) oder auf eine pulse-ep-DB (via Adapter) arbeiten.

### Was bleibt in `pulse-ultimate` (eingefroren)

`pulse-ultimate` bleibt als historisches Archiv online, mit README-Banner „⚠️ moved to pulse-ep + pulse-ep-decay" und einem letzten Release-Tag `paper-frozen-2026` für die Reproduzierbarkeit der eingereichten Paper. Keine neuen Features. Bugfixes nur, wenn ein Reviewer es ausdrücklich verlangt.

## 3 Naming-Konventionen

- Repo: `kebab-case` (`pulse-ep`, `pulse-ep-decay`)
- PyPI-Distribution: dito
- Python-Paket: `snake_case` (`pulse_ep`, `pulse_ep_decay`)
- Konsole-Skripte: Präfix `pulse-ep-` bzw. `pulse-ep-decay-`
- Version: SemVer, Start bei `0.1.0`, `1.0.0` mit erstem akzeptierten Paper

## 4 Open-Source-Standards

| Standard | Tool | Status |
|---|---|---|
| Build | setuptools (modern, declarative) | ✓ pyproject.toml vorhanden |
| Linting | `ruff` (replaces flake8+isort+pyupgrade) | ✓ konfiguriert |
| Typing | `mypy`, anfangs lax | ⏳ in dev-extra |
| Formatting | `ruff format` | ⏳ in pre-commit |
| Tests | `pytest` + `pytest-cov` | ⏳ Suite leer |
| Pre-commit | `pre-commit` | ⏳ |
| CI | GitHub Actions, Matrix 3.10/3.11/3.12 | ⏳ |
| Docs | `mkdocs-material` + `mkdocstrings` | ⏳ |
| Versioning | SemVer, Tag-basierter Release | ⏳ |
| DOI | Zenodo via GitHub-Release | ⏳ |
| Citation | `CITATION.cff` | ✓ vorhanden, Software-Paper-Cite aktualisieren wenn akzeptiert |
| License | MIT, `LICENSE`-Datei | ✓ |
| Code of Conduct | `CODE_OF_CONDUCT.md` (Contributor Covenant) | ⏳ |
| Contributing | `CONTRIBUTING.md` | ⏳ |
| Issue/PR Templates | `.github/ISSUE_TEMPLATE/` | ⏳ |

## 5 Migrationsregeln

1. **Keine Funktionalität verlieren** beim Schritt pulse-ultimate → pulse-ep. Erst portieren + testen, dann im alten Repo deaktivieren.
2. **Keine CARTO-Patientendaten im Open-Source-Repo**. Das aktuelle `study.csv` und die `decay_profiles/`-Verzeichnisse bleiben in pulse-ultimate (privates UKSH-Verzeichnis). Tests/Demos arbeiten ausschließlich mit synthetischen Daten.
3. **Imports nur in eine Richtung, und nur im Adapter**: Der wissenschaftliche Kern von `pulse-ep-decay` importiert *nicht* aus `pulse-ep`. Nur das optionale Submodul `pulse_ep_decay.integration.pulse_ep` darf das. `pulse-ep` selbst importiert niemals aus `pulse-ep-decay`. Damit: kein Zyklus, schlanke Plattform-Installation ohne `potpourri3d`, und der Method-Paper-Kern lebt unabhängig.
4. **Datenbankschema bleibt kompatibel**. Alembic-Migrationen nur additiv. Bestehende UKSH-DBs müssen ohne Datenverlust mit pulse-ep weiterlaufen.

## 6 Reihenfolge der Arbeit

1. **Strategie & Setup (jetzt)** — STRATEGY.md, Git init, README, Tests-Gerüst, CI-Skelett
2. **pulse-ep-decay extrahieren** — Code-Refactor Skript→Library, Tests, eigenes Repo
3. **pulse-ep entkernen** — Decay-Code raus, Demo rein, Doku schreiben
4. **Verifikation** — Frische venv, `pip install pulse-ep + pulse-ep-decay`, alle Demos durchspielen
5. **Software-Paper updaten** — Titel/Inhalt an Split anpassen, einreichen
6. **pulse-ultimate einfrieren** — README-Banner, finaler Release-Tag

## 7 Offene Punkte

- [ ] GitHub-Username bestätigen (CITATION.cff steht auf `swillert`)
- [ ] Affiliation für Software-Paper (aktuell UKSH Kiel, Department Internal Medicine III) — bleibt so?
- [ ] **Autorenliste Software-Paper (Stand 2026-05-17, vorläufig): Willert, Lian, Frank.**
      Bisher im `paper.tex` eingetragen: Willert, Maslova, Zaman, Frank, Lian → muss reduziert/geändert werden,
      ggf. erneut anpassen. Vor Submission Beiträge nach CRediT-Taxonomie dokumentieren.
- [ ] Demo-Datensatz: rein synthetisch, oder zusätzlich ein anonymisiertes Phantom-Beispiel?
- [ ] Disputationstermin → ergibt PyPI-Release-Deadline (Paper-Acceptance muss vor Disputation liegen)

---

*Dieses Dokument wird beim Fortschritt aktualisiert. Jede Änderung am Scope braucht ein Update hier zuerst.*
