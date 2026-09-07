import { EventEmitter } from './eventEmitter.js';
import PropertiesWidget from './propertiesWidget.js';
import StudySelectorWidget from './studySelectorWidget.js';
import ColormapWidget from './colormapWidget.js';
import ViewerWidget from './viewerWidget.js';

class DashboardController {
    constructor() {
        this.eventEmitter = new EventEmitter();
    }

    initialize() {
        // Initialize all the widgets
        this.viewerWidget = new ViewerWidget(this.eventEmitter);
        this.viewerWidget.initialize();

        this.studySelectorWidget = new StudySelectorWidget(this.eventEmitter);
        this.studySelectorWidget.initialize();

        this.colormapWidget = new ColormapWidget(this.eventEmitter);
        this.colormapWidget.initialize();

        this.propertiesWidget = new PropertiesWidget(this.eventEmitter);
        this.propertiesWidget.initialize();

        // The template owns the current sidebar resizer.
    }
}

// Initialize the dashboard when the DOM is ready
const dashboardController = new DashboardController();
document.addEventListener('DOMContentLoaded', () => dashboardController.initialize());