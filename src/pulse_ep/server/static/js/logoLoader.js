import * as THREE from 'three';
import { SVGLoader } from 'three/addons/loaders/SVGLoader.js';

export class LogoLoader {
    constructor(scene, camera, renderer) {
        this.scene = scene;
        this.camera = camera;
        this.renderer = renderer;

        // Set background color to black
        this.renderer.setClearColor(0x000000);

        // Add ambient light
        const ambientLight = new THREE.AmbientLight(0xffffff, 1.0); // Increase intensity
        this.scene.add(ambientLight);

        // Add a directional light
        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.7); // Increase intensity
        directionalLight.position.set(1, 1, 1).normalize();
        this.scene.add(directionalLight);
    }

    loadLogo(url) {
        const loader = new SVGLoader();

        loader.load(
            url,
            (data) => {
                const paths = data.paths;

                const material = new THREE.MeshStandardMaterial({
                    color: 0xffffff, // White logo color
                    metalness: 0.7,
                    roughness: 0.4,
                    side: THREE.DoubleSide,
                    envMapIntensity: 1.2,
                    wireframe: false, // Set to true for debugging
                });

                const group = new THREE.Group();

                paths.forEach((path) => {
                    const shapes = path.toShapes(true);
                    shapes.forEach((shape) => {
                        const extrudeSettings = {
                            depth: 20,
                            bevelEnabled: true,
                            bevelThickness: 2,
                            bevelSize: 1,
                            bevelSegments: 5,
                            curveSegments: 12,
                            steps: 2,
                        };

                        const geometry = new THREE.ExtrudeGeometry(shape, extrudeSettings);
                        const mesh = new THREE.Mesh(geometry, material);
                        group.add(mesh);
                    });
                });

                const boundingBox = new THREE.Box3().setFromObject(group);
                const size = boundingBox.getSize(new THREE.Vector3());
                const scale = Math.min(200 / size.x, 200 / size.y);
                group.scale.multiplyScalar(scale);

                group.scale.y *= -1;

                boundingBox.setFromObject(group);
                const center = boundingBox.getCenter(new THREE.Vector3());
                group.position.sub(center);

                this.scene.add(group);

                this.renderer.render(this.scene, this.camera);
            },
            undefined,
            (error) => {
                console.error('An error happened while loading the SVG:', error);
            }
        );
    }
}
