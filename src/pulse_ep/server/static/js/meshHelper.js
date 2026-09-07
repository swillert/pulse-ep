import * as THREE from 'three';

export class MeshHelper {
    constructor(scene, camera, renderer, eventEmitter) {
        this.scene = scene;
        this.camera = camera;
        this.renderer = renderer;
        this.eventEmitter = eventEmitter;
        this.currentMapId = null;
        this.currentMapName = 'unknown';
        this.currentStudyName = 'unknown';
        this.currentColormap = 'jet';
        this.isRelative = true;  // see ColormapWidget
        this.clipping = true;
        this.currentDatatype = null; // set from the map's own scalars
        this.center = new THREE.Vector3();
    }

    async loadMesh(mapId, mapName, studyName) {
        this.currentMapId = mapId;
        this.currentStudyName = studyName;
        this.currentMapName = mapName;
        await this.fetchAndRenderMesh(mapId, mapName, studyName);
    }

    async reloadMesh() {
        if (!this.currentMapId) {
            console.warn('No current map ID to reload mesh');
            return;
        }
        await this.fetchAndRenderMesh(this.currentMapId, this.currentMapName, this.currentStudyName, true);
    }

    async fetchAndRenderMesh(mapId, mapName, studyName, isReload = false) {
        const token = localStorage.getItem('token');
        // Omit scalar_name entirely when none is chosen yet, so the server
        // picks the map's own primary quantity. Interpolating a null here sent
        // the literal string "null", which no map has a field for.
        const params = new URLSearchParams({ map_id: mapId, distance: this.currentDistance });
        if (this.currentDatatype) params.set('scalar_name', this.currentDatatype);
        const url = `/get_mesh_data?${params}`;

        try {
            console.log('Fetching mesh data with URL:', url);

            const response = await fetch(url, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!response.ok) {
                throw new Error('Failed to fetch mesh data: ' + response.statusText);
            }

            const data = await response.json();
            console.log('Mesh data received:', data);

            // Always clear first. This used to be skipped on a reload, so
            // changing the datatype or colormap added another mesh on top of
            // the previous one instead of replacing it.
            this.clearScene();

            // Fetch the colormap data once and use it for both mesh and points
            const colormapResponse = await fetch(`/colormaps/${this.currentColormap}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            const colormapData = await colormapResponse.json();

            console.log('Colormap data fetched:', colormapData);
            console.log('Intervals:', colormapData.intervals);

            // Handle mesh geometry and coloring
            const geometry = new THREE.BufferGeometry();
            const vertices = new Float32Array(data.mesh_data.vertices.flat());
            const faces = new Uint32Array(data.mesh_data.faces.flat());
            geometry.setIndex(new THREE.BufferAttribute(faces, 1));
            geometry.setAttribute('position', new THREE.BufferAttribute(vertices, 3));

            if (data.mesh_data.scalar_data && data.mesh_data.scalar_data.length) {
                const scalarValues = data.mesh_data.scalar_data.flat().map(val => parseFloat(val)).filter(val => !isNaN(val));
                console.log('Scalar values:', scalarValues);

                const colors = this.applyColormap(data.mesh_data.scalar_data, colormapData);
                console.log('Colors applied to mesh:', colors);

                geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

                if (scalarValues.length > 0) {
                    const minScalar = Math.min(...scalarValues);
                    const maxScalar = Math.max(...scalarValues);

                    this.eventEmitter.emit('updateProperties', {
                        mapId: mapId || 'Unknown',
                        mapName: mapName || 'Unknown',
                        studyName: studyName || 'Unknown',
                        minScalar: minScalar,
                        maxScalar: maxScalar,
                    });

                    const intervals = colormapData.intervals.map((interval, index) => {
                        if (index < colormapData.intervals.length - 1) {
                            return [interval, colormapData.intervals[index + 1]];
                        }
                    }).filter(Boolean);

                    console.log('Intervals for area calculation:', intervals);
                    await this.calculateAreasForIntervals(mapId, intervals);

                } else {
                    console.warn('No valid scalar data found in mesh data.');
                    this.eventEmitter.emit('updateProperties', {
                        mapId,
                        mapName: 'No data',
                        studyName,
                        minScalar: 'N/A',
                        maxScalar: 'N/A'
                    });
                }
            } else {
                console.warn('No scalar data found in mesh data.');
                this.eventEmitter.emit('updateProperties', {
                    mapId,
                    mapName: 'No data',
                    studyName,
                    minScalar: 'N/A',
                    maxScalar: 'N/A'
                });
            }

            const material = new THREE.MeshBasicMaterial({
                vertexColors: true,
                side: THREE.DoubleSide
            });

            const mesh = new THREE.Mesh(geometry, material);

            if (!isReload) {
                this.scene.add(mesh);

                const box = new THREE.Box3().setFromObject(mesh);
                const size = new THREE.Vector3();
                box.getSize(size);
                box.getCenter(this.center);

                console.log('Mesh center calculated:', this.center);

                mesh.position.sub(this.center);

                this.camera.position.set(0, 0, size.length() * 2);
                this.camera.lookAt(new THREE.Vector3(0, 0, 0));
                this.camera.updateProjectionMatrix();
            } else {
                mesh.position.sub(this.center);
                this.scene.add(mesh);
            }

            // Handle point data as colored spheres
            if (data.point_data && data.point_data.coordinates && data.point_data.coordinates.length) {
                console.log('Point data received:', data.point_data);

                const pointScalars = this.isRelative
                    ? data.point_data.normalized_scalar_data // Use normalized scalars if isRelative is true
                    : data.point_data.scalar_data;           // Use raw scalars if isRelative is false

                console.log('Point Scalars:', pointScalars);

                if (pointScalars && pointScalars.length > 0) {
                    const pointColors = this.applyColormap(pointScalars, colormapData);
                    console.log('Colors applied to points:', pointColors);

                    const pointGeometry = new THREE.SphereGeometry(0.125, 32, 32); // Diameter 0.25

                    for (let i = 0; i < data.point_data.coordinates.length; i++) {
                        const [x, y, z] = data.point_data.coordinates[i];

                        const color = new THREE.Color(
                            pointColors[i * 3],
                            pointColors[i * 3 + 1],
                            pointColors[i * 3 + 2]
                        );

                        const pointMaterial = new THREE.MeshStandardMaterial({
                            color: color,       // Set the color for the sphere
                            metalness: 0.3,     // Moderate reflectivity
                            roughness: 0.8,     // Increase roughness to make the material less reflective and more visible
                            transparent: false, // Not transparent
                        });

                        const sphere = new THREE.Mesh(pointGeometry, pointMaterial);
                        sphere.position.set(x - this.center.x, y - this.center.y, z - this.center.z);

                        this.scene.add(sphere);
                    }
                } else {
                    console.warn('No valid point scalars found or no colormap applied to points.');
                }
            }

            console.log('Mesh and spheres added to scene and rendered.');
            this.renderer.render(this.scene, this.camera);
        } catch (error) {
            console.error('Error loading mesh:', error);
        }
    }

    applyColormap(scalarData, colormapData) {
        const colors = new Float32Array(scalarData.length * 3);
        const grayColor = [0.5, 0.5, 0.5];
        const whiteColor = [1, 1, 1];

        const colormapColors = colormapData.colors.map(color => {
            const hex = parseInt(color.slice(1), 16);
            return [
                ((hex >> 16) & 255) / 255,
                ((hex >> 8) & 255) / 255,
                (hex & 255) / 255
            ];
        });

        let intervals = colormapData.intervals;
        const minInterval = Math.min(...intervals);
        const maxInterval = Math.max(...intervals);

        let minValue = Math.min(...scalarData.filter(val => val !== null && !isNaN(val)));
        let maxValue = Math.max(...scalarData.filter(val => val !== null && !isNaN(val)));

        if (this.isRelative) {
            const range = maxValue - minValue;
            scalarData = scalarData.map(val => {
                if (val !== null && !isNaN(val)) {
                    return (val - minValue) / range;
                }
                return val;
            });

            // Normalize intervals
            const intervalRange = maxInterval - minInterval;
            intervals = intervals.map(interval => (interval - minInterval) / intervalRange);
        }

        const linearColor = new THREE.Color();
        for (let i = 0; i < scalarData.length; i++) {
            const scalar = scalarData[i];
            let color;

            if (scalar === null || isNaN(scalar)) {
                color = grayColor;
            } else {
                if (scalar < intervals[0]) {
                    color = this.clipping ? colormapColors[0] : whiteColor;
                } else if (scalar > intervals[intervals.length - 1]) {
                    color = this.clipping ? colormapColors[colormapColors.length - 1] : whiteColor;
                } else {
                    // Determine color based on gradient setting
                    for (let j = 0; j < intervals.length - 1; j++) {
                        if (scalar >= intervals[j] && scalar <= intervals[j + 1]) {
                            if (this.useGradient) {
                                // Interpolate between colors if gradient is active
                                const t = (scalar - intervals[j]) / (intervals[j + 1] - intervals[j]);
                                color = [
                                    colormapColors[j][0] + t * (colormapColors[j + 1][0] - colormapColors[j][0]),
                                    colormapColors[j][1] + t * (colormapColors[j + 1][1] - colormapColors[j][1]),
                                    colormapColors[j][2] + t * (colormapColors[j + 1][2] - colormapColors[j][2])
                                ];
                            } else {
                                // Assign the solid color corresponding to the interval without blending
                                color = colormapColors[j];
                            }
                            break;
                        }
                    }
                }
            }

            // The colour-bar hex values and interpolation are sRGB. Vertex
            // attributes must be linear: otherwise the renderer brightens
            // them a second time and the mesh no longer matches its legend.
            linearColor.setRGB(color[0], color[1], color[2], THREE.SRGBColorSpace);
            linearColor.toArray(colors, i * 3);
        }

        return colors;
    }

    async calculateAreasForIntervals(mapId, intervals) {
        const token = localStorage.getItem('token');
        const url = '/calculate_areas_for_intervals';

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    map_id: mapId,
                    intervals: intervals,
                    // omitted when unset — the server resolves the map's primary
                    ...(this.currentDatatype ? { scalar_name: this.currentDatatype } : {}),
                    distance: this.currentDistance
                })
            });

            if (!response.ok) {
                throw new Error('Failed to calculate areas: ' + response.statusText);
            }

            const data = await response.json();
            this.displayIntervalsAndAreas(intervals, data.areas);
        } catch (error) {
            console.error('Error calculating areas for intervals:', error);
        }
    }

    displayIntervalsAndAreas(intervals, areas) {
        const overlayText = document.getElementById('overlay-text');
        if (!overlayText) {
            console.error('Overlay text element not found');
            return;
        }

        let content = 'Intervals and Areas:\n';
        for (let i = 0; i < intervals.length; i++) {
            content += `Interval: ${intervals[i].join(' - ')}, Area: ${areas[i]}\n`;
        }

        // Ensuring that new lines are rendered correctly in the overlayText
        overlayText.innerHTML = content.replace(/\n/g, '<br/>');
    }

    /**
     * Remove the rendered objects, keeping the scene's lights.
     *
     * This used to remove *every* child, lights included — harmless only
     * because the mesh material is unlit, and a trap for anyone who changes
     * that. Geometries and materials are disposed explicitly: a 50k-vertex
     * mesh reloaded on every datatype change otherwise leaks GPU memory.
     */
    clearScene() {
        const disposable = this.scene.children.filter((child) => !child.isLight);
        for (const child of disposable) {
            this.scene.remove(child);
            child.geometry?.dispose();
            if (Array.isArray(child.material)) {
                child.material.forEach((m) => m.dispose());
            } else {
                child.material?.dispose();
            }
        }
    }
}
