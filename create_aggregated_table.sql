-- Phase 1: Create pre-aggregated table in SQLite
-- This eliminates N+1 queries by grouping all providers per block_geoid into JSON
-- Run with: sqlite3 bdc_internet_new.db < create_aggregated_table.sql

-- Drop if exists (for re-runs)
DROP TABLE IF EXISTS block_providers_agg;

-- Create aggregated table with JSON providers array per block
-- Only includes fiber/cable technologies: 10, 40, 41, 42, 43, 50
CREATE TABLE block_providers_agg AS
SELECT 
    block_geoid,
    json_group_array(
        json_object(
            'name', provider_name,
            'tech', technology,
            'down', max_down,
            'up', max_up,
            'low_lat', low_latency
        )
    ) AS providers_json
FROM (
    SELECT 
        block_geoid,
        provider_name,
        technology,
        MAX(max_down) as max_down,
        MAX(max_up) as max_up,
        MAX(low_latency) as low_latency
    FROM providers
    WHERE technology IN ('10', '40', '41', '42', '43', '50')
    GROUP BY block_geoid, provider_name, technology
)
GROUP BY block_geoid
ORDER BY block_geoid;

-- Create index for efficient streaming with checkpoint resume
CREATE INDEX idx_block_geoid ON block_providers_agg(block_geoid);

-- Verify
SELECT COUNT(*) as total_blocks FROM block_providers_agg;
SELECT * FROM block_providers_agg LIMIT 3;
