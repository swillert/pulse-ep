import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { LogoLoader } from './logoLoader.js';
import { MeshHelper } from './meshHelper.js';

class ViewerWidget {
    constructor(eventEmitter) {
        this.eventEmitter = eventEmitter;
        this.logoDisplayed = true; // Flag to control when the logo is displayed
    }

    initialize() {
        this.initializeViewer();

        const logoLoader = new LogoLoader(this.scene, this.camera, this.renderer);
        logoLoader.loadLogo('/static/assets/logo.svg'); // Load and display the logo immediately

        const meshHelper = new MeshHelper(this.scene, this.camera, this.renderer, this.eventEmitter);

        this.eventEmitter.on('loadMesh', (mapId, mapName, studyName) => {
            if (this.logoDisplayed) {
                meshHelper.clearScene(); // Clear the logo before loading the mesh
                this.logoDisplayed = false; // Mark that the logo is no longer displayed
            }

            console.log('Viewer received loadMesh event with parameters:', {
                mapId: mapId,
                mapName: mapName,
                studyName: studyName
            });
            meshHelper.loadMesh(mapId, mapName, studyName);
        });

        this.eventEmitter.on('colormapChanged', (colormap, isRelative, clipping, datatype, distance, useGradient) => {
            meshHelper.currentColormap = colormap;
            meshHelper.isRelative = isRelative;
            meshHelper.clipping = clipping;
            meshHelper.currentDatatype = datatype;
            meshHelper.currentDistance = distance;
            meshHelper.useGradient = useGradient;
            if (meshHelper.currentMapId) {
                meshHelper.reloadMesh();
            } else {
                console.warn('No current map ID to reload mesh');
            }
        });
    }

    initializeViewer() {
        const viewer = document.getElementById('viewer');
        if (!viewer) {
            console.error('Viewer element not found');
            return;
        }

        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(viewer.offsetWidth, viewer.offsetHeight);
        viewer.appendChild(this.renderer.domElement);

        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(75, viewer.offsetWidth / viewer.offsetHeight, 0.1, 1000);
        this.camera.position.set(0, 0, 300);

        const ambientLight = new THREE.AmbientLight(0x404040);
        this.scene.add(ambientLight);
        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.5);
        directionalLight.position.set(0, 1, 1);
        this.scene.add(directionalLight);

        this.controls = new OrbitControls(this.camera, this.renderer.domElement);
        this.controls.addEventListener('change', () => this.renderer.render(this.scene, this.camera));

        const animate = () => {
            requestAnimationFrame(animate);
            this.controls.update();
            this.renderer.render(this.scene, this.camera);
        };

        animate();
    }
}

export default ViewerWidget;
