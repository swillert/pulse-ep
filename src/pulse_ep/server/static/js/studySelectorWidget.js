import { EventEmitter } from './eventEmitter.js';

class StudySelectorWidget {
    constructor(eventEmitter) {
        this.eventEmitter = eventEmitter;
        this.studies = {}; // Store studies information
    }

    initialize() {
        this.loadStudies();
    }

    loadStudies() {
        const studiesList = document.getElementById('studiesList');
        const epmapsList = document.getElementById('epmapsList');
        const searchInput = document.getElementById('searchInput');
        const token = localStorage.getItem('token');

        if (!token) {
            window.location.href = '/login';
            return;
        }

        fetch('/list_studies', {
            headers: { 'Authorization': `Bearer ${token}` }
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to fetch studies: ' + response.statusText);
                }
                return response.json();
            })
            .then(studies => {
                console.log('Studies loaded:', studies);
                this.studies = studies.reduce((acc, study) => {
                    acc[study.id] = study.study_name;
                    return acc;
                }, {});
                const allStudies = studies;
                studiesList.innerHTML = '';
                this.displayStudies(allStudies);

                searchInput.addEventListener('input', () => {
                    const filter = searchInput.value.toLowerCase();
                    const filteredStudies = allStudies.filter(study =>
                        study.study_name.toLowerCase().includes(filter)
                    );
                    this.displayStudies(filteredStudies);
                });
            })
            .catch(error => {
                console.error('Error loading studies:', error);
            });
    }

    displayStudies(studies) {
        const studiesList = document.getElementById('studiesList');
        const epmapsList  = document.getElementById('epmapsList');
        studiesList.innerHTML = '';
        studies.forEach((study) => {
            const li = document.createElement('li');
            li.className = 'sidebar-item';
            li.innerHTML = `<i class="fas fa-folder"></i> ${study.study_name}`;
            li.onclick = () => {
                document.querySelectorAll('#studiesList .sidebar-item').forEach(el => el.classList.remove('active'));
                li.classList.add('active');
                epmapsList.innerHTML = '';
                this.loadEpMaps(study.id, study.study_name);
            };
            studiesList.appendChild(li);
        });
    }

    loadEpMaps(studyId, studyName) {
        const epmapsList = document.getElementById('epmapsList');
        const token = localStorage.getItem('token');

        fetch(`/list_epmaps_in_study/${studyId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to fetch EPMaps: ' + response.statusText);
                }
                return response.json();
            })
            .then(epmaps => {
                console.log('EPMaps loaded for study', studyId, ':', epmaps);
                epmapsList.innerHTML = '';
                epmaps.forEach((epmap) => {
                    const li = document.createElement('li');
                    li.className = 'sidebar-item';
                    li.innerHTML = `<i class="fas fa-heart"></i> ${epmap.map_name}`;
                    li.onclick = () => {
                        document.querySelectorAll('#epmapsList .sidebar-item').forEach(el => el.classList.remove('active'));
                        li.classList.add('active');
                        this.eventEmitter.emit('loadMesh', epmap.id, epmap.map_name, studyName);
                    };
                    epmapsList.appendChild(li);
                });
            })
            .catch(error => {
                console.error('Error loading EPMaps:', error);
            });
    }
}

export default StudySelectorWidget;
