import { EventEmitter } from './eventEmitter.js';

class ColormapWidget {
    constructor(eventEmitter) {
        this.eventEmitter = eventEmitter;
        this.currentColormap = 'jet'; // Initialize with a default colormap
        this.currentDatatype = 'act'; // Initialize with a default datatype
        this.editingColormapId = null; // Track which colormap is being edited
        this.useGradient = true; // Initialize with default gradient option
        this.isRelative = false; // Initialize with default relative option
        this.clipping = true; // Initialize with default clipping option
        this.formClipping = true; // Initialize form clipping option
        this.currentDistance = 5;
    }

    initialize() {
        this.initializeColormapWidget();
    }

    initializeColormapWidget() {
        const colormapSelect = document.getElementById('colormap-select');
        const datatypeSelect = document.getElementById('datatype-select'); // New data type select
        const colormapCanvas = document.getElementById('colormap-canvas');
        const addColormapButton = document.getElementById('add-colormap-button');
        const editColormapButton = document.getElementById('edit-colormap-button');
        const saveColormapButton = document.getElementById('save-colormap-button');
        const deleteColormapButton = document.getElementById('delete-colormap-button');
        const cancelColormapButton = document.getElementById('cancel-colormap-button');
        const colormapForm = document.getElementById('colormap-form');
        const colorList = document.getElementById('color-list');
        const addColorButton = document.getElementById('add-color-button');
        const useGradientButton = document.getElementById('use-gradient');
        const isRelativeButton = document.getElementById('is-relative');
        const clippingButton = document.getElementById('clipping');
        const formClippingCheckbox = document.getElementById('form-clipping');
        const distanceInput = document.getElementById('distance-input');

        if (distanceInput) {
            distanceInput.addEventListener('input', (e) => {
                this.currentDistance = parseFloat(e.target.value);
                this.emitColormapChanged(); // Re-emit the event with the new distance value
            });
        } else {
            console.error('Distance input element not found');
        }

        if (!colormapSelect || !datatypeSelect || !colormapCanvas || !addColormapButton || !editColormapButton || !saveColormapButton || !deleteColormapButton || !cancelColormapButton || !colormapForm || !colorList || !addColorButton || !useGradientButton || !isRelativeButton || !clippingButton || !formClippingCheckbox) {
            console.error('One or more elements are missing');
            return;
        }

        colormapSelect.addEventListener('change', async (e) => {
            this.currentColormap = e.target.value;
            console.log('Colormap selected:', this.currentColormap);
            await this.updateCheckBoxDefaults(this.currentColormap);
            this.drawColormap(colormapCanvas, this.currentColormap);
            this.emitColormapChanged();
        });

        distanceInput.addEventListener('input', (e) => {
            this.currentDistance = parseFloat(e.target.value);
            this.emitColormapChanged(); // Re-emit the event with the new distance value
        });

        datatypeSelect.addEventListener('change', (e) => {
            this.currentDatatype = e.target.value;
            console.log('Datatype selected:', this.currentDatatype);
            this.emitColormapChanged();
        });

        useGradientButton.addEventListener('click', () => {
            this.useGradient = !this.useGradient;
            this.updateButtonState(useGradientButton, this.useGradient);
            this.drawColormap(colormapCanvas, this.currentColormap);
            this.emitColormapChanged();
        });

        isRelativeButton.addEventListener('click', () => {
            this.isRelative = !this.isRelative;
            this.updateButtonState(isRelativeButton, this.isRelative);
            this.drawColormap(colormapCanvas, this.currentColormap);
            this.emitColormapChanged();
        });

        clippingButton.addEventListener('click', () => {
            this.clipping = !this.clipping;
            this.updateButtonState(clippingButton, this.clipping);
            this.drawColormap(colormapCanvas, this.currentColormap);
            this.emitColormapChanged();
        });

        formClippingCheckbox.addEventListener('change', () => {
            this.formClipping = formClippingCheckbox.checked;
        });

        addColormapButton.addEventListener('click', () => {
            this.clearForm();
            colormapForm.style.display = 'block';
            this.editingColormapId = null; // Reset editing mode
        });

        editColormapButton.addEventListener('click', this.loadSelectedColormap.bind(this));
        saveColormapButton.addEventListener('click', this.saveColormap.bind(this));
        deleteColormapButton.addEventListener('click', this.confirmDeleteColormap.bind(this));
        cancelColormapButton.addEventListener('click', () => {
            colormapForm.style.display = 'none';
        });
        addColorButton.addEventListener('click', this.addColorField.bind(this));

        this.loadColormaps();
    }

    async updateCheckBoxDefaults(colormap) {
        try {
            const response = await fetch(`/colormaps/${colormap}`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                }
            });
            const data = await response.json();
            this.useGradient = data.use_gradient;
            this.isRelative = data.is_relative;
            this.clipping = data.clipping; // Update clipping

            this.updateButtonState(document.getElementById('use-gradient'), this.useGradient);
            this.updateButtonState(document.getElementById('is-relative'), this.isRelative);
            this.updateButtonState(document.getElementById('clipping'), this.clipping);

