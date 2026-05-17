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

        // Initialize the resizer functionality
        this.initializeResizing();
    }

    initializeResizing() {
        const searchPanel = document.getElementById('search');
        const studiesPanel = document.getElementById('studies');
        const resizer = searchPanel.querySelector('.resizer');

        let isResizing = false;
        let startY = 0;
        let startHeight = 0;

        // Start resizing when the mouse is pressed down on the resizer
        resizer.addEventListener('mousedown', function (e) {
            isResizing = true;
            startY = e.clientY;
            startHeight = parseInt(document.defaultView.getComputedStyle(searchPanel).height, 10);
            document.addEventListener('mousemove', resizePanels);
            document.addEventListener('mouseup', stopResizing);
            document.body.style.userSelect = 'none'; // Prevent text selection while resizing
        });

        // Resize the panels when the mouse is moved
        function resizePanels(e) {
            if (!isResizing) return;

            const dy = e.clientY - startY;
            const newHeight = startHeight + dy;

            // Prevent resizing from making the panel too small or too large
            if (newHeight > 50 && newHeight < window.innerHeight * 0.6) {
                searchPanel.style.height = `${newHeight}px`;
                studiesPanel.style.height = `calc(100% - ${newHeight + 50}px)`; // Adjust studies panel height dynamically
            }
        }

        // Stop resizing when the mouse is released
        function stopResizing() {
            isResizing = false;
            document.removeEventListener('mousemove', resizePanels);
            document.removeEventListener('mouseup', stopResizing);
            document.body.style.userSelect = ''; // Restore text selection after resizing
        }
    }
}

// Initialize the dashboard when the DOM is ready
const dashboardController = new DashboardController();
document.addEventListener('DOMContentLoaded', () => dashboardController.initialize());