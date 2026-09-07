"""Shared database/store selection for REST and command-line OpenEP export."""

from __future__ import annotations


def export_inputs(
    session,
    model,
    *,
    include_points=True,
    include_signals=False,
    ablation_scope="none",
    ablation_ids=None,
):
    from pulse_ep.core.config import get_settings
    from pulse_ep.core.models import PlacedPointModel, StudyModel, WaveformModel
    from pulse_ep.core.waveform import FilesystemStore

    if ablation_scope not in {"none", "study"}:
        raise ValueError("ablation_scope must be none or study")
    if ablation_ids and ablation_scope != "none":
        raise ValueError("choose ablation_ids or ablation_scope=study, not both")
    if include_signals and not include_points:
        raise ValueError("include_signals requires include_points")
    study = session.get(StudyModel, model.study_id) if model.study_id else None
    epmap = model.to_epmap(include_points=include_points)
    root = get_settings().waveform_store_dir
    force, signals, notes = [], [], []
    if include_points and root and model.study_id:
        from sqlalchemy import or_

        rows = session.query(WaveformModel).filter(
            WaveformModel.study_id == model.study_id,
            or_(WaveformModel.map_id == model.id, WaveformModel.map_id.is_(None)),
        )
        if not include_signals:
            rows = rows.filter(WaveformModel.signal_type.like("contact_force%"))
        store = FilesystemStore(root)
        seen = set()
        for row in rows.order_by(WaveformModel.id):
            if row.data_uri in seen:
                continue
            seen.add(row.data_uri)
            if not (
                str(row.signal_type).startswith(("contact_force", "egm"))
                or row.signal_type == "ecg"
            ):
                continue
            try:
                wave = store.read(row.data_uri)
            except (OSError, ValueError):
                notes.append(f"waveform {row.id}: stored file unavailable; omitted")
                continue
            if str(row.signal_type).startswith("contact_force"):
                force.append(wave)
            elif include_signals:
                signals.append(wave)
    elif include_signals:
        notes.append("signals: no waveform store configured")
    placed = None
    ids = []
    if ablation_scope == "study" or ablation_ids:
        rows = session.query(PlacedPointModel).filter(PlacedPointModel.study_id == model.study_id)
        if ablation_ids:
            rows = rows.filter(PlacedPointModel.id.in_(ablation_ids))
        selected = rows.order_by(PlacedPointModel.id).all()
        ids = [r.id for r in selected]
        if ablation_ids and set(ids) != set(ablation_ids):
            raise ValueError("ablation_ids must identify markers from this map's study")
        placed = [r.to_placed_point() for r in selected]
    kwargs = dict(
        study_name=getattr(study, "name", None),
        system_name=getattr(study, "vendor", None),
        force_windows=force,
        signal_windows=signals if include_signals else None,
        ablation_points=placed,
    )
    return (
        epmap,
        kwargs,
        {
            "notes": notes,
            "ablation_ids": ids,
            "ablation_scope": "selected" if ablation_ids else ablation_scope,
        },
    )


def stored_userdata(session, model, *, ecg_channels=None, signal_scale_to_mv=None, **options):
    import math

    from pulse_ep.core.openep import to_userdata

    if signal_scale_to_mv is not None:
        if not math.isfinite(signal_scale_to_mv) or signal_scale_to_mv <= 0:
            raise ValueError("signal_scale_to_mv must be finite and positive")
        if not options.get("include_signals"):
            raise ValueError("signal_scale_to_mv requires include_signals")
    epmap, kwargs, provenance = export_inputs(session, model, **options)
    userdata = to_userdata(
        epmap, **kwargs, ecg_channels=ecg_channels, signal_scale_to_mv=signal_scale_to_mv
    )
    userdata["notes"].extend(provenance.pop("notes"))
    userdata["pulse_ep"].update(provenance)
    return userdata
