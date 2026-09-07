% OPENEP_SIGNAL_DEMO Fetch stored signals over REST and read them with OpenEP.
% Requires OpenEP on the MATLAB path and PULSE_EP_BASE_URL,
% PULSE_EP_USERNAME, PULSE_EP_PASSWORD and PE_MAP_ID in the environment.
% The selected map must have been imported with waveform storage enabled.
baseURL = getenv('PULSE_EP_BASE_URL');
if isempty(baseURL); baseURL = 'http://127.0.0.1:5000'; end
username = getenv('PULSE_EP_USERNAME');
password = getenv('PULSE_EP_PASSWORD');
mapId = str2double(getenv('PE_MAP_ID'));
if isempty(username) || isempty(password) || ~isfinite(mapId)
    error('Set PULSE_EP_USERNAME, PULSE_EP_PASSWORD and PE_MAP_ID.');
end
token = pe_login(baseURL, username, password);
userdata = pe_to_openep(baseURL, token, mapId, true, 'IncludeSignals', true);
if ~isfield(userdata.electric, 'egm')
    error('This map has no point-linked electrograms; check import options and userdata.notes.');
end
pointIndex = find(any(isfinite(userdata.electric.egm), 2), 1);
if isempty(pointIndex); error('No finite bipolar electrogram is available.'); end

% This is the actual OpenEP accessor. Quantitative reference data are read
% directly below because that accessor scales reference traces for display.
[traces, ~, names] = getEgmsAtPoints(userdata, 'iegm', pointIndex, ...
                                  'egmtype', 'bip', 'reference', 'off');
n = userdata.pulse_ep.signals.sample_counts(pointIndex);
time_ms = (0:n-1) / userdata.electric.sampleFrequency * 1000;
figure;
tiledlayout(3, 1);
nexttile; plot(time_ms, traces{1}(1:n));
ylabel(local_unit(userdata.pulse_ep.signals.units.bipolar, pointIndex));
title(['Bipolar electrogram: ' char(names{1})], 'Interpreter', 'none');
nexttile; plot(time_ms, squeeze(userdata.electric.egmUni(pointIndex,1:n,:)));
ylabel(local_unit(userdata.pulse_ep.signals.units.unipolar_1, pointIndex));
legend('Unipole 1', 'Unipole 2'); title('Unipolar electrograms');
nexttile; plot(time_ms, userdata.electric.egmRef(pointIndex,1:n));
ylabel(local_unit(userdata.pulse_ep.signals.units.reference, pointIndex));
title('Reference signal, stored amplitude'); xlabel('Time from first sample (ms)');

fprintf('%d points with bipolar signals; %.0f Hz; selected point %d has %d samples.\n', ...
        userdata.pulse_ep.signals.points_with_bipolar, ...
        userdata.electric.sampleFrequency, pointIndex, n);

function label = local_unit(units, index)
    units = string(units);
    unit = units(index);
    if strlength(unit) == 0 || unit == "unknown"
        label = 'Amplitude (unit unspecified)';
    else
        label = ['Amplitude (' char(unit) ')'];
    end
end
