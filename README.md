# Merchant

A small, fast CRM for capturing market intelligence, partnership leads,
funding prospects and other opportunities across key economic sectors, so
what staff learn at meetings and events becomes a searchable knowledge base.

Built with Python (Flask), MySQL 8 and server-rendered pages.

## Status

| Step | What | State |
|---|---|---|
| 1 | Database, local login, users, groups, cluster and opportunity type lists | Done |
| 2 | Entry form, search, filters, recent submissions | Done |
| 3 | PDF reports | Done |
| 4 | Microsoft Entra SSO, split-server deployment guide | Done |

## Run it on one machine with Docker

New to Docker? Follow the step-by-step guide in
[docs/docker-quickstart.md](docs/docker-quickstart.md).

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
`UPLOAD_FOLDER` path. The full walkthrough, including HTTPS, is in
[docs/split-servers.md](docs/split-servers.md).

## Single sign-on with SAML (AWS IAM Identity Center and others)

Set `SAML_IDP_METADATA_URL` or `SAML_IDP_METADATA_FILE` and the sign-in page
shows **Sign in with AWS** (the wording is configurable). It works with AWS IAM
Identity Center and other SAML 2.0 identity providers, under the same rule as
Microsoft sign-in: only people an admin has added can get in. Merchant's SAML
details are at `/saml/metadata`. [docs/aws-lab.md](docs/aws-lab.md) is a
complete AWS walkthrough with separate app and database servers, HTTPS and
Identity Center.

## Users, roles and groups

* **Admins** manage users, groups and the cluster and opportunity type lists.
* **Contributors** add and search entries. They can edit or delete their own
  entries, and anyone can update an entry's follow-up status.
* **Groups** organize people (for example Advancement or Applied Research).
  Each group can later be granted permissions for specific functions. The
  tables for this exist now, and `User.has_permission()` is the check to use,
  but nothing is restricted by group yet.

New users get a temporary password and must choose their own at first
sign-in. After five wrong passwords an account is locked for 15 minutes
(both adjustable in `.env`).

## Signing in with Microsoft

Once IT registers Merchant in Microsoft Entra ID and you put three values in
`.env`, the sign-in page shows **Sign in with Microsoft**. Only people an admin
has already added in Merchant can get in; Merchant matches them by email the
first time and by their Microsoft account ID after that. Anyone else is told to
ask an administrator. Each user's sign-in method is either *Merchant password
(and single sign-on)* or *Single sign-on only*. Setup steps for you and IT are in
[docs/entra-sso.md](docs/entra-sso.md).

## Entry shortcuts

* Picking an organization that already has entries on **New entry** fills in
  its clusters, opportunity types, contact, college area and link from its most
  recent entry. Those sections are locked (greyed out) until you press **Edit**.
* On the **Knowledge base**, any set of filters can be saved with a name, either
  just for you or shared with everyone. Saved filters appear as buttons above
  the results.

## Look

Merchant opens in **Orbit**, a dark sci-fi look (glassy panels with cut
corners and cyan accents). Anyone can switch to the plain **Classic** look under
**Look** in the menu, and their browser remembers it. `DEFAULT_THEME=classic`
in `.env` makes Classic the default for everyone. Orbit's Chakra Petch font
(SIL Open Font License) ships with the app, so nothing loads from the internet.

**Personal themes:** put `<name>.css` (and any fonts it uses) in
`app/static/themes-local/`. It appears in the Look menu on that machine only;
git ignores the folder, so it never reaches the repository. Docker reads the
folder live, so new or edited themes appear on a page refresh. See the README
in that folder.

## Reports

Under **Reports**, anyone signed in can view these on screen or download them
as a PDF, for any date range and set of clusters:

* **Recent opportunities**: everything entered in the period, with counts by cluster.
* **Emerging sector trends**: clusters, opportunity types and organizations,
  compared with the period before, plus month-by-month counts.
* **Potential funding opportunities** and **Partnership leads**: entries whose
  opportunity types are marked for that report. By default donors, sponsors and
  grants count as funding, and partnership and applied research count as
  partnership leads. Admins can change this on the Opportunity types page.
* **Priority follow-ups**: open follow-ups that are overdue, due within two
  weeks, or high priority.

PDFs are made with ReportLab, which is pure Python, so nothing extra needs
installing on Windows or Linux.

## Demo data, backups and starting fresh

`flask demo-data load` fills Merchant with realistic sample data and
`flask demo-data clear` removes it again without touching real data. See
[docs/data-management.md](docs/data-management.md) for that, plus backing up,
restoring and wiping everything before going live.

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
