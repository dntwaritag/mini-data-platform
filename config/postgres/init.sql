-- Mini Data Platform — PostgreSQL bootstrap
-- Runs automatically on first container start (docker-entrypoint-initdb.d).

CREATE SCHEMA IF NOT EXISTS analytics;

COMMENT ON SCHEMA analytics IS 'Cleaned and transformed data for the Mini Data Platform';

CREATE TABLE IF NOT EXISTS analytics.sales (
    id               BIGSERIAL PRIMARY KEY,
    transaction_id   TEXT        NOT NULL UNIQUE,
    transaction_date DATE        NOT NULL,
    customer_id      TEXT        NOT NULL,
    product_id       TEXT        NOT NULL,
    product_category TEXT        NOT NULL DEFAULT 'Unknown',
    quantity         INTEGER     NOT NULL CHECK (quantity >= 0),
    unit_price       NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    revenue          NUMERIC(14, 2) NOT NULL CHECK (revenue >= 0),
    region           TEXT        NOT NULL DEFAULT 'Unknown',
    payment_method   TEXT        NOT NULL DEFAULT 'Unknown',
    sales_year       SMALLINT    NOT NULL,
    sales_month      SMALLINT    NOT NULL CHECK (sales_month BETWEEN 1 AND 12),
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sales_transaction_date ON analytics.sales (transaction_date);
CREATE INDEX IF NOT EXISTS idx_sales_product_category ON analytics.sales (product_category);
CREATE INDEX IF NOT EXISTS idx_sales_region ON analytics.sales (region);
CREATE INDEX IF NOT EXISTS idx_sales_year_month ON analytics.sales (sales_year, sales_month);

COMMENT ON TABLE analytics.sales IS 'Cleaned, transformed sales transactions loaded by the Airflow DAG. transaction_id is unique so re-running the load for the same file is idempotent.';
