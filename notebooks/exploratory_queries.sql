-- ============================================================================
-- Sprint 1, Day 07 — Exploratory Queries
-- Run against: data/nifty100.db
-- Usage: sqlite3 data/nifty100.db < notebooks/exploratory_queries.sql
-- ============================================================================

-- 1. Row counts across all 12 tables
SELECT 'companies' AS table_name, COUNT(*) AS row_count FROM companies
UNION ALL SELECT 'profitandloss', COUNT(*) FROM profitandloss
UNION ALL SELECT 'balancesheet', COUNT(*) FROM balancesheet
UNION ALL SELECT 'cashflow', COUNT(*) FROM cashflow
UNION ALL SELECT 'analysis', COUNT(*) FROM analysis
UNION ALL SELECT 'documents', COUNT(*) FROM documents
UNION ALL SELECT 'prosandcons', COUNT(*) FROM prosandcons
UNION ALL SELECT 'sectors', COUNT(*) FROM sectors
UNION ALL SELECT 'stock_prices', COUNT(*) FROM stock_prices
UNION ALL SELECT 'market_cap', COUNT(*) FROM market_cap
UNION ALL SELECT 'financial_ratios', COUNT(*) FROM financial_ratios
UNION ALL SELECT 'peer_groups', COUNT(*) FROM peer_groups;

-- 2. Null / completeness audit for critical P&L columns
SELECT
    COUNT(*)                                       AS total_rows,
    SUM(CASE WHEN sales IS NULL THEN 1 ELSE 0 END)        AS null_sales,
    SUM(CASE WHEN net_profit IS NULL THEN 1 ELSE 0 END)   AS null_net_profit,
    SUM(CASE WHEN eps IS NULL THEN 1 ELSE 0 END)          AS null_eps
FROM profitandloss;

-- 3. Year coverage per company (min year, max year, distinct year count)
SELECT company_id,
       MIN(year) AS first_year,
       MAX(year) AS last_year,
       COUNT(DISTINCT year) AS n_years
FROM profitandloss
GROUP BY company_id
ORDER BY n_years ASC
LIMIT 15;   -- companies with the SHORTEST history first (coverage risk)

-- 4. Companies with fewer than 5 years of P&L history (ties to DQ-16)
SELECT company_id, COUNT(DISTINCT year) AS n_years
FROM profitandloss
GROUP BY company_id
HAVING COUNT(DISTINCT year) < 5
ORDER BY n_years ASC;

-- 5. Sector distribution — company count per broad_sector
SELECT broad_sector, COUNT(*) AS n_companies
FROM sectors
GROUP BY broad_sector
ORDER BY n_companies DESC;

-- 6. P&L + Balance Sheet join for a single fiscal year (FY24, all companies)
SELECT p.company_id, p.year, p.sales, p.net_profit,
       b.borrowings, b.total_assets
FROM profitandloss p
JOIN balancesheet b USING (company_id, year)
WHERE p.year = '2024-03'
ORDER BY p.sales DESC
LIMIT 15;

-- 7. Full company profile with sector (Section 7.3 standard join pattern)
SELECT c.id, c.company_name, s.broad_sector, s.sub_sector, s.market_cap_category
FROM companies c
JOIN sectors s ON c.id = s.company_id
ORDER BY c.company_name
LIMIT 15;

-- 8. CFO vs Net Profit health check — flag companies where CFO went negative
--    in the latest available year while net_profit stayed positive
--    (quality-of-earnings red flag)
SELECT p.company_id, p.year, p.net_profit, f.operating_activity
FROM profitandloss p
JOIN cashflow f USING (company_id, year)
WHERE p.net_profit > 0 AND f.operating_activity < 0
ORDER BY p.year DESC;

-- 9. Debt-free companies (borrowings = 0) in the most recent fiscal year
--    available per company
WITH latest_bs AS (
    SELECT company_id, MAX(year) AS latest_year
    FROM balancesheet
    WHERE year LIKE '%-03'   -- restrict to standard March-end FY rows
    GROUP BY company_id
)
SELECT b.company_id, b.year, b.borrowings, b.reserves
FROM balancesheet b
JOIN latest_bs lb ON b.company_id = lb.company_id AND b.year = lb.latest_year
WHERE b.borrowings = 0
ORDER BY b.company_id;

-- 10. Peer group ranking — ROE rank within each peer group, using each
--     company's own most recent available financial_ratios year (source
--     data has sparse/uneven year coverage across companies, so a single
--     global "latest year" filter would drop most peer members; Sprint 2's
--     Ratio Engine will populate this table more completely for all 92
--     companies x all years).
WITH latest_ratio AS (
    SELECT company_id, MAX(year) AS latest_year
    FROM financial_ratios
    GROUP BY company_id
)
SELECT pg.peer_group_name, r.company_id, r.year, r.return_on_equity_pct,
       RANK() OVER (
           PARTITION BY pg.peer_group_name
           ORDER BY r.return_on_equity_pct DESC
       ) AS roe_rank_in_group
FROM financial_ratios r
JOIN latest_ratio lr ON r.company_id = lr.company_id AND r.year = lr.latest_year
JOIN peer_groups pg USING (company_id)
ORDER BY pg.peer_group_name, roe_rank_in_group;
