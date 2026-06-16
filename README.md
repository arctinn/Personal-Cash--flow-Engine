# 📊 Quantitative Personal Finance Engine

An automated, full-stack data engineering pipeline and financial dashboard. This engine securely ingests live banking data via the Plaid API, stores it in a relational PostgreSQL database, and visualizes double-entry cash flow netting in a dark-mode Streamlit application.

## 🏗️ System Architecture

This project utilizes a Three-Pillar Architecture to separate raw data ingestion from mathematical transformation and presentation:

1. **Ingestion (ETL Backend):** A Python-based automation engine (`sync_job.py`) securely authenticates with the Plaid Production API, fetches real-time account balances, and extracts raw transaction ledgers.
2. **Storage (Data Warehouse):** A local **PostgreSQL** database enforces strict relational schemas (`schema.sql`), ensuring data integrity between banking items, accounts, and individual transactions.
3. **Presentation (UI/UX):** A **Streamlit** dashboard acts as the command center, applying quantitative logic to calculate net liquidity and visualize cash burn.

## 🚀 Key Features

* **Double-Entry Liability Routing:** Segregates "Depository" assets from "Credit" liabilities. The mathematical engine strictly nets out refunds and isolates internal bank transfers to prevent artificial inflation of spending metrics.
* **SaaS-Grade UI:** Custom CSS overrides create a clean, dark-mode visual interface with interactive Plotly graphs, moving away from standard, static dataframes.
* **Automated Batch Processing:** Designed to run silently in the background via Windows Task Scheduler or cron jobs, updating the relational database daily without manual web server initiation.
* **Multi-Institution Aggregation:** Seamlessly loops through multiple distinct API access tokens to aggregate data across completely separate financial institutions (e.g., Bank of America, American Express).

## 💻 Local Deployment

To run this pipeline locally, clone the repository and set up your virtual environment. 

### 1. Environment Variables
You must create a `.env` file in the root directory with your own API keys. **Never commit this file.**

```env
PLAID_CLIENT_ID=your_client_id_here
PLAID_SECRET=your_production_secret_here
PLAID_ENV=production
DATABASE_URL=postgresql://username:password@localhost:5432/finance_db