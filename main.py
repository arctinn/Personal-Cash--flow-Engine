import os
import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel
import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.accounts_get_request import AccountsGetRequest

# Load variables from .env file
load_dotenv()

app = FastAPI(title="Personal Finance Pipeline Backend")

# Enable CORS so your local HTML file can communicate with your FastAPI backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

# Map environment strings to Plaid API hosts
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")
if PLAID_ENV == "sandbox":
    host = plaid.Environment.Sandbox
elif PLAID_ENV == "development":
    host = plaid.Environment.Development
else:
    host = plaid.Environment.Production

# Initialize the Plaid API Client Configuration
configuration = plaid.Configuration(
    host=host,
    api_key={
        'clientId': os.getenv("PLAID_CLIENT_ID"),
        'secret': os.getenv("PLAID_SECRET"),
    }
)

# --- Database Connection Helper ---
def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

api_client = plaid.ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)

# Pydantic Model for incoming requests
class TokenExchangeRequest(BaseModel):
    public_token: str

# Global variables for temporary token storage
access_token = None
item_id = None

@app.get("/")
def read_root():
    return {"status": "Pipeline backend is running", "environment": PLAID_ENV}

@app.post("/api/create_link_token")
def create_link_token():
    """
    Step 1: Generates a short-lived token to initialize the bank login widget.
    """
    try:
        request = LinkTokenCreateRequest(
            products=[Products("transactions")],
            client_name="Personal Finance Dashboard",
            country_codes=[CountryCode("US")],
            language="en",
            user=LinkTokenCreateRequestUser(client_user_id="unique-user-id-123")
        )
        response = client.link_token_create(request)
        return {"link_token": response['link_token']}
    except plaid.ApiException as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/set_access_token")
def exchange_public_token(request: TokenExchangeRequest):
    """
    Step 2: Exchanges the temporary public_token for a permanent access_token
    and stores it securely in the PostgreSQL database.
    """
    try:
        exchange_request = ItemPublicTokenExchangeRequest(
            public_token=request.public_token
        )
        exchange_response = client.item_public_token_exchange(exchange_request)
        
        access_token = exchange_response['access_token']
        item_id = exchange_response['item_id']
        
        # --- DATABASE INSERTION ---
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # We use parameterized queries (%s) to prevent SQL injection attacks.
        # The 'ON CONFLICT' clause ensures we don't crash if we link the same bank twice; 
        # it just updates the token instead.
        cursor.execute("""
            INSERT INTO items (item_id, access_token, institution_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (item_id) DO UPDATE 
            SET access_token = EXCLUDED.access_token;
        """, (item_id, access_token, "Plaid Sandbox Bank"))
        
        conn.commit()  # Save the changes
        cursor.close()
        conn.close()
        
        print(f"\n✅ SUCCESS! Token safely stored in PostgreSQL.")
        
        return {"message": "Access token secured in database!"}
    
    except psycopg2.Error as db_error:
        print(f"Database Error: {db_error}")
        raise HTTPException(status_code=500, detail="Failed to save to database.")
    except plaid.ApiException as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@app.post("/api/sync")
def sync_data():
    """
    Step 3: The Production Data Engine. 
    1. Fetches Accounts and updates balances.
    2. Fetches new Transactions and appends them to the ledger.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Retrieve both item_id and access_token from the database
        cursor.execute("SELECT item_id, access_token FROM items LIMIT 1;")
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=400, detail="No linked accounts found in database.")
        
        item_id, access_token = row[0], row[1]
        
        # --- 1. INGEST ACCOUNTS & BALANCES ---
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
                item_id,
                acct['account_id'],
                acct['name'],
                str(acct['type']),
                str(acct.get('subtype', 'unknown')),
                acct['balances'].get('current'),
                acct['balances'].get('available'),
                acct['balances'].get('iso_currency_code')
            ))
            
        print(f"\n✅ Synced {len(accounts_response['accounts'])} accounts into database.")

        # --- 2. INGEST TRANSACTIONS ---
        request = TransactionsSyncRequest(access_token=access_token)
        response = client.transactions_sync(request)
        added_transactions = response['added']
        
        for tx in added_transactions:
            cursor.execute("""
                INSERT INTO transactions (account_id, transaction_id, amount, date, merchant_name, category, pending)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (transaction_id) DO NOTHING;
            """, (
                tx['account_id'],
                tx['transaction_id'],
                tx['amount'],
                tx['date'],
                tx.get('merchant_name') or tx.get('name') or "Unknown",
                tx.get('personal_finance_category', {}).get('primary') or "UNCLASSIFIED",
                tx['pending']
            ))
            
        print(f"✅ Synced {len(added_transactions)} new transactions into database.\n")
        
        conn.commit() # Save all changes to the PostgreSQL database
        
        return {
            "message": "Full database sync successful!", 
            "accounts_updated": len(accounts_response['accounts']),
            "transactions_added": len(added_transactions)
        }

    except psycopg2.Error as db_error:
        conn.rollback() # Cancel the database transaction if something breaks
        print(f"Database Error: {db_error}")
        raise HTTPException(status_code=500, detail="Database failure.")
    except plaid.ApiException as e:
        print(f"Plaid Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()
        conn.close()