            // Immediately update the colormap preview
            this.drawColormap(document.getElementById('colormap-canvas'), colormap);
            this.emitColormapChanged();
        } catch (error) {
            console.error('Error fetching colormap defaults:', error);
        }
    }

    drawColormap(canvas, colormap) {
        const ctx = canvas.getContext('2d');

        fetch(`/colormaps/${colormap}`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        })
            .then(response => response.json())
            .then(data => {
                if (!data.colors || !data.intervals) {
                    console.error('Invalid colormap data', data);
                    return;
                }

                const colors = data.colors;
                let intervals = data.intervals;

                const minInterval = Math.min(...intervals);
                const maxInterval = Math.max(...intervals);

                // Normalize intervals to fit the canvas width
                const normalizedIntervals = intervals.map(interval => (interval - minInterval) / (maxInterval - minInterval));

                ctx.clearRect(0, 0, canvas.width, canvas.height);

                const colormapHeight = canvas.height * 0.6; // Set the colormap height to 60% of the canvas height
                const tickAreaHeight = canvas.height - colormapHeight; // The remaining height is for ticks and labels

                // Draw the colormap
                if (this.useGradient) {
                    // Draw using gradients between colors
                    for (let i = 0; i < colors.length - 1; i++) {
                        const start = normalizedIntervals[i] * canvas.width;
                        const end = normalizedIntervals[i + 1] * canvas.width;
                        const gradient = ctx.createLinearGradient(start, 0, end, 0);

                        gradient.addColorStop(0, colors[i]);
                        gradient.addColorStop(1, colors[i + 1]);

                        ctx.fillStyle = gradient;
                        ctx.fillRect(start, 0, end - start, colormapHeight); // Draw only within the colormap height
                    }
                } else {
                    // Draw sharp color blocks
                    for (let i = 0; i < colors.length; i++) {
                        const start = normalizedIntervals[i] * canvas.width;
                        const end = i < colors.length - 1
                            ? normalizedIntervals[i + 1] * canvas.width
                            : canvas.width; // Ensure the last color block extends to the end of the canvas

                        ctx.fillStyle = colors[i];
                        ctx.fillRect(start, 0, end - start, colormapHeight); // Draw solid color block
                    }
                }

                // Add ticks and labels in the tick area
                ctx.fillStyle = 'black';
                ctx.font = '8px Arial';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'top';

                for (let i = 0; i < normalizedIntervals.length; i++) {
                    const x = normalizedIntervals[i] * canvas.width;
                    const tickYPosition = colormapHeight + tickAreaHeight * 0.2; // Adjust tick position below the colormap
                    const labelYPosition = colormapHeight + tickAreaHeight * 0.4; // Adjust label position below the ticks

                    // Draw ticks
                    ctx.beginPath();
                    ctx.moveTo(x, colormapHeight);
                    ctx.lineTo(x, tickYPosition);
                    ctx.stroke();

                    // Draw labels
                    const labelValue = this.isRelative
                        ? normalizedIntervals[i].toFixed(2)
                        : intervals[i].toFixed(2);
                    ctx.fillText(labelValue, x, labelYPosition);
                }
            })
            .catch(error => {
                console.error('Error drawing colormap:', error);
            });
    }

    loadColormaps() {
        fetch('/colormaps', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        })
            .then(response => response.json())
            .then(data => {
                const colormapSelect = document.getElementById('colormap-select');
                colormapSelect.innerHTML = ''; // Clear existing options
                data.forEach(colormap => {
                    const option = document.createElement('option');
                    option.value = colormap.name;
                    option.textContent = colormap.name;
                    option.dataset.id = colormap.id; // Store the id in the dataset
                    colormapSelect.appendChild(option);
                });
                this.updateCheckBoxDefaults(colormapSelect.value); // Set defaults for the initially selected colormap
                this.drawColormap(document.getElementById('colormap-canvas'), colormapSelect.value);
                this.emitColormapChanged(); // Emit initial event
            })
            .catch(error => {
                console.error('Error loading colormaps:', error);
            });
    }

    saveColormap() {
        const name = document.getElementById('colormap-name').value;
        const colors = Array.from(document.getElementsByClassName('color-input')).map(input => input.value);
        const intervals = Array.from(document.getElementsByClassName('interval-input')).map(input => parseFloat(input.value) || 0);
        const use_gradient = document.getElementById('form-use-gradient').checked;
        const is_relative = document.getElementById('form-is-relative').checked;
        const clipping = document.getElementById('form-clipping').checked; // Get form clipping value

        if (intervals.length !== colors.length) {
            alert('The number of intervals must match the number of colors');
            return;
        }

        const method = this.editingColormapId ? 'PUT' : 'POST';
        const url = this.editingColormapId ? `/colormaps/${this.editingColormapId}` : '/colormaps';

        fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({ name, colors, intervals, use_gradient, is_relative, clipping }) // Include clipping
        })
            .then(response => response.json())
            .then(data => {
                this.loadColormaps();
                document.getElementById('colormap-form').style.display = 'none';
                this.drawColormap(document.getElementById('colormap-canvas'), data.name); // Update the preview
            })
            .catch(error => {
                console.error('Error saving colormap:', error);
            });
    }

    loadSelectedColormap() {
        const colormapSelect = document.getElementById('colormap-select');
        const colormapName = colormapSelect.value;
        const selectedOption = colormapSelect.options[colormapSelect.selectedIndex];
        this.editingColormapId = selectedOption.dataset.id; // Store the id for editing

        fetch(`/colormaps/${colormapName}`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        })
            .then(response => response.json())
            .then(data => {
                this.clearForm();
                document.getElementById('colormap-name').value = data.name;
                data.colors.forEach((color, index) => {
                    const interval = data.intervals && index < data.intervals.length ? data.intervals[index] : 0;
                    this.addColorField(color, interval);
                });
                this.useGradient = data.use_gradient;
                this.isRelative = data.is_relative;
                this.formClipping = data.clipping; // Set form clipping

                document.getElementById('form-use-gradient').checked = this.useGradient;
                document.getElementById('form-is-relative').checked = this.isRelative;
                document.getElementById('form-clipping').checked = this.formClipping; // Set form clipping checkbox
                document.getElementById('colormap-form').style.display = 'block';
                this.updateColormapPreview(); // Update preview when loading a colormap
            })
            .catch(error => {
                console.error('Error loading colormap:', error);
            });
    }

    clearForm() {
        document.getElementById('colormap-name').value = '';
        document.getElementById('color-list').innerHTML = '';
        document.getElementById('form-use-gradient').checked = true;
        document.getElementById('form-is-relative').checked = false;
        document.getElementById('form-clipping').checked = true; // Reset form clipping
    }

    confirmDeleteColormap() {
        if (confirm('Are you sure you want to delete this colormap?')) {
            this.deleteColormap();
        }
    }

    deleteColormap() {
        const colormapSelect = document.getElementById('colormap-select');
        const colormapName = colormapSelect.value;
        const selectedOption = colormapSelect.options[colormapSelect.selectedIndex];
        const colormapId = selectedOption.dataset.id;

        fetch(`/colormaps/${colormapId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        })
            .then(response => {
                if (response.ok) {
                    this.loadColormaps();
                } else {
                    console.error('Error deleting colormap');
                }
            })
            .catch(error => {
                console.error('Error deleting colormap:', error);
            });
    }

    addColorField(color = '#000000', interval = 0) {
        const colorList = document.getElementById('color-list');
        const colorField = document.createElement('div');
        colorField.className = 'color-field';

        const colorInput = document.createElement('input');
        colorInput.type = 'color';
        colorInput.className = 'color-input';
        colorInput.value = color;

        const intervalInput = document.createElement('input');
        intervalInput.type = 'number';
        intervalInput.className = 'interval-input';
        intervalInput.step = '0.01';
        intervalInput.value = interval;
        intervalInput.placeholder = 'Interval';

        const deleteButton = document.createElement('button');
        deleteButton.className = 'icon-button';
        deleteButton.title = 'Delete Color';
        deleteButton.innerHTML = '<i class="fas fa-trash"></i>';
        deleteButton.addEventListener('click', () => {
            colorField.remove();
            this.updateColormapPreview(); // Update preview when deleting a color field
        });

        colorInput.addEventListener('input', this.updateColormapPreview.bind(this));
        intervalInput.addEventListener('input', this.updateColormapPreview.bind(this));

        colorField.appendChild(colorInput);
        colorField.appendChild(intervalInput);
        colorField.appendChild(deleteButton);

        colorList.appendChild(colorField);

        this.updateColormapPreview(); // Update preview when adding a new color field
    }

    updateColormapPreview() {
        const colors = Array.from(document.getElementsByClassName('color-input')).map(input => input.value);
        const canvas = document.getElementById('colormap-canvas');
        const ctx = canvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, canvas.width, 0);

        ctx.clearRect(0, 0, canvas.width, canvas.height); // Clear the canvas

        if (this.useGradient) {
            const step = 1 / (colors.length - 1);
            for (let i = 0; i < colors.length; i++) {
                if (isFinite(i * step)) {
                    gradient.addColorStop(i * step, colors[i]);
                } else {
                    console.error(`Non-finite interval value detected at index ${i}: ${i * step}`);
                }
            }
            ctx.fillStyle = gradient;
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        } else {
            const rectWidth = canvas.width / colors.length;
            for (let i = 0; i < colors.length; i++) {
                ctx.fillStyle = colors[i];
                ctx.fillRect(i * rectWidth, 0, rectWidth, canvas.height);
            }
        }

        // Emit colormap change with the current state
        this.emitColormapChanged();
    }

    updateButtonState(button, isActive) {
        button.dataset.state = isActive ? 'true' : 'false';
    }

    emitColormapChanged() {
        this.eventEmitter.emit('colormapChanged', this.currentColormap, this.isRelative, this.clipping, this.currentDatatype, this.currentDistance, this.useGradient);
    }
}

export default ColormapWidget;
