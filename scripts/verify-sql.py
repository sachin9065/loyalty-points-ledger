import sqlite3, json
con=sqlite3.connect(':memory:')
con.executescript(open('data/sql/schema.sql').read())
con.executescript(open('data/sql/seed.sql').read())
tables=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print(tables)
for t in tables:
    print(t, con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0])
print('null pk points', con.execute("SELECT COUNT(*) FROM points_transactions WHERE points_txn_id IS NULL OR points_txn_id=''").fetchone()[0])
print('fk broken', con.execute('SELECT COUNT(*) FROM points_transactions WHERE account_id NOT IN (SELECT account_id FROM loyalty_accounts)').fetchone()[0])
print('balance check mismatches', con.execute('''SELECT COUNT(*) FROM loyalty_accounts a WHERE a.available_points != (SELECT COALESCE(SUM(points_delta),0) FROM points_transactions p WHERE p.account_id=a.account_id)''').fetchone()[0])
