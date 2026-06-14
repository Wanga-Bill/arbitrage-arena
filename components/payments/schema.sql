CREATE TABLE IF NOT EXISTS billing_ledger (
    invoice_id TEXT PRIMARY KEY,
    tg_user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    gateway TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
