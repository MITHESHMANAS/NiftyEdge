-- ============================================================================
-- N100 Financial Intelligence Platform — SQLite Schema
-- Module 1: Data Ingestion & ETL (Sprint 1)
-- 12 tables — one per source dataset (7 core + 5 supplementary)
-- All monetary columns are in INR Crore unless noted.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 1. companies — Master company reference (PK: id = NSE ticker)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS companies;
CREATE TABLE companies (
    id                  TEXT PRIMARY KEY,      -- NSE ticker, normalised uppercase
    company_logo        TEXT,
    company_name        TEXT NOT NULL,
    chart_link          TEXT,
    about_company       TEXT,
    website              TEXT,
    nse_profile         TEXT,
    bse_profile         TEXT,
    face_value          REAL,
    book_value          REAL,
    roce_percentage     REAL,
    roe_percentage      REAL
);

-- ----------------------------------------------------------------------------
-- 2. profitandloss — Annual P&L statements. PK: (company_id, year)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS profitandloss;
CREATE TABLE profitandloss (
    id                  INTEGER,               -- source row id (not unique across files, informational only)
    company_id          TEXT NOT NULL,
    year                TEXT NOT NULL,          -- normalised YYYY-MM
    sales               REAL,
    expenses            REAL,
    operating_profit    REAL,
    opm_percentage      REAL,
    other_income        REAL,
    interest            REAL,
    depreciation        REAL,
    profit_before_tax   REAL,
    tax_percentage      REAL,
    net_profit          REAL,
    eps                 REAL,
    dividend_payout     REAL,
    PRIMARY KEY (company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- ----------------------------------------------------------------------------
-- 3. balancesheet — Annual balance sheet. PK: (company_id, year)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS balancesheet;
CREATE TABLE balancesheet (
    id                  INTEGER,
    company_id          TEXT NOT NULL,
    year                TEXT NOT NULL,
    equity_capital       REAL,
    reserves            REAL,
    borrowings          REAL,
    other_liabilities   REAL,
    total_liabilities   REAL,
    fixed_assets        REAL,
    cwip                REAL,
    investments         REAL,
    other_asset         REAL,
    total_assets        REAL,
    PRIMARY KEY (company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- ----------------------------------------------------------------------------
-- 4. cashflow — Annual cash flow statement. PK: (company_id, year)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS cashflow;
CREATE TABLE cashflow (
    id                  INTEGER,
    company_id          TEXT NOT NULL,
    year                TEXT NOT NULL,
    operating_activity  REAL,
    investing_activity  REAL,
    financing_activity  REAL,
    net_cash_flow       REAL,
    PRIMARY KEY (company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- ----------------------------------------------------------------------------
-- 5. analysis — Pre-computed growth metrics, text-encoded. PK: company_id
--    (only ~8/92 companies covered; used for display cross-check only)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS analysis;
CREATE TABLE analysis (
    id                          INTEGER,
    company_id                  TEXT NOT NULL,
    compounded_sales_growth_raw TEXT,
    compounded_profit_growth_raw TEXT,
    stock_price_cagr_raw        TEXT,
    roe_raw                     TEXT,
    -- parsed numeric values (period_years, pct_value) extracted via regex
    compounded_sales_growth_years REAL,
    compounded_sales_growth_pct   REAL,
    compounded_profit_growth_years REAL,
    compounded_profit_growth_pct   REAL,
    stock_price_cagr_years        REAL,
    stock_price_cagr_pct          REAL,
    roe_years                     REAL,
    roe_pct                       REAL,
    PRIMARY KEY (company_id),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- ----------------------------------------------------------------------------
-- 6. documents — Annual report URL repository. PK: (company_id, year, id)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS documents;
CREATE TABLE documents (
    id                  INTEGER,
    company_id          TEXT NOT NULL,
    year                INTEGER NOT NULL,
    annual_report_url   TEXT,
    url_status_code     INTEGER,               -- populated by URL validator (DQ-13); NULL until checked
    PRIMARY KEY (company_id, year, id),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- ----------------------------------------------------------------------------
-- 7. prosandcons — Qualitative pros/cons notes. Multiple rows per company.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS prosandcons;
CREATE TABLE prosandcons (
    id                  INTEGER PRIMARY KEY,
    company_id          TEXT NOT NULL,
    pros                TEXT,
    cons                TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- ----------------------------------------------------------------------------
-- 8. sectors — Sector / sub-sector mapping. PK: company_id (1 row per company)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS sectors;
CREATE TABLE sectors (
    id                  INTEGER,
    company_id          TEXT NOT NULL,
    broad_sector        TEXT NOT NULL,
    sub_sector          TEXT,
    index_weight_pct    REAL,
    market_cap_category TEXT,
    PRIMARY KEY (company_id),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- ----------------------------------------------------------------------------
-- 9. stock_prices — Monthly OHLCV. PK: (company_id, date)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS stock_prices;
CREATE TABLE stock_prices (
    id                  INTEGER,
    company_id          TEXT NOT NULL,
    date                TEXT NOT NULL,          -- YYYY-MM-DD
    open_price          REAL,
    high_price          REAL,
    low_price           REAL,
    close_price         REAL,
    volume              INTEGER,
    adjusted_close       REAL,
    PRIMARY KEY (company_id, date),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- ----------------------------------------------------------------------------
-- 10. market_cap — Annual valuation multiples. PK: (company_id, year)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS market_cap;
CREATE TABLE market_cap (
    id                      INTEGER,
    company_id              TEXT NOT NULL,
    year                    INTEGER NOT NULL,
    market_cap_crore        REAL,
    enterprise_value_crore  REAL,
    pe_ratio                REAL,
    pb_ratio                REAL,
    ev_ebitda               REAL,
    dividend_yield_pct      REAL,
    PRIMARY KEY (company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- ----------------------------------------------------------------------------
-- 11. financial_ratios — Computed KPI table.
--     Sprint 1 loads financial_ratios.xlsx as-is (13 raw columns) for the
--     initial ETL. Sprint 2's Ratio Engine (src/analytics/) recomputes
--     every row from raw P&L/BS/CF and OVERWRITES this table with the full
--     50+ KPI set below. PK: (company_id, year)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS financial_ratios;
CREATE TABLE financial_ratios (
    id                              INTEGER,
    company_id                      TEXT NOT NULL,
    year                            TEXT NOT NULL,

    -- Profitability (Sprint 2, Day 08)
    net_profit_margin_pct           REAL,
    operating_profit_margin_pct     REAL,
    opm_cross_check_mismatch        INTEGER,   -- 0/1: |computed - source opm_percentage| > 1pp
    return_on_equity_pct            REAL,
    return_on_capital_employed_pct  REAL,
    return_on_assets_pct            REAL,

    -- Leverage & efficiency (Sprint 2, Day 09)
    debt_to_equity                  REAL,
    high_leverage_flag              INTEGER,   -- 0/1: D/E > 5 and non-Financials sector
    interest_coverage               REAL,
    icr_label                       TEXT,      -- 'Debt Free' when interest = 0
    icr_risk_flag                   INTEGER,   -- 0/1: ICR < 1.5
    net_debt_cr                     REAL,      -- borrowings - investments
    asset_turnover                  REAL,

    -- CAGR engine (Sprint 2, Day 10) — 3/5/10yr windows + edge-case flag
    revenue_cagr_3yr                REAL,
    revenue_cagr_5yr                REAL,
    revenue_cagr_10yr               REAL,
    revenue_cagr_5yr_flag           TEXT,      -- NULL | DECLINE_TO_LOSS | TURNAROUND | BOTH_NEGATIVE | ZERO_BASE | INSUFFICIENT
    pat_cagr_3yr                    REAL,
    pat_cagr_5yr                    REAL,
    pat_cagr_10yr                   REAL,
    pat_cagr_5yr_flag               TEXT,
    eps_cagr_3yr                    REAL,
    eps_cagr_5yr                    REAL,
    eps_cagr_10yr                   REAL,
    eps_cagr_5yr_flag               TEXT,

    -- Cash flow KPIs & capital allocation (Sprint 2, Day 11)
    free_cash_flow_cr               REAL,
    capex_cr                        REAL,
    capex_intensity_pct             REAL,
    capex_intensity_label           TEXT,      -- Asset Light | Moderate | Capital Intensive
    fcf_conversion_rate_pct         REAL,
    cfo_quality_score               REAL,      -- 5yr avg CFO/PAT
    cfo_quality_label                TEXT,      -- High Quality | Moderate | Accrual Risk
    capital_allocation_pattern      TEXT,      -- 8-pattern classifier label

    -- Pass-through / source-derived fields
    earnings_per_share              REAL,
    book_value_per_share            REAL,
    dividend_payout_ratio_pct       REAL,
    total_debt_cr                   REAL,
    cash_from_operations_cr         REAL,

    -- Composite (Sprint 2 provisional; refined into the 0-100 health score
    -- in Sprint 3)
    composite_quality_score         REAL,

    PRIMARY KEY (company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- ----------------------------------------------------------------------------
-- 12. peer_groups — Peer comparison group membership. M:N company<->group.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS peer_groups;
CREATE TABLE peer_groups (
    id                  INTEGER PRIMARY KEY,
    peer_group_name     TEXT NOT NULL,
    company_id          TEXT NOT NULL,
    is_benchmark        INTEGER NOT NULL DEFAULT 0,  -- 0/1 boolean
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- ----------------------------------------------------------------------------
-- 13. peer_percentiles — Sprint 3, Day 18. Percentile rank (0-1) for each
--     of 10 metrics, computed within each peer group. D/E is inverted
--     (lower D/E -> higher percentile). One row per (company, metric).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS peer_percentiles;
CREATE TABLE peer_percentiles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id       TEXT NOT NULL,
    peer_group_name  TEXT NOT NULL,
    metric           TEXT NOT NULL,
    value            REAL,
    percentile_rank  REAL,
    year             TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- ----------------------------------------------------------------------------
-- Indexes to support common join / filter patterns
-- ----------------------------------------------------------------------------
CREATE INDEX idx_pnl_company        ON profitandloss(company_id);
CREATE INDEX idx_bs_company         ON balancesheet(company_id);
CREATE INDEX idx_cf_company         ON cashflow(company_id);
CREATE INDEX idx_docs_company       ON documents(company_id);
CREATE INDEX idx_pros_company       ON prosandcons(company_id);
CREATE INDEX idx_prices_company     ON stock_prices(company_id);
CREATE INDEX idx_mktcap_company     ON market_cap(company_id);
CREATE INDEX idx_ratios_company     ON financial_ratios(company_id);
CREATE INDEX idx_peer_company       ON peer_groups(company_id);
CREATE INDEX idx_peer_group_name    ON peer_groups(peer_group_name);
CREATE INDEX idx_peer_pct_company   ON peer_percentiles(company_id);
CREATE INDEX idx_peer_pct_group     ON peer_percentiles(peer_group_name);
CREATE INDEX idx_sectors_broad      ON sectors(broad_sector);
