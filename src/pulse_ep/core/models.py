from typing import Optional

import numpy as np
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, FLOAT, JSONB
from sqlalchemy.orm import Session, declarative_base, relationship
from sqlalchemy.orm.attributes import flag_modified

from pulse_ep.core.epmap import EPMap
from pulse_ep.core.measurement import Measurement, MeasurementPoint
from pulse_ep.core.placed_point import PlacedPoint
from pulse_ep.core.scalar_field import ScalarField
from pulse_ep.core.study import Study

Base = declarative_base()

# Portable JSON: JSONB on PostgreSQL (indexable), plain JSON elsewhere
# (e.g. SQLite in tests) so the same models create on both backends.
PortableJSON = JSON().with_variant(JSONB, "postgresql")


class StudyModel(Base):
    __tablename__ = "studies"

    id: int = Column(Integer, primary_key=True, index=True)
    name: str = Column(String, nullable=False)
    # ── Vendor & provenance (vendor-neutral platform) ──
    vendor: str | None = Column(String, index=True)
    provenance: dict | None = Column(PortableJSON)

    def __init__(self, name: str, vendor: str | None = None, provenance: dict | None = None):
        self.name = name
        self.vendor = vendor
        self.provenance = provenance

    def create(self, session):
        session.add(self)
        session.commit()

    @classmethod
    def retrieve(cls, session, id):
        return session.query(cls).filter_by(id=id).first()

    def update(self, session):
        session.commit()

    def delete(self, session):
        session.delete(self)
        session.commit()

    @classmethod
    def find_by_name(cls, name: str, session: Session) -> Optional["StudyModel"]:
        return session.query(cls).filter_by(name=name).first()

    @classmethod
    def find_by_id(cls, id: int, session: Session) -> Optional["StudyModel"]:
        return session.query(cls).filter_by(id=id).first()

    @classmethod
    def get_study_list(cls, session: Session) -> list[tuple[int, str]]:
        studies = session.query(cls).with_entities(cls.id, cls.name).all()
        return [(study.id, study.name) for study in studies]

    @classmethod
    def get_epmap_list_by_id(cls, session: Session, study_id: int):
        study = cls.retrieve(session, study_id)
        if study is None:
            return None
        epmaps = (
            session.query(EPMapModel.id, EPMapModel.map_name, EPMapModel.number_of_points)
            .filter(EPMapModel.study_id == study_id)
            .all()
        )
        return epmaps

    def get_epmap_list(self, session: Session):
        session.refresh(self)
        return [(epmap.id, epmap.map_name) for epmap in self.epmaps]

    @classmethod
    def from_study(cls, study: Study) -> "StudyModel":
        return cls(
            name=study.name,
            vendor=getattr(study, "vendor", None),
            provenance=getattr(study, "provenance", None),
        )

    @classmethod
    def get_all_studies_and_epmaps(cls, session: Session) -> list[tuple[int, str, int, str, int]]:
        query = (
            session.query(
                cls.id.label("study_id"),
                cls.name.label("study_name"),
                EPMapModel.id.label("epmap_id"),
                EPMapModel.map_name.label("epmap_map_name"),
                EPMapModel.number_of_points.label("number_of_points"),
            )
            .join(EPMapModel, EPMapModel.study_id == cls.id)
            .join(EPMapAttributes, EPMapAttributes.map_id == EPMapModel.id)
            .group_by(cls.id, cls.name, EPMapModel.id, EPMapModel.map_name)
            .order_by(cls.name, EPMapModel.map_name)
        )
        return query.all()


# ═══════════════════════════════════════════════════════════════════════════
#  EPMapModel — per-map mesh & scalar data
# ═══════════════════════════════════════════════════════════════════════════


