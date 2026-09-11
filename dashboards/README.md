# Sales Dashboard — Metabase Setup

This documents how to stand up the required dashboard. `scripts/init_metabase.py`
attempts to automate the first two steps (admin account + database connection)
via Metabase's one-shot setup API — try that first with `make init-metabase`.
If it doesn't work (Metabase's setup API varies across versions and only
works on a completely fresh instance), follow the manual steps below; they
always work.

## 1. Open Metabase

Visit http://localhost:3000 (or `$METABASE_PORT` if you changed it).

## 2. Complete the setup wizard / log in

On first launch Metabase walks you through creating an admin account. If
`init_metabase.py` already did this, just log in with the admin email and
password you configured.

## 3. Add PostgreSQL as a database (skip if the script did this)

Admin settings -> Databases -> Add database:

| Field    | Value                                   |
|----------|------------------------------------------|
| Type     | PostgreSQL                                |
| Host     | `postgres` (the Docker service name — **not** `localhost`) |
| Port     | `5432`                                    |
| Database | value of `POSTGRES_DB` (default `mini_data_platform`) |
| Username | value of `POSTGRES_USER`                  |
| Password | value of `POSTGRES_PASSWORD`              |

## 4. Select the schema/table

The pipeline loads into `analytics.sales`. Metabase will sync this
automatically after the database is added (Admin settings -> Databases ->
Sync database schema now, if it doesn't appear right away).

## 5. Create questions (cards)

Create a new Question -> SQL query against the PostgreSQL database for each
of the following. Save each with the suggested name.

**Total Revenue**
```sql
SELECT SUM(revenue) AS total_revenue FROM analytics.sales;
```

**Total Transactions**
```sql
SELECT COUNT(*) AS total_transactions FROM analytics.sales;
```

**Total Quantity Sold**
```sql
SELECT SUM(quantity) AS total_quantity FROM analytics.sales;
```

**Average Transaction Value**
```sql
SELECT ROUND(AVG(revenue), 2) AS avg_transaction_value FROM analytics.sales;
```

**Revenue Over Time**
```sql
SELECT transaction_date, SUM(revenue) AS revenue
FROM analytics.sales
GROUP BY transaction_date
ORDER BY transaction_date;
```
Visualize as a line chart.

**Revenue by Product Category**
```sql
SELECT product_category, SUM(revenue) AS revenue
FROM analytics.sales
GROUP BY product_category
ORDER BY revenue DESC;
```
Visualize as a bar chart.

**Revenue by Region**
```sql
SELECT region, SUM(revenue) AS revenue
FROM analytics.sales
GROUP BY region
ORDER BY revenue DESC;
```
Visualize as a bar chart or map.

**Top Products**
```sql
SELECT product_id, SUM(revenue) AS revenue, SUM(quantity) AS units_sold
FROM analytics.sales
GROUP BY product_id
ORDER BY revenue DESC
LIMIT 10;
```

**Top Customers**
```sql
SELECT customer_id, SUM(revenue) AS revenue, COUNT(*) AS transactions
FROM analytics.sales
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 10;
```

## 6. Build the dashboard

Create a new Dashboard ("Sales Overview"), add all the cards above, and
arrange the four KPI numbers along the top with the charts below.

## 7. Add filters

Add a Dashboard filter for:
* **Date range** — map to `transaction_date` on each relevant card.
* **Region** — map to `region`.
* **Product Category** — map to `product_category`.

## Notes

* This dashboard cannot show anything until the Airflow DAG has loaded at
  least one batch of data — run `make pipeline` first (see the main README).
* Automated dashboard/card creation through the Metabase API was not
  pursued beyond the initial database connection: Metabase's card/dashboard
  API is verbose and version-sensitive, and a documented, reliable manual
  process was judged more valuable for an academic deliverable than a
  brittle automation that might silently produce the wrong chart type.
