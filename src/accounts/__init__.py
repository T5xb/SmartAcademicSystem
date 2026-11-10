"""
Accounts, sign-in sessions and role-based access (student / advisor / admin).

    db.py        the tables (Supabase Postgres; SQLite in the tests)
    security.py  password hashing and session tokens
    store.py     reads and writes: users, sessions, chats, profiles
    deps.py      FastAPI dependencies: who is signed in, which role is allowed
    api.py       /api/auth, /api/me, /api/advisor, /api/admin/users
    documents.py the admin's source-file management and index rebuild
"""
