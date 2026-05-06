-- GridWar — Supabase Schema
-- Run this in your Supabase SQL Editor

-- 1. Grid Cells Table
CREATE TABLE IF NOT EXISTS grid_cells (
    cell_id      INTEGER PRIMARY KEY,
    owner_id     TEXT NOT NULL,
    owner_name   TEXT NOT NULL,
    color        TEXT NOT NULL,
    captured_at  DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_grid_cells_owner ON grid_cells(owner_id);


-- 2. User Scores Table
CREATE TABLE IF NOT EXISTS user_scores (
    user_id    TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    color      TEXT NOT NULL,
    score      INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON user_scores
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();


-- RLS (backend uses service_role so this won't block it)
ALTER TABLE grid_cells  ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_scores ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all_grid"  ON grid_cells  FOR ALL USING (true);
CREATE POLICY "service_role_all_users" ON user_scores FOR ALL USING (true);

-- To reset the grid:
-- DELETE FROM grid_cells;
-- DELETE FROM user_scores;
