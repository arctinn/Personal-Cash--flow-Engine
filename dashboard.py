import streamlit as st
import pandas as pd
import psycopg2
import os
from dotenv import load_dotenv
import plotly.express as px

# --- 1. CONFIGURATION & CUSTOM CSS ---
load_dotenv()
st.set_page_config(page_title="FinEngine | Dashboard", page_icon="🏦", layout="wide", initial_sidebar_state="expanded")

# Injecting Custom SaaS UI/UX CSS
st.markdown("""
    <style>
    /* Main Backgrounds */
    [data-testid="stAppViewContainer"] { background-color: #0e1117; color: #ffffff; }
    [data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
    
    /* Clean Metric Cards */
    div[data-testid="metric-container"] {
        background-color: #1c2128;
        border-radius: 12px;
        padding: 24px;
        border: 1px solid #30363d;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    
    /* Hide Streamlit Branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- 2. DATA INGESTION ---
@st.cache_data(ttl=300) # Caches data for 5 mins to make the UI lightning fast
def load_data():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    accounts_df = pd.read_sql("SELECT account_id, name, type, current_balance FROM accounts;", conn)
    query = """
        SELECT t.date, a.name as account_name, t.merchant_name, t.category, t.amount
        FROM transactions t JOIN accounts a ON t.account_id = a.account_id ORDER BY t.date DESC;
    """
    transactions_df = pd.read_sql(query, conn)
    conn.close()
    
    if not transactions_df.empty:
        transactions_df['date'] = pd.to_datetime(transactions_df['date'])
        transactions_df['billing_cycle'] = transactions_df['date'].dt.strftime('%Y-%m')
    
    return accounts_df, transactions_df

accounts, transactions = load_data()

# --- 3. SIDEBAR NAVIGATION ---
with st.sidebar:
    st.markdown("### 🏦 **FinEngine**")
    st.caption("Personal Wealth Dashboard")
    st.divider()
    
    if not transactions.empty:
        cycles = ["All Time"] + sorted(transactions['billing_cycle'].unique().tolist(), reverse=True)
        selected_cycle = st.selectbox("📅 Billing Cycle", cycles)
        
        account_list = ["All Accounts"] + accounts['name'].unique().tolist()
        selected_account = st.selectbox("💳 Filter Account", account_list)
    else:
        selected_cycle = "All Time"
        selected_account = "All Accounts"

# --- 4. MAIN UI ROUTING ---
if accounts.empty:
    st.error("⚠️ Database is empty. Please run the Plaid authentication and execute `sync_job.py`.")
else:
    st.title("Net Worth & Liquidity")
    
    # STRICT MATH LOGIC: Absolute values prevent negative/positive API flips
    liquid_cash = abs(accounts[accounts['type'] == 'depository']['current_balance'].sum())
    credit_debt = abs(accounts[accounts['type'] == 'credit']['current_balance'].sum())
    net_liquidity = liquid_cash - credit_debt

    # Top KPI Row
    col1, col2, col3 = st.columns(3)
    col1.metric("Adv SafeBalance (Assets)", f"${liquid_cash:,.2f}")
    col2.metric("Total Debt (Liabilities)", f"${credit_debt:,.2f}")
    col3.metric("True Net Liquidity", f"${net_liquidity:,.2f}")
    
    st.divider()

    # Apply global sidebar filters
    viz_tx = transactions.copy()
    if selected_cycle != "All Time":
        viz_tx = viz_tx[viz_tx['billing_cycle'] == selected_cycle]
    if selected_account != "All Accounts":
        viz_tx = viz_tx[viz_tx['account_name'] == selected_account]

    # --- 5. VISUAL ANALYTICS ---
    st.subheader("Cash Flow Analytics")
    
    # Financial Logic: Strip out routing/transfers
    exclusion_pattern = 'TRANSFER|PAYMENT|CREDIT CARD'
    viz_tx = viz_tx[~viz_tx['category'].str.upper().str.contains(exclusion_pattern, na=False)]
    
    # Group and filter strictly positive spend (expenses)
    spend_df = viz_tx[viz_tx['amount'] > 0]

    if not spend_df.empty:
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            spend_by_cat = spend_df.groupby("category")["amount"].sum().reset_index()
            fig_pie = px.pie(
                spend_by_cat, values='amount', names='category', hole=0.5,
                color_discrete_sequence=px.colors.sequential.Teal
            )
            # Make Plotly background completely transparent to match the UI
            fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False)
            fig_pie.update_traces(textposition='inside', textinfo='percent+label', marker=dict(line=dict(color='#0e1117', width=2)))
            st.plotly_chart(fig_pie, use_container_width=True)

        with chart_col2:
            top_merchants = spend_df.groupby("merchant_name")["amount"].sum().reset_index().sort_values(by="amount").tail(8)
            fig_bar = px.bar(
                top_merchants, x='amount', y='merchant_name', orientation='h', text_auto='$.2f',
                color='amount', color_continuous_scale=px.colors.sequential.Teal
            )
            fig_bar.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", 
                xaxis=dict(showgrid=False), yaxis=dict(showgrid=False, title="")
            )
            st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("No expense data found for these filters.")

    # --- 6. INTERACTIVE LEDGER ---
    st.subheader("Transaction Ledger")
    
    display_df = viz_tx.copy()
    if not display_df.empty:
        display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
        display_df = display_df[['date', 'account_name', 'merchant_name', 'category', 'amount']]
        display_df.rename(columns={'date': 'Date', 'account_name': 'Bank', 'merchant_name': 'Merchant', 'category': 'Category', 'amount': 'Amount ($)'}, inplace=True)
        
        st.dataframe(
            display_df, use_container_width=True, hide_index=True, height=400,
            column_config={"Amount ($)": st.column_config.NumberColumn("Amount ($)", format="$ %.2f")}
        )