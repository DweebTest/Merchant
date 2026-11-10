# Running the database and the app on separate servers

Merchant is two pieces:

* the **database server**: MySQL 8 and the attachments folder
* the **app server**: the Merchant web app, which people open in a browser

They can share one machine (the Docker setup) or live on two. Moving them apart
needs no code changes, only settings. The examples use `db01` for the database
server and `app01` for the app server. Replace them with your own names or IP
addresses.

```
 browser ──HTTPS──▶ app01 (proxy + Merchant) ──3306──▶ db01 (MySQL)
                                     └──SMB/NFS share──▶ db01 (attachments folder)
```

## 1. Database server (db01)

### Install MySQL and create the database

Install MySQL 8 (Windows installer, `apt install mysql-server`, or the `db`
service from `docker-compose.yml`). Then, as the MySQL root user:

```sql
CREATE DATABASE merchant CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- Allow the Merchant user to connect only from the app server.
CREATE USER 'merchant'@'app01.yourcollege.edu' IDENTIFIED BY 'a-long-password';
GRANT ALL ON merchant.* TO 'merchant'@'app01.yourcollege.edu';
```

You can use the app server's IP address instead of its name, for example
`'merchant'@'10.0.5.20'`.

### Let MySQL listen on the network

By default MySQL may only accept connections from itself. In the MySQL config
(`my.ini` on Windows, `/etc/mysql/mysql.conf.d/mysqld.cnf` on Ubuntu) set:

```ini
[mysqld]
bind-address = 0.0.0.0
```

Restart MySQL afterwards.

### Firewall

Open TCP port **3306** inbound on db01 **only from app01**. Nobody else needs
to reach MySQL directly.

### Share the attachments folder

Create a folder for attachments, for example `D:\MerchantFiles` or
`/srv/merchant-files`, and share it with the app server:

* **Windows:** share it over SMB to the account the app runs as on app01, with
  read/write permission.
* **Linux:** export it over NFS (`/etc/exports`:
  `/srv/merchant-files app01(rw,sync,no_subtree_check)`) or share it with Samba.

Merchant keeps only file *names* in the database, so the database and folder
must be backed up together (step 5).

### Moving existing data

If you've been running everything on one machine, take a backup there first
(see [data-management.md](data-management.md)), restore the SQL into the new
`merchant` database on db01, and copy the uploads into the shared folder.

## 2. App server (app01)

### Mount the attachments share

* **Windows:** map the share or use its UNC path directly, for example
  `UPLOAD_FOLDER=\\db01\MerchantFiles`. The service account running Merchant
  needs write access to it.
* **Linux:** mount it, for example in `/etc/fstab`:
  `db01:/srv/merchant-files  /mnt/merchant-files  nfs  defaults,_netdev  0 0`

### Install and configure Merchant

Follow "Run it without Docker" in the [README](../README.md) (Python, `pip
install -r requirements.txt`). In `.env` on app01:

```ini
SECRET_KEY=<long random string>
DB_HOST=db01.yourcollege.edu
DB_PORT=3306
DB_NAME=merchant
DB_USER=merchant
DB_PASSWORD=a-long-password
UPLOAD_FOLDER=/mnt/merchant-files
```

Then, once:

```sh
flask db upgrade      # creates the tables on db01
flask seed            # default clusters and opportunity types
flask create-admin    # first administrator (skip if you restored a backup)
```

### Run it as a service

* **Linux:** `gunicorn -w 3 -b 127.0.0.1:8000 wsgi:app` under systemd.
* **Windows:** `waitress-serve --listen=127.0.0.1:8000 wsgi:app`, run as a
  service with NSSM or Task Scheduler ("at startup").

Three gunicorn workers (or waitress's default threads) are plenty for about 10
people. Listening on `127.0.0.1` means only the proxy in the next step can
reach Merchant directly.

**With Docker instead:** use `docker-compose.yml` without the `db` service,
remove `DB_HOST: db` from the `app` section, and bind-mount the share in place
of the `uploads` volume (`- /mnt/merchant-files:/data/uploads`).

## 3. HTTPS

Put a web server in front of Merchant on app01 to handle the certificate:
**IIS** with URL Rewrite and Application Request Routing on Windows, or
**nginx**/**Caddy** on Linux. It forwards requests to `http://127.0.0.1:8000`.

An nginx example:

```nginx
server {
    listen 443 ssl;
    server_name merchant.yourcollege.edu;
    ssl_certificate     /etc/ssl/merchant.crt;
    ssl_certificate_key /etc/ssl/merchant.key;
    client_max_body_size 30m;            # a bit above MAX_UPLOAD_MB

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
}
```

With IIS, turn on "Preserve host header" in ARR (Server Proxy Settings), and
add a server variable `HTTP_X_FORWARDED_PROTO` = `https` in the rewrite rule.

Then tell Merchant it's behind one proxy and on HTTPS, in `.env`:

```ini
TRUSTED_PROXIES=1
SESSION_COOKIE_SECURE=true
```

`TRUSTED_PROXIES` lets Merchant see the real `https://` address, which
Microsoft sign-in needs for its redirect. Leave it at `0` if people connect to
Merchant without a proxy, because otherwise anyone could fake those headers.

## 4. Check it works

1. Open `https://merchant.yourcollege.edu` and sign in.
2. Add an entry with an attachment, then confirm the file appears in the share
   on db01.
3. If Microsoft sign-in is set up, try the Microsoft button
   ([entra-sso.md](entra-sso.md)).

Common problems:

* **"Can't connect to MySQL server"**: check the firewall, `bind-address`, and
  that the MySQL user's host part matches app01 exactly.
* **"Access denied for user"**: the password, or the user was created for a
  different host. `SELECT user, host FROM mysql.user;` on db01 shows them.
* **Attachments fail to upload**: the account Merchant runs as can't write to
  the share.
* **Microsoft says the redirect URI doesn't match**: set `TRUSTED_PROXIES=1`
  and check the proxy sends `X-Forwarded-Proto`, or set `ENTRA_REDIRECT_URI`.

## 5. Backups

Back up the database and the attachments folder together, from db01:

```sh
mysqldump --single-transaction --routines merchant > merchant-YYYY-MM-DD.sql
```

On Windows, schedule this with Task Scheduler, and copy the attachments folder
alongside it with `robocopy D:\MerchantFiles <backup location> /MIR`. The
college's normal server backups can also cover both. Restoring is described in
[data-management.md](data-management.md).
