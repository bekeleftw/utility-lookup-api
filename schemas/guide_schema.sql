-- Resident Guide Feature - Database Schema
-- Run this migration against your PostgreSQL database

-- Table: guide_requests
-- Tracks PM requests for resident guides
CREATE TABLE IF NOT EXISTS guide_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    address TEXT NOT NULL,
    address_components JSONB,  -- {street, city, state, zip}
    utility_results JSONB NOT NULL,  -- Copy of lookup results at time of request
    email TEXT NOT NULL,
    company_name TEXT NOT NULL,
    website TEXT,  -- Optional, PM's website for logo scraping
    logo_url TEXT,  -- URL to stored logo (after retrieval)
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    emailed_at TIMESTAMP WITH TIME ZONE
);

-- Table: guide_outputs
-- Stores generated PDFs and shareable links
CREATE TABLE IF NOT EXISTS guide_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guide_request_id UUID NOT NULL REFERENCES guide_requests(id) ON DELETE CASCADE,
    short_code TEXT NOT NULL UNIQUE,  -- 8 chars for shareable URL
    pdf_url TEXT NOT NULL,  -- URL to stored PDF
    guide_data JSONB NOT NULL,  -- Full compiled guide content
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table: utility_instructions_cache
-- Caches AI-extracted signup instructions (90-day TTL)
CREATE TABLE IF NOT EXISTS utility_instructions_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    utility_id TEXT NOT NULL,  -- Your existing utility identifier
    utility_name TEXT NOT NULL,
    utility_type TEXT NOT NULL,  -- electric, gas, water, internet
    instructions JSONB NOT NULL,  -- Extracted/generated instructions
    source_urls TEXT[],  -- URLs that were scraped
    is_generic BOOLEAN DEFAULT FALSE,  -- True if using fallback template
    extraction_method TEXT NOT NULL,  -- ai, fallback, manual
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '90 days'),
    UNIQUE(utility_id, utility_type)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_guide_requests_status ON guide_requests(status);
CREATE INDEX IF NOT EXISTS idx_guide_requests_email ON guide_requests(email);
CREATE INDEX IF NOT EXISTS idx_guide_requests_created_at ON guide_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_guide_outputs_short_code ON guide_outputs(short_code);
CREATE INDEX IF NOT EXISTS idx_utility_instructions_cache_lookup ON utility_instructions_cache(utility_id, utility_type);
CREATE INDEX IF NOT EXISTS idx_utility_instructions_cache_expires ON utility_instructions_cache(expires_at);

-- Function to clean up expired cache entries (run periodically)
CREATE OR REPLACE FUNCTION cleanup_expired_instructions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM utility_instructions_cache WHERE expires_at < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