class EPMapModel(Base):
    __tablename__ = "epmaps"

    id: int = Column(Integer, primary_key=True, index=True)
    study_id: int = Column(Integer, ForeignKey("studies.id"), nullable=False, index=True)

    map_name: str = Column(String, nullable=False)
    study_name: str = Column(String, nullable=False)
    number_of_points: int | None = Column(Integer)
    mesh_file: str | None = Column(String)

    # ── Per-vertex mesh data (stays here — these are interpolated onto mesh) ──
    triangles: list[int] = Column(ARRAY(Integer))
    vertices: list[float] = Column(ARRAY(FLOAT))
    triangle_areas: list[float] = Column(ARRAY(FLOAT))
    is_vertex_at_edge: list[bool] = Column(ARRAY(Boolean))
    act_bip: list[float] = Column(ARRAY(FLOAT))  # legacy CARTO (activation+bipolar)
    normals: list[float] = Column(ARRAY(FLOAT))
    uni_imp_frc: list[float] = Column(ARRAY(FLOAT))

    # ── Vendor-neutral scalar fields: {name: {values, kind, unit, status_mask, source}} ──
    # Open map (any number of kinds per map); the successor to fixed act_bip.
    scalar_fields: dict | None = Column(PortableJSON)

    # ── Relationships ──
    study = relationship("StudyModel", backref="epmaps")
    points = relationship(
        "EPMapPoint",
        back_populates="map",
        order_by="EPMapPoint.point_index",
        cascade="all, delete-orphan",
    )

    def __init__(self, map_name: str, study_id: int, **kwargs) -> None:
        self.map_name = map_name
        self.study_id = study_id
        for k, v in kwargs.items():
            setattr(self, k, v)

    def create(self, session):
        session.add(self)
        session.commit()

    @classmethod
    def retrieve(cls, session, id):
        return session.query(cls).filter_by(id=id).first()

    def update(self, session):
        session.commit()

    def delete(self, session):
        session.delete(self)
        session.commit()

    @classmethod
    def find_by_name(cls, map_name: str, session: Session) -> Optional["EPMapModel"]:
        return session.query(cls).filter_by(map_name=map_name).first()

    @classmethod
    def find_by_id(cls, id: int, session: Session) -> Optional["EPMapModel"]:
        return session.query(cls).filter_by(id=id).first()

    @classmethod
    def get_number_of_points_by_id(cls, session: Session, id: int) -> int | None:
        epmap_model = session.query(cls).filter_by(id=id).first()
        return epmap_model.number_of_points if epmap_model else None

    @classmethod
    def from_epmap(cls, epmap, study_id: int) -> "EPMapModel":
        def _list(a):
            return a.tolist() if a is not None else None

        scalar_fields = (
            {name: field.to_dict() for name, field in epmap.scalar_fields.items()}
            if getattr(epmap, "scalar_fields", None)
            else None
        )
        return cls(
            map_name=epmap.map_name,
            study_id=study_id,
            study_name=epmap.study_name,
            number_of_points=epmap.number_of_points,
            mesh_file=epmap.mesh_file,
            triangles=_list(epmap.triangles),
            vertices=_list(epmap.vertices),
            triangle_areas=_list(epmap.triangle_areas),
            is_vertex_at_edge=_list(epmap.is_vertex_at_edge),
            act_bip=_list(epmap.act_bip),
            normals=_list(epmap.normals),
            uni_imp_frc=_list(epmap.uni_imp_frc),
            scalar_fields=scalar_fields,
        )

    def to_epmap(self, include_points: bool = False) -> EPMap:
        """Convert DB model to EPMap domain object.

        Args:
            include_points: If True, build xyz array from related EPMapPoints.
                            Requires that self.points is loaded.
        """
        xyz = None
        if include_points and self.points:
            xyz = np.array(
                [
                    [p.position_x or np.nan, p.position_y or np.nan, p.position_z or np.nan]
                    for p in sorted(self.points, key=lambda p: p.point_index)
                ]
            )

        def _arr(v):
            return np.array(v) if v is not None else None

        scalar_fields = (
            {name: ScalarField.from_dict(d) for name, d in self.scalar_fields.items()}
            if self.scalar_fields
            else None
        )
        return EPMap(
            map_name=self.map_name,
            study_name=self.study_name,
            map_number_of_points=self.number_of_points,
            mesh_file=self.mesh_file,
            triangles=_arr(self.triangles),
            vertices=_arr(self.vertices),
            triangle_areas=_arr(self.triangle_areas),
            is_vertex_at_edge=_arr(self.is_vertex_at_edge),
            act_bip=_arr(self.act_bip),
            normals=_arr(self.normals),
            uni_imp_frc=_arr(self.uni_imp_frc) if self.uni_imp_frc else None,
            xyz=xyz,
            scalar_fields=scalar_fields,
        )


