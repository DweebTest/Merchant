# Merchant

A small, fast CRM for capturing market intelligence, partnership leads,
funding prospects and other opportunities across key economic sectors, so
what staff learn at meetings and events becomes a searchable knowledge base.

Built with Python (Flask), MySQL 8 and server-rendered pages.

## Status

| Step | What | State |
|---|---|---|
| 1 | Database, local login, users, groups, cluster and opportunity type lists | Done |
| 2 | Entry form, search, filters, recent submissions | Next |
| 3 | PDF reports | Planned |
| 4 | Microsoft Entra SSO, split-server deployment guide | Planned |

## Run it on one machine with Docker

```sh
cp .env.example .env
# Edit .env: set SECRET_KEY, DB_PASSWORD and MYSQL_ROOT_PASSWORD
docker compose up -d --build
docker compose exec app flask create-admin
```

Open http://localhost:8000 and sign in with the admin account you created.
The app creates the tables and loads the default clusters and opportunity
types on startup.

## Run it without Docker

You need Python 3.12+ and a MySQL 8 server.

```sql
CREATE DATABASE merchant CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'merchant'@'%' IDENTIFIED BY 'choose-a-password';
GRANT ALL ON merchant.* TO 'merchant'@'%';
```

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in SECRET_KEY and the DB_* settings
export FLASK_APP=wsgi.py
flask db upgrade              # create or update tables
flask seed                    # load default clusters and opportunity types
flask create-admin            # first administrator
gunicorn -b 0.0.0.0:8000 wsgi:app
```

On Windows, use `waitress-serve --port=8000 wsgi:app` instead of gunicorn (gunicorn is Linux and macOS only).

## Moving the database to its own server

All database settings come from `.env`. On the app server, set `DB_HOST` to
the database server's name or IP. Nothing in the code changes. Make sure the
MySQL user is allowed to connect from the app server and that port 3306 is
open between the two.

Attachments are stored in `UPLOAD_FOLDER`. They live on the database server,
so share that folder from it and mount it on the app server at the same
`UPLOAD_FOLDER` path. Step 4 adds a full guide.

## Users, roles and groups

* **Admins** manage users, groups and the cluster and opportunity type lists.
* **Contributors** add and search entries.
* **Groups** organize people (for example Advancement or Applied Research).
  Each group can later be granted permissions for specific functions. The
  tables for this exist now, and `User.has_permission()` is the check to use,
  but nothing is restricted by group yet.

New users get a temporary password and must choose their own at first
sign-in. After five wrong passwords an account is locked for 15 minutes
(both adjustable in `.env`).

## Tests

```sh
pip install -r requirements-dev.txt
pytest                                   # quick, uses in-memory SQLite
TEST_DATABASE_URL="mysql+pymysql://merchant:pw@localhost/merchant_test?charset=utf8mb4" pytest
```

## Changing the database

Edit `app/models.py`, then:

```sh
flask db migrate -m "describe the change"
flask db upgrade
```
