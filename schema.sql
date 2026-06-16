-- Create the Items table (Stores your Bank Logins / Access Tokens)
CREATE TABLE items (
    id SERIAL PRIMARY KEY,
    item_id VARCHAR(255) UNIQUE NOT NULL,
    access_token VARCHAR(255) UNIQUE NOT NULL,
    institution_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create the Accounts table (Stores your specific Checking/Savings/Credit accounts)
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    item_id VARCHAR(255) REFERENCES items(item_id) ON DELETE CASCADE,
    account_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,
    subtype VARCHAR(50),
    current_balance DECIMAL(15, 2),
    available_balance DECIMAL(15, 2),
    iso_currency_code VARCHAR(3),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create the Transactions table (The raw ledger data)
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255) REFERENCES accounts(account_id) ON DELETE CASCADE,
    transaction_id VARCHAR(255) UNIQUE NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    date DATE NOT NULL,
    merchant_name VARCHAR(150),
    category VARCHAR(100),
    pending BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);