# ═══════════════════════════════════════════════════════════════════════════
#  EPMapPoint — per-measurement-point raw data (NEW)
# ═══════════════════════════════════════════════════════════════════════════


class EPMapPoint(Base):
    """
    One measurement point within an EP map.
    Stores raw CARTO data: positions, annotations, catheter positions, ECG.
    """

    __tablename__ = "ep_map_points"

    id = Column(Integer, primary_key=True, index=True)
    map_id = Column(
        Integer, ForeignKey("epmaps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    point_index = Column(Integer, nullable=False)  # 0-based order within map

    carto_point_id = Column(Integer)  # CARTO Point ID
    start_time = Column(BigInteger)  # CARTO ms timestamp

    # ── Position (from study XML Position3D) ──
    position_x = Column(Float)
    position_y = Column(Float)
    position_z = Column(Float)

    # ── Annotations ──
    woi_from = Column(Float)
    woi_to = Column(Float)
    reference_annotation = Column(Float)
    map_annotation = Column(Float)

    # ── Voltages ──
    unipolar_voltage = Column(Float)
    bipolar_voltage = Column(Float)

    # ── Catheter positions at annotation time (OnAnnotation) ──
    # Each stores a flat list [x1,y1,z1, x2,y2,z2, ...] of electrode coords
    cs_positions = Column(ARRAY(FLOAT))  # CS: typically 10 electrodes × 3
    magnetic20_positions = Column(ARRAY(FLOAT))  # 20A: 20 electrodes × 3
    roving_positions = Column(ARRAY(FLOAT))  # MEC/NAVISTAR: variable × 3

    # ── Connector types present for this point ──
    connector_types = Column(ARRAY(String))  # e.g. ['CS_CONNECTOR', 'MAGNETIC_20_POLE_A_CONNECTOR']

    # ── Relationships ──
    map = relationship("EPMapModel", back_populates="points")

    __table_args__ = (Index("ix_ep_map_points_map_point", "map_id", "point_index"),)

    def __repr__(self):
        return f"<EPMapPoint map_id={self.map_id} idx={self.point_index} carto_id={self.carto_point_id}>"


# ═══════════════════════════════════════════════════════════════════════════
#  AttributeMetadata + EPMapAttributes (unchanged)
# ═══════════════════════════════════════════════════════════════════════════


class AttributeMetadata(Base):
    __tablename__ = "attribute_metadata"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    data_type = Column(String, nullable=False)
    default_value = Column(JSONB, nullable=True)


class EPMapAttributes(Base):
    __tablename__ = "epmap_attributes"
    map_id = Column(Integer, ForeignKey("epmaps.id"), primary_key=True, index=True)
    attributes = Column(JSONB, default={})

    __table_args__ = (
        Index("ix_epmap_attributes_attributes", "attributes", postgresql_using="gin"),
    )

    def get_all_attributes(self) -> dict[str, any]:
        return self.attributes or {}

    def set_attributes(self, attribute_values: dict[str, any]):
        if self.attributes is None:
            self.attributes = {}
        self.attributes.update(attribute_values)
        flag_modified(self, "attributes")

    def initialize_attributes_with_metadata(self, session: Session):
        metadata = session.query(AttributeMetadata).all()
        if self.attributes is None:
            self.attributes = {}
        for meta in metadata:
            if meta.name not in self.attributes:
                self.attributes[meta.name] = meta.default_value
        flag_modified(self, "attributes")


# ═══════════════════════════════════════════════════════════════════════════
#  UserModel, ColormapModel, ReportModel (unchanged)
# ═══════════════════════════════════════════════════════════════════════════


class UserModel(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, nullable=False)

    def __init__(self, username, password, role):
        self.username = username
        self.password = password
        self.role = role


class ColormapModel(Base):
    __tablename__ = "colormaps"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    colors = Column(ARRAY(String), nullable=False)
    intervals = Column(ARRAY(Float), nullable=True)
    use_gradient = Column(Boolean, default=True)
    annotations = Column(ARRAY(String), nullable=True)
    is_relative = Column(Boolean, default=False)
    clipping = Column(Boolean, default=True)

    def __init__(
        self,
        name,
        colors,
        intervals=None,
        use_gradient=True,
        annotations=None,
        is_relative=False,
        clipping=True,
    ):
        self.name = name
        self.colors = colors
        self.intervals = intervals
        self.use_gradient = use_gradient
        self.annotations = annotations
        self.is_relative = is_relative
        self.clipping = clipping

    def create(self, session):
        session.add(self)
        session.commit()

    def update(self, session, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        session.commit()

    def delete(self, session):
        session.delete(self)
        session.commit()

    @classmethod
    def find_by_name(cls, name, session):
        return session.query(cls).filter_by(name=name).first()

    @classmethod
    def find_by_id(cls, id, session):
        return session.query(cls).filter_by(id=id).first()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "colors": self.colors,
            "intervals": self.intervals,
            "use_gradient": self.use_gradient,
            "annotations": self.annotations,
            "is_relative": self.is_relative,
            "clipping": self.clipping,
        }


class ReportModel(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    map_ids = Column(ARRAY(Integer), nullable=False)
    additional_data = Column(JSON, nullable=True)

    def __init__(self, map_ids, additional_data=None):
        self.map_ids = map_ids
        self.additional_data = additional_data or {}

    def create(self, session):
        session.add(self)
        session.commit()

    def update(self, session, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        session.commit()

    def delete(self, session):
        session.delete(self)
        session.commit()

    @classmethod
    def find_by_id(cls, id, session):
        return session.query(cls).filter_by(id=id).first()

    @classmethod
    def find_all(cls, session):
        return session.query(cls).all()

    def to_dict(self):
        ad = dict(self.additional_data or {})
        return {
            "id": self.id,
            "map_ids": self.map_ids,
            "report_name": ad.pop("report_name", "Unnamed Report"),
            "colormap_id": ad.pop("colormap_id", None),
            "colormap_name": ad.pop("colormap_name", "Unnamed Colormap"),
            "additional_data": ad,
        }

    def add_map_id(self, session, map_id):
        if self.map_ids is None:
            self.map_ids = []
        if map_id not in self.map_ids:
            self.map_ids.append(map_id)
            flag_modified(self, "map_ids")
            session.commit()

    def update_additional_data(self, session, key, value):
        if self.additional_data is None:
            self.additional_data = {}
        self.additional_data[key] = value
        flag_modified(self, "additional_data")
        session.commit()


# ═══════════════════════════════════════════════════════════════════════════
#  WaveformModel — signal metadata; the samples live in a WaveformStore
# ═══════════════════════════════════════════════════════════════════════════


class WaveformModel(Base):
    """Metadata for one waveform. The numeric samples are NOT stored here —
    they live in a :class:`~pulse_ep.core.waveform.WaveformStore` (Parquet);
    ``data_uri`` points at them."""

    __tablename__ = "waveforms"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(
        Integer, ForeignKey("studies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    map_id = Column(
        Integer, ForeignKey("epmaps.id", ondelete="CASCADE"), nullable=True, index=True
    )

    signal_type = Column(String)  # egm_bipolar | egm_unipolar | ecg
    channels = Column(PortableJSON)  # list[str]
    sample_rate = Column(Float)
    n_samples = Column(Integer)
    n_channels = Column(Integer)
    segment = Column(String, nullable=True)
    filters = Column(PortableJSON, nullable=True)

    # ── Out-of-DB signal storage ──
    data_uri = Column(String, nullable=False)  # store-relative path
    data_format = Column(String, default="parquet")
    size_bytes = Column(Integer, nullable=True)
    checksum = Column(String, nullable=True)
    source = Column(String, nullable=True)


def store_waveform(waveform, store, key, study_id=None, map_id=None) -> WaveformModel:
    """Write a :class:`Waveform` to ``store`` and build its DB metadata row."""
    uri = store.write(waveform, key)
    meta = waveform.meta or {}
    return WaveformModel(
        study_id=study_id,
        map_id=map_id,
        signal_type=waveform.signal_type,
        channels=[str(c) for c in waveform.channels],
        sample_rate=waveform.sample_rate,
        n_samples=int(waveform.data.shape[0]),
        n_channels=int(waveform.data.shape[1]),
        segment=meta.get("segment"),
        filters=meta.get("filters"),
        data_uri=uri,
        data_format="parquet",
        source=meta.get("software_version"),
    )


def ingest_waveforms(plan, source, store, study_id=None) -> list[WaveformModel]:
    """Parse + store the opt-in waveforms of a prepared EnSite plan.

    Only runs for studies whose ``waveforms.include`` is True (default off).
    """
    from pathlib import Path

    from pulse_ep.core.importers.ensite import parse_ensite_waveforms

    rows: list[WaveformModel] = []
    for sp in plan.studies:
        if not sp.waveforms.include:
            continue
        for name in sp.waveforms.files:
            wave = parse_ensite_waveforms(source.open(name).read(), name=name)
            key = f"{sp.study_name}/{Path(name).stem}"
            rows.append(store_waveform(wave, store, key, study_id=study_id))
    return rows


# ═══════════════════════════════════════════════════════════════════════════
#  MeasurementPointModel — open per-point measurements (vendor-neutral)
# ═══════════════════════════════════════════════════════════════════════════


class MeasurementPointModel(Base):
    """A per-point acquisition sample with an OPEN set of measurements.

    Successor to the fixed-column CARTO ``ep_map_points`` — measured
    quantities live in a JSONB ``measurements`` map keyed by ``kind`` name,
    and electrode geometry in a JSONB ``electrodes`` map keyed by label."""

    __tablename__ = "measurement_points"

    id = Column(Integer, primary_key=True, index=True)
    map_id = Column(
        Integer, ForeignKey("epmaps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    point_index = Column(Integer)
    source_id = Column(String, nullable=True)
    position = Column(ARRAY(FLOAT))  # [x, y, z]
    measurements = Column(PortableJSON)  # {name: {value, kind, unit}}
    electrodes = Column(PortableJSON)  # {label: [x, y, z]}

    __table_args__ = (
        Index("ix_measurement_points_map_point", "map_id", "point_index"),
    )

    def to_measurement_point(self) -> MeasurementPoint:
        measurements = {
            name: Measurement(d["value"], d["kind"], d.get("unit", ""))
            for name, d in (self.measurements or {}).items()
        }
        electrodes = {
            label: np.array(pos, dtype=float) for label, pos in (self.electrodes or {}).items()
        }
        return MeasurementPoint(
            position=np.array(self.position, dtype=float),
            measurements=measurements,
            electrodes=electrodes,
            source_id=self.source_id,
            index=self.point_index,
        )


def measurement_points_to_models(
    points: list[MeasurementPoint], map_id: int
) -> list[MeasurementPointModel]:
    """Serialise domain :class:`MeasurementPoint`s to ORM rows."""
    rows: list[MeasurementPointModel] = []
    for p in points:
        rows.append(
            MeasurementPointModel(
                map_id=map_id,
                point_index=p.index,
                source_id=p.source_id,
                position=[float(x) for x in p.position],
                measurements={
                    name: {"value": m.value, "kind": m.kind, "unit": m.unit}
                    for name, m in p.measurements.items()
                },
                electrodes={
                    label: [float(x) for x in pos] for label, pos in p.electrodes.items()
                },
            )
        )
    return rows


def persist_study(session, study) -> StudyModel:
    """Persist a domain Study (+ its maps and measurement points) to the DB.

    Writes the vendor-neutral study, one EPMapModel per map (with scalar_fields),
    an empty EPMapAttributes tag bag per map, and any attached measurement
    points. Commits and returns the StudyModel (with its assigned id).
    """
    study_model = StudyModel.from_study(study)
    session.add(study_model)
    session.flush()  # assign study_model.id

    for row in placed_points_to_models(getattr(study, "placed_points", None) or [], study_model.id):
        session.add(row)

    for epmap in study.epmaps:
        map_model = EPMapModel.from_epmap(epmap, study_model.id)
        session.add(map_model)
        session.flush()  # assign map_model.id
        session.add(EPMapAttributes(map_id=map_model.id, attributes=getattr(epmap, "attributes", None) or {}))
        for row in measurement_points_to_models(
            getattr(epmap, "measurement_points", None) or [], map_model.id
        ):
            session.add(row)

    session.commit()
    return study_model


# ═══════════════════════════════════════════════════════════════════════════
#  PlacedPointModel — study-level operator/system markers (open attributes)
# ═══════════════════════════════════════════════════════════════════════════


class PlacedPointModel(Base):
    """A study-level placed marker (ablation site, landmark, tag, …).

    ``type`` comes from a controlled vocabulary; type-specific data lives in
    the open JSONB ``attributes`` map. Study-level (a physical location in the
    shared study frame), not tied to one map's mesh."""

    __tablename__ = "placed_points"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(
        Integer, ForeignKey("studies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type = Column(String, index=True)
    position = Column(ARRAY(FLOAT))  # [x, y, z]
    label = Column(String, nullable=True)
    attributes = Column(PortableJSON)  # open, type-specific
    source_id = Column(String, nullable=True)

    def to_placed_point(self) -> PlacedPoint:
        return PlacedPoint(
            type=self.type,
            position=np.array(self.position, dtype=float),
            label=self.label,
            attributes=self.attributes or {},
            source_id=self.source_id,
        )


def placed_points_to_models(points: list[PlacedPoint], study_id: int) -> list[PlacedPointModel]:
    """Serialise domain :class:`PlacedPoint`s to ORM rows."""
    return [
        PlacedPointModel(
            study_id=study_id,
            type=p.type,
            position=[float(x) for x in p.position],
            label=p.label,
            attributes=p.attributes,
            source_id=p.source_id,
        )
        for p in points
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  ImportJobModel — the import queue state machine
# ═══════════════════════════════════════════════════════════════════════════

# job statuses
JOB_DETECTED = "detected"
JOB_NEEDS_REVIEW = "needs_review"
JOB_IMPORTING = "importing"
JOB_DONE = "done"
JOB_ERROR = "error"


class ImportJobModel(Base):
    """One queued import: a detected export bundle moving through
    detected -> needs_review -> importing -> done / error. ``plan`` holds the
    prepared (and reviewer-edited) ImportPlan as JSON."""

    __tablename__ = "import_jobs"

    id = Column(Integer, primary_key=True, index=True)
    source_path = Column(String, nullable=False)  # folder or zip
    vendor = Column(String, nullable=True)
    status = Column(String, nullable=False, index=True, default=JOB_DETECTED)
    plan = Column(PortableJSON)  # ImportPlan as dict (with reviewer edits)
    study_id = Column(Integer, nullable=True)
    error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
