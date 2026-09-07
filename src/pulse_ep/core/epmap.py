import matplotlib.pyplot as plt
import numpy as np
import pymeshfix
import pyvista as pv
from scipy.spatial import cKDTree

from pulse_ep.core import interpolation
from pulse_ep.core import plot_proc as plot_proc
from pulse_ep.core.scalar_field import ScalarField


class EPMap:
    def __init__(
        self,
        map_name: str,
        study_name: str,
        map_number_of_points: int | None = None,
        mesh_file: str | None = None,
        triangles: np.ndarray | None = None,
        vertices: np.ndarray | None = None,
        triangle_areas: np.ndarray | None = None,
        is_vertex_at_edge: np.ndarray | None = None,
        act_bip: np.ndarray | None = None,
        normals: np.ndarray | None = None,
        uni_imp_frc: np.ndarray | None = None,
        xyz: np.ndarray | None = None,
        pv_mesh: pv.PolyData | None = None,
        scalar_fields: dict[str, ScalarField] | None = None,
        measurement_points: list | None = None,
        attributes: dict | None = None,
    ):

        if map_name is None:
            raise ValueError("map_name must be provided.")

        self.map_name: str = map_name
        self.study_name: str = study_name
        self.number_of_points: int | None = map_number_of_points
        self.mesh_file: str | None = mesh_file
        self.triangles: np.ndarray | None = triangles
        self.vertices: np.ndarray | None = vertices
        self.triangle_areas: np.ndarray | None = triangle_areas
        self.is_vertex_at_edge: np.ndarray | None = is_vertex_at_edge
        self.act_bip: np.ndarray | None = act_bip
        self.normals: np.ndarray | None = normals
        self.uni_imp_frc: np.ndarray | None = uni_imp_frc
        self.xyz: np.ndarray | None = xyz
        self.pv_mesh: pv.PolyData | None = pv_mesh
        # Vendor-neutral named per-vertex scalar fields, each carrying its
        # declared ``kind`` (see :class:`ScalarField`). Both importers
        # register conditioned fields here, named by the quantity they hold.
        # ``act_bip`` below is the legacy CARTO array, still populated for
        # figure/tag consumers that read it directly.
        self.scalar_fields: dict[str, ScalarField] = scalar_fields or {}
        # Discrete acquisition points behind this map (rich per-point
        # measurements + electrode geometry); see :class:`MeasurementPoint`.
        self.measurement_points: list = measurement_points or []
        # Map-level tags (e.g. {"kind": "anatomy", "chamber": "Left"}),
        # persisted into EPMapAttributes.
        self.attributes: dict = attributes or {}

    def register_scalar(
        self,
        scalar_name: str,
        values: np.ndarray,
        kind: str,
        unit: str = "",
        status_mask: np.ndarray | None = None,
        source: str | None = None,
    ) -> None:
        """Register a per-vertex scalar with its declared ``kind``.

        ``values`` are stored as-is: any vendor decode (sign convention,
        sentinel masking) is the importer's job and must be applied before
        registration, so analysis code stays semantics-agnostic.
        """
        self.scalar_fields[scalar_name] = ScalarField(
            np.asarray(values), kind, unit=unit, status_mask=status_mask, source=source
        )

    def get_field(self, scalar_name: str) -> ScalarField | None:
        """Return the :class:`ScalarField` (values + metadata), or ``None``."""
        return self.scalar_fields.get(scalar_name)

    #: Which quantity a map "is about" when the caller does not say, most
    #: interesting first. Every analysis default resolves through this — a
    #: literal ``"act"`` default (CARTO's old name) made those calls fail on
    #: every EnSiteX map.
    PRIMARY_SCALAR_ORDER = (
        "activation_time",
        "pacemap_score",
        "voltage_bipolar",
        "voltage_unipolar",
    )

    def primary_scalar(self) -> str | None:
        """The name of this map's most representative scalar, or ``None``.

        Prefers a quantity from :data:`PRIMARY_SCALAR_ORDER`; failing that,
        falls back to whatever was registered first, so a map carrying only
        vendor-specific fields still has a sensible default.
        """
        for kind in self.PRIMARY_SCALAR_ORDER:
            if (f := self.field_of_kind(kind)) is not None:
                return next(n for n, v in self.scalar_fields.items() if v is f)
        return next(iter(self.scalar_fields), None)

    def field_of_kind(self, kind: str) -> ScalarField | None:
        """The first field holding this quantity, whatever it is named.

        Fields are normally named by their kind, so this is usually the same
        as a name lookup — it matters for studies imported under the old
        CARTO names, and for a map carrying a second field of one kind.
        """
        if (direct := self.scalar_fields.get(kind)) is not None:
            return direct
        return next((f for f in self.scalar_fields.values() if f.kind == kind), None)

    def get_scalar(self, scalar_name: str) -> np.ndarray:
        """Resolve a named per-vertex scalar as a 1-D array of values.

        Fields are registered under the name of the quantity they hold, so a
        name is a kind and one name spans both vendors. CARTO's historical
        ``act`` / ``vol`` still resolve, via the lexicon, to whichever quantity
        the map actually carries — ``act`` held either an activation time or a
        pace-mapping score.

        :raises ValueError: if the name resolves to no registered scalar.
        """
        field = self.scalar_fields.get(scalar_name)
        if field is not None:
            return field.values

        from pulse_ep.core.importers.lexicon import CARTO_LEGACY_NAMES

        for kind in CARTO_LEGACY_NAMES.get(scalar_name.strip().casefold(), ()):
            legacy = self.field_of_kind(kind)
            if legacy is not None:
                return legacy.values
        raise ValueError(f"Unsupported scalar_name: {scalar_name}")

    def generate_anatomical_pv_mesh(self, simplify: bool = True) -> pv.PolyData:
        faces = np.pad(self.triangles, ((0, 0), (1, 0)), "constant", constant_values=3)
        self.pv_mesh = pv.PolyData(self.vertices, faces)  # Store pv_mesh in the instance variable
        if simplify:
            self.repair_and_simplify_mesh()
        return self.pv_mesh

    def measurement_positions(self) -> np.ndarray | None:
        """Where this map was actually measured, or ``None`` if nowhere.

        Prefers the legacy CARTO ``xyz`` array, then falls back to the
        vendor-neutral :class:`MeasurementPoint` positions. EnSiteX maps only
        ever have the latter, so anything reading ``xyz`` directly rejected
        every one of them.
        """
        if self.xyz is not None and len(self.xyz):
            return np.asarray(self.xyz, dtype=float)
        if self.measurement_points:
            return np.array([p.position for p in self.measurement_points], dtype=float)
        return None

    def measured_field(self, scalar_name: str) -> tuple[np.ndarray, np.ndarray]:
        """``(positions, values)`` of one quantity across this map's points.

        The scattered data behind a map: what was actually measured, where.
        Only the points carrying that quantity are returned, so an unannotated
        point does not enter an interpolation as a zero.

        A name is normally a kind (see :func:`~pulse_ep.core.scalar_field.field_name`),
        but a point may carry the quantity under a vendor token, so the kind is
        the fallback lookup.
        """
        positions, values = [], []
        for point in self.measurement_points:
            value = point.get(scalar_name)
            if value is None:
                value = next(
                    (m.value for m in point.measurements.values() if m.kind == scalar_name), None
                )
            if value is None:
                continue
            positions.append(point.position)
            values.append(value)
        if not positions:
            return np.empty((0, 3)), np.empty(0)
        return np.asarray(positions, dtype=float), np.asarray(values, dtype=float)

    def project_measurements_to_mesh(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Project this map's measurement positions to the nearest mesh vertices.

        :return: Array with x, y, z coordinates of the nearest vertices.
        """
        positions = self.measurement_positions()
        if positions is None:
            raise ValueError(
                "This map has no measurement positions (neither xyz nor measurement_points)."
            )

        # Creating KDTree for the mesh points
        kdtree_mesh = cKDTree(self.pv_mesh.points)

        # Query the KDTree for closest mesh points
        _, closest_points = kdtree_mesh.query(positions)

        # Fetch and return x, y, z coordinates of the nearest vertices
        projected_vertices_coords = self.pv_mesh.points[closest_points]

        return closest_points, projected_vertices_coords

    def create_polydata_for_projected_points(
        self,
        scalar_data: np.ndarray,
        scalar_name: str | None = None,
        scalars_on_vertices: bool = True,
    ) -> pv.PolyData:
        """
        Create a PyVista PolyData object for projected vertices and assign them corresponding scalar values.

        :param scalar_data: Original scalar data.
        :param scalar_name: Scalar attribute name; defaults to the map's primary scalar.
        :param scalars_on_vertices: Flag indicating if scalar values are based on vertices (True) or xyz points (False). Defaults to True.
        :return: PyVista PolyData object.
        """
        scalar_name = scalar_name or self.primary_scalar()
        # Generate pv_mesh if not already generated
        if self.pv_mesh is None:
            self.generate_anatomical_pv_mesh()

        # Project measurements onto mesh
        closest_points, projected_vertices_coords = self.project_measurements_to_mesh()

        # Create a PolyData object for the points
        p_points = pv.PolyData(projected_vertices_coords)

        # Ensure that the length of p_sim matches the number of projected points
        if scalars_on_vertices:
            p_sim = self.pv_mesh.point_data[scalar_name][closest_points]
        else:
            p_sim = scalar_data

        # Length checks
        if len(p_points.points) != len(p_sim):
            raise ValueError(
                f"Length mismatch: Number of points ({len(p_points.points)}) does not match number of scalar data points ({len(p_sim)}) for scalar '{scalar_name}'."
            )
        else:
            print("all ok")

        if scalars_on_vertices and len(closest_points) != len(p_sim):
            raise ValueError(
                f"Length mismatch: Number of closest points ({len(closest_points)}) does not match number of scalar data points ({len(p_sim)}) for scalar '{scalar_name}'."
            )
        else:
            print("all ok")

        # Assign scalar data to the point data of the PolyData object
        p_points.point_data[scalar_name] = p_sim

        return p_points

    def set_scalars(self, scalar_name: str, scalar_values: np.ndarray) -> None:
        """
        Set scalar values in the PyVista mesh and add a normalized version with a '-norm' suffix.

        :param scalar_name: Name of the scalar attribute.
        :param scalar_values: The scalar data to set.
        """
        self.pv_mesh.point_data[scalar_name] = scalar_values

        # Normalize the scalar values in the range [0, 1]
        min_value = np.nanmin(scalar_values)
        max_value = np.nanmax(scalar_values)
        if max_value - min_value != 0:
            normalized_values = (scalar_values - min_value) / (max_value - min_value)
        else:
            normalized_values = (
                scalar_values  # If all values are the same, no normalization is needed
            )

        # Set the normalized scalars with a '-norm' suffix
        self.pv_mesh.point_data[f"{scalar_name}-norm"] = normalized_values

    def interpolate_scalar_values(
        self,
        scalar: np.ndarray,
        scalar_name: str | None = None,
        distance_threshold: float | None = None,
        scalars_on_vertices: bool = True,
        method: str = "mask",
        sigma: float | None = None,
        cycle_length: float | None = None,
    ) -> pv.PolyData:
        """
        Decide what every mesh vertex shows for one quantity.

        Two different things can happen here, and ``method`` picks which:

        ``"mask"`` (default, and all this method ever did)
            Keep the **vendor's** per-vertex field and hide the vertices
            farther than ``distance_threshold`` from any measurement. Nothing
            is interpolated — the acquisition system already did that.

        ``"gaussian"`` / ``"geodesic"``
            **Recompute** the field from this map's measurement points, so the
            result follows from the raw data rather than from the vendor's
            undocumented interpolation. ``geodesic`` measures distance along
            the surface, which matters wherever the wall is thin enough for a
            straight line to cross it. See
            :mod:`~pulse_ep.core.interpolation`.

        :param scalar: Original (vendor) scalar values — used by ``"mask"``.
        :param scalar_name: Scalar attribute name; defaults to the map's primary scalar.
        :param distance_threshold: Maximum distance for interpolation. Defaults to None.
        :param scalars_on_vertices: Flag indicating if scalar values are based on vertices (True) or xyz points (False). Defaults to True.
        :param sigma: kernel width of the computed methods (default: the
            median spacing of the measurement points).
        :param cycle_length: interpolate cyclically — for a reentrant
            activation map, where late meets early (``0`` = infer the cycle
            length from the values).
        :return: Interpolated PyVista mesh.
        :raises ValueError: for an unknown ``method``, or for a computed method
            on a map whose measurement points do not carry this quantity.
        """
        scalar_name = scalar_name or self.primary_scalar()
        # Generate pv_mesh if not already generated
        if self.pv_mesh is None:
            self.generate_anatomical_pv_mesh()

        if method not in interpolation.METHODS:
            raise ValueError(
                f"unknown interpolation method {method!r}; use one of {interpolation.METHODS}"
            )
        if method != "mask":
            values = self._computed_scalar_values(
                scalar_name, method, distance_threshold, sigma, cycle_length
            )
            self.pv_mesh.point_data[scalar_name] = values
            return self.pv_mesh, values

        # The distance threshold is a confidence mask: only show scalar values
        # near where the map was actually measured. A map with no measurement
        # positions at all — an EnSiteX mesh carrying only per-vertex fields —
        # has nothing to mask against, so its values pass through unmasked
        # rather than the whole map failing to render.
        if self.measurement_positions() is None:
            # Generating the mesh simplifies it and resamples the registered
            # fields onto the new vertices, so a scalar array fetched before
            # that no longer matches. Re-resolve it rather than trusting the
            # caller's ordering.
            if len(scalar) != self.pv_mesh.n_points and scalar_name in self.scalar_fields:
                scalar = self.scalar_fields[scalar_name].values
            self.set_scalars(scalar_name, scalar)
            return self.pv_mesh, scalar

        # Project measurements onto mesh
        closest_points, projected_vertices_coords = self.project_measurements_to_mesh()

        # Initialize scalar values as NaN for all mesh points
        interpolated_scalars = np.full(self.pv_mesh.n_points, np.nan)

        # Create a KDTree from the projected_vertices_coords
        kdtree_p = cKDTree(projected_vertices_coords)

        # Query this tree to find distances from all points in the mesh
        distances, _ = kdtree_p.query(self.pv_mesh.points)

        # Vectorized threshold mask — avoids a Python loop over every vertex
        mask = distances <= distance_threshold
        interpolated_scalars[mask] = scalar[mask]

        # Set scalar values for the mesh points
        self.pv_mesh.point_data[scalar_name] = interpolated_scalars

        # Return the mesh with interpolated scalars
        return self.pv_mesh, interpolated_scalars

    def _computed_scalar_values(
        self,
        scalar_name: str,
        method: str,
        distance_threshold: float | None,
        sigma: float | None,
        cycle_length: float | None,
    ) -> np.ndarray:
        """The field this map's own measurements imply, on the current mesh."""
        positions, values = self.measured_field(scalar_name)
        if positions.size == 0:
            raise ValueError(
                f"cannot compute {scalar_name!r} from measurements: this map's points carry no "
                f"such quantity (method={method!r}; use method='mask' to show the vendor's field)"
            )

        if method == "gaussian":
            return interpolation.gaussian_interpolate(
                self.pv_mesh.points,
                positions,
                values,
                sigma=sigma,
                distance_threshold=distance_threshold,
                cycle_length=cycle_length,
            )

        # geodesic: measurements enter the diffusion at the vertex they sit on
        source_vertices = cKDTree(self.pv_mesh.points).query(positions)[1]
        triangles = self.pv_mesh.faces.reshape((-1, 4))[:, 1:]
        return interpolation.heat_interpolate(
            self.pv_mesh.points,
            triangles,
            source_vertices,
            values,
            sigma=sigma,
            distance_threshold=distance_threshold,
            cycle_length=cycle_length,
        )

        # Commented-out original RBF interpolation logic:
        # if scalars_on_vertices:
        #     # First, we prepare our interpolation function with known points
        #     x, y, z = self.pv_mesh.points[closest_points].T
        #     act = self.pv_mesh.point_data[scalar_name][closest_points]
        # else:
        #     # If scalars are based on projected vertices, use projected_vertices_coords
        #     x, y, z = projected_vertices_coords.T
        #     act = scalar
        #
        # try:
        #     rbf = Rbf(x, y, z, act, function='thin_plate')
        # except np.linalg.LinAlgError:
        #     print("Singular matrix encountered while interpolating. Skipping interpolation.")
        #     rbf = None
        # except ZeroDivisionError:
        #     print("Division by zero encountered while interpolating. Skipping interpolation.")
        #     rbf = None
        #
        # if rbf is not None:
        #     self.pv_mesh.point_data[scalar_name][i] = rbf(*self.pv_mesh.points[i])
        # else:
        #     interpolated_scalars[i] = scalar[i]

    def repair_and_simplify_mesh(self, target_reduction_ratio: float = 0.3):
        """
        Repairs and simplifies the mesh while preserving and re-interpolating scalar data.

        :param target_reduction_ratio: The target ratio for simplifying the mesh (e.g., 0.5 for 50% reduction).
        """
        # Check that the mesh is loaded and available
        if self.pv_mesh is None:
            raise ValueError(
                "Mesh data not loaded. Please load the mesh before running this method."
            )

        # Step 1: Repair the mesh using pymeshfix
        print("Repairing mesh...")
        vertices = self.pv_mesh.points
        faces = self.pv_mesh.faces.reshape((-1, 4))[:, 1:]
        meshfix = pymeshfix.MeshFix(vertices, faces)
        meshfix.repair()  # This repairs non-manifold edges, fills holes, etc.
        repaired_vertices, repaired_faces = meshfix.points, meshfix.faces

        # Step 2: Simplify the mesh
        print(f"Simplifying mesh with target reduction ratio: {target_reduction_ratio}")
        repaired_pv_mesh = pv.PolyData(
            repaired_vertices, np.hstack([np.full((repaired_faces.shape[0], 1), 3), repaired_faces])
        )
        simplified_mesh = repaired_pv_mesh.decimate_pro(target_reduction_ratio)

        # Step 3: Interpolate scalar data back onto the simplified mesh
        print("Interpolating scalar data onto simplified mesh...")
        original_points = self.pv_mesh.points  # Original mesh vertices
        simplified_points = simplified_mesh.points  # Simplified mesh vertices

        # Create KDTree from original points for nearest neighbor search
        kdtree_original = cKDTree(original_points)

        # Query the KDTree to find the closest points on the original mesh
        _, nearest_indices = kdtree_original.query(simplified_points)

        # Step 4: Re-map every per-vertex scalar via nearest neighbour so the
        # simplified mesh keeps its data. Handles the legacy CARTO ``act_bip``
        # layout and any vendor-neutral registered fields alike.
        if self.act_bip is not None:
            simplified_scalars_0 = self.act_bip[:, 0][nearest_indices]
            simplified_scalars_1 = self.act_bip[:, 1][nearest_indices]
            simplified_mesh.point_data["act_bip_0"] = simplified_scalars_0
            simplified_mesh.point_data["act_bip_1"] = simplified_scalars_1
            self.act_bip = np.column_stack([simplified_scalars_0, simplified_scalars_1])

        if self.scalar_fields:
            remapped: dict[str, ScalarField] = {}
            for name, field in self.scalar_fields.items():
                mask = field.status_mask[nearest_indices] if field.status_mask is not None else None
                remapped[name] = ScalarField(
                    field.values[nearest_indices], field.kind, field.unit, mask, field.source
                )
                simplified_mesh.point_data[name] = remapped[name].values
            self.scalar_fields = remapped

        # Replace the original mesh with the simplified one
        self.pv_mesh = simplified_mesh

        print("Mesh repair and simplification completed.")

    def get_average_face_scalars(
        self, scalar_name: str | None = None, pv_mesh: pv.core.pointset.PolyData | None = None
    ) -> np.ndarray:
        """
        Calculate the average scalar value for each face in the mesh.

        :param scalar_name: Scalar attribute name; defaults to the map's primary scalar.
        :param pv_mesh: The PyVista mesh object. If None, the stored mesh will be used.
        :return: Array of average face scalar values.
        """
        scalar_name = scalar_name or self.primary_scalar()
        if pv_mesh is None:
            pv_mesh = self.pv_mesh

        # Reshape the faces array
        faces = pv_mesh.faces.reshape((-1, 4))
        faces = faces[:, 1:]

        # Calculate the average face scalar values
        face_scalars = np.mean(pv_mesh.point_data[scalar_name][faces], axis=1)

        return face_scalars

    def plot_histogram(
        self,
        scalar_name: str | None = None,
        clim: tuple[float, float] | None | None = None,
        step_size: float = 5,
    ) -> tuple[plt.figure, dict]:
        scalar_name = scalar_name or self.primary_scalar()

        clim = clim or [65, 100]
        intervals = list(range(min(clim), max(clim) + 1, step_size))
        areas = []

        total_surface = self.area_of_surface()

        for i in range(len(intervals) - 1):
            min_val = intervals[i]
            max_val = intervals[i + 1]
            # area = self.area_of_range(min_val, max_val, scalar_name=scalar_name)
            area = (
                self.area_of_range(min_val, max_val, scalar_name=scalar_name) / total_surface * 100
            )
            areas.append(area)

        # Compute the lesser proportion
        # lesser_area = total_surface - sum(areas)
        # lesser_proportion = lesser_area / total_surface

        lesser_proportion = 1 - sum(areas) / 100

        # Calculate the CDF values
        cdf_values = np.cumsum(areas) / total_surface + lesser_proportion
        cdf_values = (np.cumsum(areas) + lesser_proportion * 100) / 100
        cdf_values = np.insert(cdf_values, 0, lesser_proportion)
        cdf_values = 1 - cdf_values[:-1]

        # cdf_values = np.insert(np.cumsum(areas), 0, lesser_proportion * 100) / 100
        # cdf_values = cdf_values[:-1]  # To make it have the same length as 'areas'

        fig, ax1 = plt.subplots(figsize=(10, 6))

        ax1.set_xlabel("Similarity [%]")
        ax1.set_ylabel("Area [%]", color="blue")
        labels = [f"{intervals[i]}-{intervals[i + 1]}" for i in range(len(intervals) - 1)]
        ax1.bar(labels, areas, alpha=0.6, color="blue", label="Area")
        ax1.tick_params(axis="y", labelcolor="blue")

        ax2 = ax1.twinx()  # instantiate a second axes that shares the same x-axis
        ax2.set_ylabel("1-CDF", color="red")
        ax2.plot(labels, cdf_values, color="red", marker="o", linestyle="-", label="1-CDF")
        # ax2.plot(intervals[:-1], cdf_values, color='red', marker='o', linestyle='-', label='CDF')
        ax2.tick_params(axis="y", labelcolor="red")

        # Adjust title and layout
        plt.suptitle(self.study_name)
        plt.title(self.map_name)
        fig.tight_layout()

        # Create a combined legend for both ax1 and ax2
        lines, labels = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        # ax2.legend(lines + lines2, labels + labels2, loc='upper left')

        bin_info = {"bin_edges": intervals, "area_values": areas, "cdf_values": cdf_values}

        return (fig, bin_info)

    def plot_mesh(
        self,
        scalar_name: str | None = None,
        distance: float | None = None,
        off_screen: bool = True,
        clim: tuple[float, float] | None | None = None,
        plotter=None,
        norm: bool = False,
        atrium: str = "RA",
        direction: str = "AP",
    ) -> pv.Plotter:
        """
        Generate a PyVista mesh, align it, and set up the plotter.

        :param distance: Optional maximum distance to set color values (default: None).
        :param off_screen: Optional flag to render the plot off screen (default: True).
        :param clim: Optional color range limits (default: None).
        :return: The PyVista plotter object and the face scalars.
        """
        scalar_name = scalar_name or self.primary_scalar()
        # print("Working on: " + self.map_name)

        # Generate anatomical_pv_mesh and interpolate scalar values
        pv_mesh = self.generate_anatomical_pv_mesh()

        # Resolve the requested scalar (defaults to the map's primary
        # quantity — see ``primary_scalar``).
        scalar_data = self.get_scalar(scalar_name)

        # Calculate the 98th percentile value
        # threshold = np.nanpercentile(scalar_data, 98)

        # Calculate the mean and standard deviation, ignoring NaNs
        mean_value = np.nanmean(scalar_data)
        std_dev = np.nanstd(scalar_data)

        # Calculate the threshold as mean + 2 * standard deviation
        threshold = mean_value + 2 * std_dev

        # Replace values higher than the threshold with NaN
        scalar_data[scalar_data > threshold] = np.nan

        # Calculate the maximum value of scalar_data
        max_value = np.nanmax(scalar_data)

        if max_value < 0:
            scalar_data = -scalar_data

        if norm:
            max_value = np.nanmax(scalar_data)
            if max_value != 0:
                scalar_data = (scalar_data / max_value) * 100
                max_value = np.nanmax(scalar_data)

        # Set both the original and normalized scalar values
        self.set_scalars(scalar_name, scalar_data)

        # Interpolate data
        pv_mesh, scalar_data = self.interpolate_scalar_values(
            scalar_data, scalar_name=scalar_name, distance_threshold=distance
        )

        # Create a PolyData object for the points
        p_points = self.create_polydata_for_projected_points(scalar_data, scalar_name=scalar_name)

        # Create a colormap
        clim = clim or [np.nanmin(scalar_data), np.nanmax(scalar_data)]
        cmap = plot_proc.create_modified_hsv_colormap()

        # Create a Plotter object if needed
        if plotter is None:
            plotter = pv.Plotter(window_size=(1300, 1000), off_screen=off_screen)

        plotter.add_text(self.map_name, position="upper_edge", font_size=20, color="black")
        plotter.add_text(self.study_name, position=(0.5, 0.8), font_size=20, color="black")

        plotter.add_mesh(pv_mesh, scalars=scalar_name, show_scalar_bar=False, cmap=cmap, clim=clim)
        plotter.add_points(p_points, scalars=scalar_name, cmap=cmap, clim=clim, point_size=5)

        plotter.add_scalar_bar(
            title=scalar_name,
            position_x=0.90,
            position_y=0.1,
            label_font_size=20,
            title_font_size=25,
            vertical=True,
            n_labels=10,
        )
        plotter.show_grid()
        plotter.add_mesh(pv_mesh.outline(), color="black")
        plotter.set_scale(xscale=1, yscale=1, zscale=1)

        # Create a vector pointing towards the maximum scalar vertex
        # view_vector = max_scalar_vertex - np.mean(pv_mesh.points, axis=0)

        # Normalize the view vector
        # view_vector /= np.linalg.norm(view_vector)

        # Set the view vector for focusing on the maximum scalar
        # plotter.view_vector(view_vector)

        print("Plot: " + atrium + "/" + direction)

        if direction == "AP":
            view_vector = np.array([0, 0, 1])  # Assuming the Z-axis is front to back
            up_vector = np.array([0, -1, 0])  # Assuming the Y-axis is up in AP view
        elif direction == "PA":
            view_vector = np.array([0, 0, -1])  # Looking from back to front
            up_vector = np.array([0, -1, 0])  # Still the same up direction
        elif direction == "RL":
            if atrium == "RA":
                view_vector = np.array([1, 0, 0])  # Right to left
                up_vector = np.array([-1, -1, 0])  # Rotate 90 degrees clockwise around the X-axis
                camera_position = np.array(  # noqa: F841
                    [1, 0, 0]
                )  # Camera at (1, 0, 0) looking towards the origin
            else:  # LA
                view_vector = np.array([-1, 0, 0])  # Left to right
                up_vector = np.array([0, 0, 1])  # Default up direction

        # Set the view vector for the plotter
        plotter.view_vector(view_vector, up_vector)

        return plotter

    def extract_mesh_data(
        self, scalar_name: str | None = None, distance: float | None = None
    ) -> dict:
        scalar_name = scalar_name or self.primary_scalar()
        if scalar_name is None:
            scalar_name = self.primary_scalar()

        # Generate anatomical_pv_mesh and interpolate scalar values
        pv_mesh = self.generate_anatomical_pv_mesh()

        # Resolve already-conditioned values via the vendor-neutral resolver;
        # no scalar-specific handling lives here anymore.
        scalar_data = self.get_scalar(scalar_name)

        # Interpolate data to match mesh points
        pv_mesh, interpolated_scalar_data = self.interpolate_scalar_values(
            scalar_data, scalar_name=scalar_name, distance_threshold=distance
        )

        # Ensure normalized scalars are available for the mesh
        norm_key = f"{scalar_name}-norm"
        normalized_mesh_scalar_data = pv_mesh.point_data.get(norm_key, None)

        if normalized_mesh_scalar_data is None:
            self.set_scalars(scalar_name, interpolated_scalar_data)
            normalized_mesh_scalar_data = pv_mesh.point_data.get(norm_key, None)
            if normalized_mesh_scalar_data is None:
                raise KeyError(
                    f"Failed to find or create normalized data for key '{norm_key}' in the mesh"
                )

        vertices = pv_mesh.points
        faces = pv_mesh.faces.reshape((-1, 4))[:, 1:]

        if len(vertices) != len(interpolated_scalar_data):
            raise ValueError(
                f"Length mismatch: vertices ({len(vertices)}) vs scalars ({len(interpolated_scalar_data)})."
            )

        # Build point data (measurement points projected onto mesh). Read the
        # positions through measurement_positions(), not the legacy xyz array:
        # an EnSiteX map keeps them as MeasurementPoints and would otherwise
        # report no acquisition points at all despite having thousands.
        if self.measurement_positions() is not None:
            p_points = self.create_polydata_for_projected_points(
                interpolated_scalar_data, scalar_name=scalar_name
            )

            min_value = np.nanmin(interpolated_scalar_data)
            max_value = np.nanmax(interpolated_scalar_data)
            if max_value - min_value != 0:
                normalized_point_data = (p_points.point_data[scalar_name] - min_value) / (
                    max_value - min_value
                )
            else:
                normalized_point_data = p_points.point_data[scalar_name]

            point_data = {
                "coordinates": p_points.points,
                "scalar_data": p_points.point_data[scalar_name],
                "normalized_scalar_data": normalized_point_data,
            }
        else:
            # No measurement point positions available
            point_data = {
                "coordinates": np.empty((0, 3)),
                "scalar_data": np.array([]),
                "normalized_scalar_data": np.array([]),
            }

        return {
            # Name the quantity that was actually used: callers may omit
            # scalar_name to get the map's primary, and then have no other way
            # to learn what they received.
            "scalar_name": scalar_name,
            "mesh_data": {
                "vertices": vertices,
                "faces": faces,
                "scalar_data": interpolated_scalar_data,
                "normalized_scalar_data": normalized_mesh_scalar_data,
            },
            "point_data": point_data,
        }

    def precompute_areas(self) -> None:
        """Precompute and store the area of each triangle (cell) in the mesh."""
        if self.pv_mesh is None:
            self.generate_anatomical_pv_mesh()

        # Check if 'Area' is already computed
        if "Area" not in self.pv_mesh.cell_data:
            areas = self.pv_mesh.compute_cell_sizes(length=False, area=True, volume=False)
            self.pv_mesh.cell_data["Area"] = areas["Area"]

    def calculate_areas_for_intervals(
        self, intervals: list, scalar_name: str | None = None, distance: float | None = None
    ) -> list:
        """
        Prepare the mesh and calculate the areas for a given list of intervals.

        :param intervals: List of (min_value, max_value) tuples defining the intervals.
        :param scalar_name: Scalar attribute name; defaults to the map's primary scalar.
        :param distance: Optional maximum distance to set color values.
        :return: List of areas corresponding to each interval.
        """
        scalar_name = scalar_name or self.primary_scalar()
        if scalar_name is None:
            scalar_name = self.primary_scalar()

        # Generate anatomical_pv_mesh and interpolate scalar values
        pv_mesh = self.generate_anatomical_pv_mesh(simplify=False)

        # Resolve already-conditioned values (see :meth:`get_scalar`); no
        # scalar-specific handling lives here anymore.
        scalar_data = self.get_scalar(scalar_name)

        pv_mesh.point_data[scalar_name] = scalar_data

        # Interpolate data
        pv_mesh, scalar_data = self.interpolate_scalar_values(
            scalar_data, scalar_name=scalar_name, distance_threshold=distance
        )

        # Adjacent bins share no boundary values; include the final upper edge.
        final_upper = max((hi for _, hi in intervals), default=None)
        areas = []
        for min_value, max_value in intervals:
            area = self.area_of_range(
                min_value,
                max_value,
                scalar_name=scalar_name,
                include_upper=max_value == final_upper,
            )
            areas.append(area)

        return areas

    def save_mesh_to_OBJ(
        self, filename: str, scalar_name: str | None = None, distance: float | None = None
    ) -> None:
        scalar_name = scalar_name or self.primary_scalar()
        # Generate anatomical_pv_mesh and interpolate scalar values
        pv_mesh = self.generate_anatomical_pv_mesh()
        pv_mesh.save(filename)

    def area_of_range(
        self, min_value, max_value, scalar_name: str | None = None, *, include_upper: bool = False
    ):
        """Area in [min_value, max_value), optionally including the upper edge."""
        scalar_name = scalar_name or self.primary_scalar()
        if "Area" not in self.pv_mesh.cell_data:
            self.precompute_areas()

        # Convert point data to cell data
        cell_data = self.point_data_to_cell_data(scalar_name)

        # Filter based on the scalar range
        upper = cell_data <= max_value if include_upper else cell_data < max_value
        mask = (cell_data >= min_value) & upper

        # Retrieve and sum the precomputed areas
        selected_areas = self.pv_mesh.cell_data["Area"][mask]
        total_area = np.sum(selected_areas)

        return total_area / 100

    def point_data_to_cell_data(self, scalar_name: str) -> np.ndarray:
        """Convert per-point data to per-cell data by averaging point values for each triangle, handling NaNs."""
        if self.pv_mesh is None:
            self.generate_anatomical_pv_mesh()

        # Check if the cell data is already computed and stored
        if f"{scalar_name}_cell" in self.pv_mesh.cell_data:
            return self.pv_mesh.cell_data[f"{scalar_name}_cell"]

        # Get the scalar data at the points
        point_data = self.pv_mesh.point_data[scalar_name]

        # Convert faces into groups of vertex indices — shape (n_faces, 3)
        faces = self.pv_mesh.faces.reshape(-1, 4)[:, 1:]

        # Gather all vertex values for every face at once — shape (n_faces, 3)
        vertex_values = point_data[faces]

        # Vectorized nanmean: only compute on rows with at least one non-NaN value
        # to avoid RuntimeWarning: "Mean of empty slice" on all-NaN rows.
        all_nan = np.all(np.isnan(vertex_values), axis=1)
        cell_data = np.full(len(vertex_values), np.nan)
        has_data = ~all_nan
        if has_data.any():
            cell_data[has_data] = np.nanmean(vertex_values[has_data], axis=1)

        # Store the computed cell data in the mesh for future use
        self.pv_mesh.cell_data[f"{scalar_name}_cell"] = cell_data

        return cell_data

    def area_of_surface(self):
        # Use precomputed areas when available (avoids redundant compute_cell_sizes call)
        if "Area" not in self.pv_mesh.cell_data:
            self.precompute_areas()
        return np.sum(self.pv_mesh.cell_data["Area"]) / 100

    def report(self):
        min_scalar, max_scalar, avg_scalar, std_scalar = self.get_scalar_statistics()
        report = f"Name: {self.study_name}/{self.map_name}, min: {min_scalar}, max: {max_scalar}, avg: {avg_scalar}, std: {std_scalar}"
        return report

    def distance_within_range(self, min_value, max_value, scalar_name: str | None = None):
        scalar_name = scalar_name or self.primary_scalar()
        # Extract points within the range
        thresholded_mesh = self.pv_mesh.threshold([min_value, max_value], scalars=scalar_name)
        points = thresholded_mesh.points

        # If there are no points within the range, return 0 for both min and max distances
        if len(points) == 0:
            return 0, 0, 0, 0

        # Create a KDTree for efficient distance queries
        tree = cKDTree(points)

        # Compute pairwise distances - using query to find the closest non-identical point
        distances, _ = tree.query(points, k=2)

        # The distances array has 2 columns - the first column are zeros (distance to self)
        # The second column contains the smallest distances to other points
        min_distance = np.max(distances[:, 1])  # Maximum distance to the nearest neighbor

        # Compute the maximum distance between any two points within the range
        pairwise_distances = np.linalg.norm(points[:, np.newaxis] - points, axis=2)
        max_distance = np.max(pairwise_distances)

        average_distance = np.mean(
            pairwise_distances[np.triu_indices_from(pairwise_distances, k=1)]
        )

        # Extract the upper triangular values (excluding the diagonal)
        distances_flat = pairwise_distances[np.triu_indices_from(pairwise_distances, k=1)]

        # Compute median
        median_distance = np.median(distances_flat)

        return min_distance, max_distance, average_distance, median_distance

    def get_scalar_statistics(self, scalar_name: str | None = None):
        """
        Calculate the minimum, maximum, average, and standard deviation of scalar values.

        :param scalar_name: Scalar attribute name; defaults to the map's primary scalar.
        :return: Tuple containing (min, max, avg, std) of scalar values.
        """
        scalar_name = scalar_name or self.primary_scalar()
        # Ensure self.pv_mesh is not None
        if self.pv_mesh is None:
            raise ValueError(
                "PV mesh is not generated. Please generate it before calculating statistics."
            )

        # Extract scalar values and convert to a regular NumPy array
        scalar_values = np.array(self.pv_mesh.point_data[scalar_name])

        # Calculate statistics
        min_scalar = np.nanmin(scalar_values)
        max_scalar = np.nanmax(scalar_values)
        avg_scalar = np.nanmean(scalar_values)
        std_scalar = np.nanstd(scalar_values)

        return min_scalar, max_scalar, avg_scalar, std_scalar
