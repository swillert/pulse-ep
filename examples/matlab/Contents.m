% pulse-ep MATLAB — REST access to electroanatomical mapping studies.
%
% Session convenience
%   pulseep.Client              - Server and transient login session.
%
% Direct functions (also used by Client)
%   pe_login                    - Obtain a bearer token.
%   pe_list_studies              - Study metadata.
%   pe_list_maps                 - Maps in a study.
%   pe_map_scalars               - Available fields, units and ranges.
%   pe_load_map                  - Stored data with selectable components.
%   pe_get_mesh                  - Raw/display mesh and MATLAB plotting arrays.
%   pe_list_points               - Paged point measurements and annotations.
%   pe_list_waveforms            - Signal metadata and download links.
%   pe_download_waveform         - Download Parquet samples.
%   pe_areas_per_interval        - Server-side interval area calculation.
%   pe_to_openep                 - OpenEP userdata with optional signals/RF tags.
%   pe_openep_conduction_velocity - OpenEP with physical LAT and common origin.
%   pe_openep_ablation_area      - OpenEP RF coverage including small selections.
%
% Examples
%   toolbox_demo                - Login, select and load through Client.
%   pulse_ep_demo               - Plot a mesh with the direct functions.
%   openep_demo                 - Native OpenEP mesh/voltage analyses.
%   openep_signal_demo          - Point-linked signals through OpenEP.
