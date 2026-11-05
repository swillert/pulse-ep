-- Bring a pulse-ep database that predates the Alembic migrations (created by
-- Base.metadata.create_all() before July 2026, no alembic_version table) to the
-- schema of release 0.6.0 (revision a1c3e5f70b92).
--
-- Since the fix in `pulse-ep-migrate` (adopts such databases automatically) this
-- file is the same upgrade as plain SQL, for installations without Python at hand.
-- Before that fix `pulse-ep-migrate` could not do this itself: its initial revision 0e7e3563b7fb
-- creates the tables and fails with "relation already exists" on such a
-- database. This script adds what the initial revision would add to the legacy
-- tables, stamps the baseline revision and then applies every later revision
-- exactly as `pulse-ep-migrate --sql` prints it. Additive only; no data is
-- touched. Run as the owner of the tables (normally the application user), e.g.
--     psql "$PULSE_EP_DATABASE_URL" -f tools/upgrade_legacy_database.sql
-- Applied to the Kiel study database on 2026-11-05.
BEGIN;
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num));
ALTER TABLE studies ADD COLUMN vendor VARCHAR;
ALTER TABLE studies ADD COLUMN provenance JSONB;
CREATE INDEX IF NOT EXISTS ix_studies_id ON studies (id);
CREATE INDEX IF NOT EXISTS ix_studies_vendor ON studies (vendor);
ALTER TABLE epmaps ADD COLUMN scalar_fields JSONB;
INSERT INTO alembic_version (version_num) VALUES ('0e7e3563b7fb');

CREATE TABLE waveforms (
    id SERIAL NOT NULL, 
    study_id INTEGER, 
    map_id INTEGER, 
    signal_type VARCHAR, 
    channels JSONB, 
    sample_rate FLOAT, 
    n_samples INTEGER, 
    n_channels INTEGER, 
    segment VARCHAR, 
    filters JSONB, 
    data_uri VARCHAR NOT NULL, 
    data_format VARCHAR, 
    size_bytes INTEGER, 
    checksum VARCHAR, 
    source VARCHAR, 
    PRIMARY KEY (id), 
    FOREIGN KEY(map_id) REFERENCES epmaps (id) ON DELETE CASCADE, 
    FOREIGN KEY(study_id) REFERENCES studies (id) ON DELETE CASCADE
);

CREATE INDEX ix_waveforms_id ON waveforms (id);

CREATE INDEX ix_waveforms_map_id ON waveforms (map_id);

CREATE INDEX ix_waveforms_study_id ON waveforms (study_id);

UPDATE alembic_version SET version_num='61863fd599e4' WHERE alembic_version.version_num = '0e7e3563b7fb';

CREATE TABLE measurement_points (
    id SERIAL NOT NULL, 
    map_id INTEGER NOT NULL, 
    point_index INTEGER, 
    source_id VARCHAR, 
    position FLOAT[], 
    measurements JSONB, 
    electrodes JSONB, 
    PRIMARY KEY (id), 
    FOREIGN KEY(map_id) REFERENCES epmaps (id) ON DELETE CASCADE
);

CREATE INDEX ix_measurement_points_id ON measurement_points (id);

CREATE INDEX ix_measurement_points_map_id ON measurement_points (map_id);

CREATE INDEX ix_measurement_points_map_point ON measurement_points (map_id, point_index);

UPDATE alembic_version SET version_num='cc7318c9c1de' WHERE alembic_version.version_num = '61863fd599e4';

CREATE TABLE placed_points (
    id SERIAL NOT NULL, 
    study_id INTEGER NOT NULL, 
    type VARCHAR, 
    position FLOAT[], 
    label VARCHAR, 
    attributes JSONB, 
    source_id VARCHAR, 
    PRIMARY KEY (id), 
    FOREIGN KEY(study_id) REFERENCES studies (id) ON DELETE CASCADE
);

CREATE INDEX ix_placed_points_id ON placed_points (id);

CREATE INDEX ix_placed_points_study_id ON placed_points (study_id);

CREATE INDEX ix_placed_points_type ON placed_points (type);

UPDATE alembic_version SET version_num='6f7abb350e3b' WHERE alembic_version.version_num = 'cc7318c9c1de';

CREATE TABLE import_jobs (
    id SERIAL NOT NULL, 
    source_path VARCHAR NOT NULL, 
    vendor VARCHAR, 
    status VARCHAR NOT NULL, 
    plan JSONB, 
    study_id INTEGER, 
    error VARCHAR, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id)
);

CREATE INDEX ix_import_jobs_id ON import_jobs (id);

CREATE INDEX ix_import_jobs_status ON import_jobs (status);

UPDATE alembic_version SET version_num='0c2994f1da5b' WHERE alembic_version.version_num = '6f7abb350e3b';

ALTER TABLE waveforms ADD COLUMN point_source_id VARCHAR;

CREATE INDEX ix_waveforms_point_source_id ON waveforms (point_source_id);

UPDATE alembic_version SET version_num='b4f1a7c2d9e3' WHERE alembic_version.version_num = '0c2994f1da5b';

ALTER TABLE measurement_points ADD COLUMN tags JSONB;

UPDATE alembic_version SET version_num='d7e2c4a9f1b6' WHERE alembic_version.version_num = 'b4f1a7c2d9e3';

ALTER TABLE measurement_points ADD COLUMN annotations JSONB;

UPDATE alembic_version SET version_num='f3a8b5c6d201' WHERE alembic_version.version_num = 'd7e2c4a9f1b6';

ALTER TABLE waveforms ADD COLUMN units JSONB;

UPDATE alembic_version SET version_num='a1c3e5f70b92' WHERE alembic_version.version_num = 'f3a8b5c6d201';

COMMIT;

