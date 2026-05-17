import { EventEmitter } from './eventEmitter.js';

class PropertiesWidget {
    constructor(eventEmitter) {
        this.eventEmitter = eventEmitter;
        this.initialize();
    }

    initialize() {
        this.eventEmitter.on('updateProperties', (data) => {
            const set = (id, val) => {
                const el = document.getElementById(id);
                if (el) el.textContent = val ?? '—';
            };
            set('prop-map-id',    data.mapId);
            set('prop-map-name',  data.mapName);
            set('prop-study-name',data.studyName);
            set('prop-min-scalar',data.minScalar !== null ? data.minScalar : 'N/A');
            set('prop-max-scalar',data.maxScalar !== null ? data.maxScalar : 'N/A');
        });
    }
}

export default PropertiesWidget;
