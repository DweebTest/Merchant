# Demo data, backups and starting fresh

Run every command below in PowerShell (Windows) or Terminal (Mac), inside
your Merchant folder (the one with `docker-compose.yml`), while Merchant is
running (`docker compose up -d`).

| I want to… | Section |
|---|---|
| Fill Merchant with realistic sample data for a demo | [Load demo data](#load-demo-data) |
| Remove the sample data but keep my own entries | [Remove demo data](#remove-demo-data) |
| Save everything so I can get it back later | [Back up](#back-up) |
| Put a saved copy back | [Restore](#restore) |
| Wipe everything before going live | [Start fresh for production](#start-fresh-for-production) |

## Load demo data

```
docker compose exec app flask demo-data load
```

This adds about 120 entries spread over the last 12 months, from 22 made-up
organizations in all ten clusters, with contacts, follow-ups and a mix of
statuses and priorities. Dates are counted back from today, so the reports
always look current. Energy, Technology and Health Care come up more often
in recent months, so the trends report has something to show.

It also adds five groups (Advancement, Community Relations, Continuing
Education, Applied Research, Leadership) and six contributors. They sign in
with these emails and the password `Demo-pass-2026`:

* alex.morgan@demo.example.com
* priya.shah@demo.example.com
* jordan.lee@demo.example.com
* sam.okafor@demo.example.com
* taylor.brooks@demo.example.com
* chris.dubois@demo.example.com

Your own admin account and anything you've entered are left alone. If an
organization you already entered has the same name as a demo one, the demo
entries are added under yours.

## Remove demo data

```
docker compose exec app flask demo-data clear
```

Type `y` to confirm. This removes only what `load` added: the demo entries,
organizations, contacts, users and groups. Your own data is never touched.
If one of your own entries uses a demo organization or contact, that one record
is kept so your entry isn't broken, and the command tells you so.

You can run `load` again afterwards for a fresh set.

## Back up

A backup has two parts: the database (a single `.sql` file) and the attachments
folder. Run these three commands:

```
docker compose exec db sh -c 'MYSQL_PWD=$MYSQL_ROOT_PASSWORD mysqldump -uroot --single-transaction --no-tablespaces $MYSQL_DATABASE > /tmp/merchant-backup.sql'
docker compose cp db:/tmp/merchant-backup.sql ./merchant-backup.sql
docker compose cp app:/data/uploads ./uploads-backup
```

Copy the first line exactly as written, including the single quotes.

You now have `merchant-backup.sql` and an `uploads-backup` folder in your
Merchant folder. Move both somewhere safe, such as a folder named with the date.
Each backup replaces the previous one if you leave them in place.

The `.sql` file contains everything, including people's names, emails and
password hashes, so store it like any other confidential file.

## Restore

Put `merchant-backup.sql` and the `uploads-backup` folder back in your Merchant
folder, then run:

```
docker compose cp ./merchant-backup.sql db:/tmp/merchant-backup.sql
docker compose exec db sh -c 'MYSQL_PWD=$MYSQL_ROOT_PASSWORD mysql -uroot $MYSQL_DATABASE < /tmp/merchant-backup.sql'
docker compose cp ./uploads-backup/. app:/data/uploads
docker compose exec -u root app chown -R merchant /data/uploads
docker compose restart app
```

This **replaces** whatever is in Merchant now with the backup. Anything added
since the backup was taken is lost, so take a fresh backup first if you're not
sure.

If the backup came from an older version of Merchant, the app brings the
database up to date when it restarts.

## Start fresh for production

When you're ready to go live and want nothing left from testing (no demo data,
no test entries, no test accounts):

1. Take a [backup](#back-up) first if you might want your test data again.
2. Wipe everything:
   ```
   docker compose down -v
   ```
   The `-v` deletes the database and the attachments. This can't be undone.
3. Start again and create the real administrator:
   ```
   docker compose up -d
   docker compose exec app flask create-admin
   ```

Merchant starts empty except for the default clusters and opportunity types.

If you only want to remove the demo data and keep your own test entries and
accounts, use [Remove demo data](#remove-demo-data) instead.

## When the database is on its own server

The commands above assume the Docker setup. Once MySQL runs on a separate
server, your database administrator can back it up with the same
`mysqldump` and `mysql` commands on that server, plus a copy of the
attachments folder. The demo-data commands work the same everywhere:
`flask demo-data load` and `flask demo-data clear`.
