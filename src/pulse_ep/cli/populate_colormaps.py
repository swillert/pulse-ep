from pulse_ep.core.database import get_db_session
from pulse_ep.core.models import ColormapModel

# Predefined colormaps with annotations and intervals
predefined_colormaps = [
    {
        "name": "jet",
        "colors": [
            "#00007F",
            "#0000FF",
            "#007FFF",
            "#00FFFF",
            "#7FFF7F",
            "#FFFF00",
            "#FF7F00",
            "#FF0000",
            "#7F0000",
        ],
        "intervals": [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0],
        "use_gradient": True,
        "annotations": [
            "Start",
            "Low",
            "Lower Mid",
            "Mid Low",
            "Middle",
            "Mid High",
            "Higher Mid",
            "High",
            "End",
        ],
        # Intervals run 0..1 — a normalised scale, meaningless against raw
        # millivolts or milliseconds unless the data is mapped onto it.
        "is_relative": True,
        "clipping": False,  # Ensure clipping is False
    },
    {
        "name": "viridis",
        "colors": [
            "#440154",
            "#482878",
            "#3E4A89",
            "#31688E",
            "#26838F",
            "#1F9D8A",
            "#6CCE59",
            "#B6DE2B",
            "#FDE724",
        ],
        "intervals": [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0],
        "use_gradient": True,
        "annotations": None,  # No annotations
        # Intervals run 0..1 — a normalised scale, meaningless against raw
        # millivolts or milliseconds unless the data is mapped onto it.
        "is_relative": True,
        "clipping": False,  # Ensure clipping is False
    },
    {
        "name": "plasma",
        "colors": [
            "#0D0887",
            "#41049D",
            "#6A00A8",
            "#900DA4",
            "#B12A90",
            "#CB4678",
            "#E16462",
            "#F1844B",
            "#FCA636",
        ],
        "intervals": [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0],
        "use_gradient": True,
        "annotations": None,  # No annotations
        # Intervals run 0..1 — a normalised scale, meaningless against raw
        # millivolts or milliseconds unless the data is mapped onto it.
        "is_relative": True,
        "clipping": False,  # Ensure clipping is False
    },
    {
        "name": "magma",
        "colors": [
            "#000004",
            "#1B0C41",
            "#4A0C6B",
            "#781C6D",
            "#A52C60",
            "#CF4446",
            "#ED6925",
            "#FB9906",
            "#FCFFA4",
        ],
        "intervals": [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0],
        "use_gradient": True,
        "annotations": None,  # No annotations
        # Intervals run 0..1 — a normalised scale, meaningless against raw
        # millivolts or milliseconds unless the data is mapped onto it.
        "is_relative": True,
        "clipping": False,  # Ensure clipping is False
    },
    {
        "name": "inferno",
        "colors": [
            "#000004",
            "#1F0C48",
            "#550F6D",
            "#88226A",
            "#AC4453",
            "#BD6C38",
            "#CA9626",
            "#E2D417",
            "#FCFFA4",
        ],
        "intervals": [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0],
        "use_gradient": True,
        "annotations": None,
        # Intervals run 0..1 — a normalised scale, meaningless against raw
        # millivolts or milliseconds unless the data is mapped onto it.
        "is_relative": True,
        "clipping": False,
    },
    {
        # Gray below 70 (no match), then blue→cyan→green→yellow→orange→red for 70–100, steps of 5
        "name": "pacemapping_5",
        "colors": [
            "#808080",  # 0   – below threshold (gray)
            "#000099",  # 70
            "#0033FF",  # 75
            "#00CCFF",  # 80
            "#00FF66",  # 85
            "#FFFF00",  # 90
            "#FF6600",  # 95
            "#990000",  # 100
        ],
        "intervals": [0, 70, 75, 80, 85, 90, 95, 100],
        "use_gradient": True,
        "annotations": ["<70", "70", "75", "80", "85", "90", "95", "100"],
        "is_relative": False,
        "clipping": False,
    },
    {
        # Gray below 70 (no match), then blue→cyan→green→yellow→orange→red for 70–100
        "name": "pacemapping",
        "colors": [
            "#808080",  # 0   – below threshold (gray)
            "#000099",  # 70
            "#0000FF",  # 72
            "#0066FF",  # 74
            "#00CCFF",  # 76
            "#00FFCC",  # 78
            "#00FF00",  # 80
            "#66FF00",  # 82
            "#CCFF00",  # 84
            "#FFFF00",  # 86
            "#FFCC00",  # 88
            "#FF9900",  # 90
            "#FF6600",  # 92
            "#FF3300",  # 94
            "#FF0000",  # 96
            "#CC0000",  # 98
            "#990000",  # 100
        ],
        "intervals": [0, 70, 72, 74, 76, 78, 80, 82, 84, 86, 88, 90, 92, 94, 96, 98, 100],
        "use_gradient": True,
        "annotations": [
            "<70",
            "70",
            "72",
            "74",
            "76",
            "78",
            "80",
            "82",
            "84",
            "86",
            "88",
            "90",
            "92",
            "94",
            "96",
            "98",
            "100",
        ],
        "is_relative": False,
        "clipping": False,
    },
]


def populate_colormaps():
    with get_db_session() as session:
        for colormap in predefined_colormaps:
            name = colormap["name"]
            colors = colormap["colors"]
            intervals = colormap.get("intervals")
            use_gradient = colormap.get("use_gradient", True)
            annotations = colormap.get("annotations")
            is_relative = colormap.get("is_relative", False)
            clipping = colormap.get("clipping", False)  # Ensure clipping is False

            # Ensure annotations match intervals or are None
            if annotations and len(annotations) != len(intervals):
                raise ValueError(
                    f"Annotations length {len(annotations)} does not match intervals length {len(intervals)} for colormap {name}"
                )

            # Check if the colormap already exists
            existing_colormap = ColormapModel.find_by_name(name, session)
            if existing_colormap:
                # Skipping wholesale meant a corrected definition never reached
                # a database that had been seeded once. Bring the display flags
                # in step; colours and intervals stay as the operator left them.
                if existing_colormap.is_relative != is_relative:
                    existing_colormap.is_relative = is_relative
                    session.commit()
                    print(f"Colormap '{name}': is_relative -> {is_relative}.")
                else:
                    print(f"Colormap '{name}' already exists. Skipping.")
                continue

            new_colormap = ColormapModel(
                name=name,
                colors=colors,
                intervals=intervals,
                use_gradient=use_gradient,
                annotations=annotations,
                is_relative=is_relative,
                clipping=clipping,  # Ensure clipping is False
            )
            session.add(new_colormap)
            print(f"Added colormap '{name}' to the database.")

        session.commit()
        print("Colormaps have been added to the database.")


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point (``pulse-ep-populate-colormaps``).

    The entry point in ``pyproject.toml`` names ``main``; without it the
    installed script raised ImportError instead of running.
    """
    populate_colormaps()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
