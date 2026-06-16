import os
import psycopg2
from dotenv import load_dotenv
import plaid
from plaid.api import plaid_api
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.accounts_get_request import AccountsGetRequest

# 1. Load environment and database
load_dotenv()

# 2. Initialize Plaid
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")
if PLAID_ENV == "sandbox":
    host = plaid.Environment.Sandbox
else:
    host = plaid.Environment.Production

configuration = plaid.Configuration(
    host=host,
    api_key={
        'clientId': os.getenv("PLAID_CLIENT_ID"),
        'secret': os.getenv("PLAID_SECRET"),
    }
)
client = plaid_api.PlaidApi(plaid.ApiClient(configuration))

def run_automated_sync():
    print("Initializing background database sync across all institutions...")
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()
    
    try:
        # FIX: Fetch ALL items instead of LIMIT 1
        cursor.execute("SELECT item_id, access_token FROM items;")
        items = cursor.fetchall()
        
        if not items:
            print("❌ No linked accounts found in the database. Exiting.")
            return
            
        total_accounts_updated = 0
        total_transactions_added = 0
        
        # Loop through every single bank connection stored in your database
        for item_id, access_token in items:
            print(f"-> Pulling latest data for bank item: {item_id}")
            
            try:
                # 1. Sync Accounts for this specific bank
                accounts_request = AccountsGetRequest(access_token=access_token)
                accounts_response = client.accounts_get(accounts_request)
                
                for acct in accounts_response['accounts']:
                    cursor.execute("""
                        INSERT INTO accounts (item_id, account_id, name, type, subtype, current_balance, available_balance, iso_currency_code)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (account_id) DO UPDATE 
                        SET current_balance = EXCLUDED.current_balance,
                            available_balance = EXCLUDED.available_balance,
                            updated_at = CURRENT_TIMESTAMP;
                    """, (
                        item_id, acct['account_id'], acct['name'], str(acct['type']),
                        str(acct.get('subtype', 'unknown')), acct['balances'].get('current'),
                        acct['balances'].get('available'), acct['balances'].get('iso_currency_code')
                    ))
                total_accounts_updated += len(accounts_response['accounts'])
                
                # 2. Sync Transactions for this specific bank
                request = TransactionsSyncRequest(access_token=access_token)
                response = client.transactions_sync(request)
                added_transactions = response['added']
                
                for tx in added_transactions:
                    cursor.execute("""
                        INSERT INTO transactions (account_id, transaction_id, amount, date, merchant_name, category, pending)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (transaction_id) DO NOTHING;
                    """, (
                        tx['account_id'], tx['transaction_id'], tx['amount'], tx['date'],
                        tx.get('merchant_name') or tx.get('name') or "Unknown",
                        tx.get('personal_finance_category', {}).get('primary') or "UNCLASSIFIED",
                        tx['pending']
                    ))
                total_transactions_added += len(added_transactions)
                
            except Exception as item_error:
                print(f"❌ Failed to sync item {item_id}: {item_error}")
                continue # Keep going even if one bank fails
                
        conn.commit()
        print(f"\n✅ Auto-Sync Complete: Total of {total_accounts_updated} accounts updated and {total_transactions_added} transactions aggregated.")

    except Exception as e:
        conn.rollback()
        print(f"❌ Critical error during pipeline execution: {e}")
    finally:
        cursor.close()
        conn.close()
        
if __name__ == "__main__":
    run_automated_sync()