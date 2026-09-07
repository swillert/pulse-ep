# Native MATLAB toolbox integration

These tests require an installed toolbox, base MATLAB and a disposable
PostgreSQL-backed pulse-ep server. They use only public synthetic inputs.
They are separate from the Python test suite and must be run explicitly.

1. Build the installer with `examples/matlab/build_toolbox.m` (R2023a+).
2. Initialize an empty disposable database with `pulse-ep-init`. Configure a
   test administrator, waveform store, reports/drop directories, JWT secret
   and a loopback server address. Keep all settings in an isolated environment.
3. Set `PULSE_EP_TEST_DATABASE=1` and `PULSE_EP_TEST_CONFIG` to a temporary
   JSON path. Run `python tests/matlab/seed_test_database.py` in that environment.
   It refuses a nonempty database. Start the server with the same settings.
4. Pass `PULSE_EP_BASE_URL`, `PULSE_EP_USERNAME`, `PULSE_EP_PASSWORD` and
   `PULSE_EP_TEST_CONFIG` to MATLAB. Install the `.mltbx`, then run from a
   directory outside the source checkout without its MATLAB folder on the path:

```matlab
results = runtests('/path/to/pulse-ep/tests/matlab/test_client.m');
assertSuccess(results);
```

Verify that `which('pulseep.Client')` and `which('pe_load_map')` resolve into
the installed toolbox. Preserve the results and installer hash; uninstall
the temporary test installation and remove its server, database, waveform
store and runtime configuration afterward. Do not replace an existing user
installation just to run a test.

The checks cover login/logout, expired credentials, transient tokens, stable
study/map tables, component selection, raw/direct-function parity, CARTO and
EnSite meshes, point-only maps, paging, Parquet samples, OpenEP conversion and
server area calculations. Actual OpenEP analysis routines are tested by the
separate OpenEP compatibility protocol; they are not bundled in this toolbox.
