# AWS lab: split servers, HTTPS and AWS single sign-on

This walks through a complete test setup of Merchant on Amazon Web Services:

* **db01**: a database server running MySQL and holding the attachments folder
* **app01**: an app server running Merchant in Docker, with HTTPS
* **AWS IAM Identity Center** (formerly "AWS SSO"), so people sign in with
  their AWS access-portal account. Only people you've added in Merchant get in.

It mirrors the on-premises layout in [split-servers.md](split-servers.md), so
what you learn here carries over. Allow about two hours the first time. All
the clicking is in the AWS web console, and you won't need anything installed
on your PC.

```
           ┌──────────── AWS (one region) ─────────────────────────────────┐
 browser ──HTTPS──▶ app01: Caddy ─▶ Merchant ──3306 MySQL──▶ db01: MySQL      │
           │                         └──2049 NFS (attachments)──▶ db01: files │
           │  IAM Identity Center ◀── sign-in redirects ──▶ Merchant          │
           └──────────────────────────────────────────────────────────────────┘
```

## What it costs

This lab uses two small servers, two public IP addresses and 16 GB of disk:
roughly **US$25–30 a month** if they run all the time, or about **US$5–8 a
month** if you pause them between sessions (see **Pausing the lab**). IAM
Identity Center has no charge of its own. New AWS accounts may come with
credits that cover this for a while; each person only gets those once. The
**Clean up** section at the end removes everything.

## 1. Account and budget alert

1. Create the account with the classic sign-up page,
   <https://portal.aws.amazon.com/billing/signup>, so you get a standalone
   account that you fully own. Accounts made through the newer
   **settings.aws.com** sign-up (with "Projects") sit inside an organization
   AWS manages: IAM Identity Center is greyed out there, and some console
   features fail with *"explicit deny in a service control policy"*.
   Turn on **MFA** for the root user when prompted, under
   **Security credentials**.
2. In the top-right region menu, pick one region and use it for everything,
   for example **Canada (Central) ca-central-1**.
3. Search for **Billing and Cost Management → Budgets → Create budget**, choose
   the **Monthly cost budget** template, set the most you're happy to spend
   (for example **US$30**), and enter your email. AWS will email you if
   spending heads past that.
4. Don't use the root user day to day. Once Identity Center is on (step 6),
   give yourself an administrator permission set and sign in through the
   access portal instead. Keep the root password and MFA somewhere safe.
5. **EC2 → Settings → EBS encryption → Manage → Enable**, so every disk you
   create from now on is encrypted. It's free.

## 2. Security groups (firewall rules)

**EC2 → Security Groups → Create security group** (keep the default VPC):

| Name | Inbound rules |
|---|---|
| `merchant-app` | HTTP 80 from Anywhere-IPv4; HTTPS 443 from Anywhere-IPv4; SSH 22 from **`ec2-instance-connect`** (see below) |
| `merchant-db` | MySQL/Aurora 3306 from **`merchant-app`** (pick the security group as the source); NFS 2049 from **`merchant-app`**; SSH 22 from **`ec2-instance-connect`** |

You'll reach both servers through **Connect** in the console, which opens a
terminal in your browser. That connection comes from AWS's own servers, not
your PC, so the SSH rule's source must be AWS's connection service: in the
Source box, start typing `ec2-instance-connect` and pick
`com.amazonaws.<region>.ec2-instance-connect`. Without it, Connect fails with
*"Error establishing SSH connection"*. (Ignore the console's AI "connection
assistant"; you don't need it.)

The database is never reachable from the internet. Only the app server can
reach MySQL and the attachments share.

## 3. Launch the two servers

**EC2 → Instances → Launch instances**, twice:

| | db01 | app01 |
|---|---|---|
| Name | `merchant-db01` | `merchant-app01` |
| Image | Ubuntu Server 24.04 LTS | Ubuntu Server 24.04 LTS |
| Instance type | one marked **Free tier eligible**, e.g. `t3.micro` or `t3.small` | same |
| Key pair | *Proceed without a key pair* (you'll use Connect) | same |
| Network settings → Select existing security group | `merchant-db` | `merchant-app` |
| Storage | 8 GB gp3 (default), **Encrypted** (on by default after step 1.5) | same |
| Advanced details → Metadata version | **V2 only (token required)** | same |

When they're running, click each one and note its **Private IPv4 address**
(it starts with 172.31). You'll need both.

### Give app01 a fixed public address

**EC2 → Elastic IPs → Allocate Elastic IP address → Allocate**, then
**Actions → Associate**, and pick `merchant-app01`. Write down the address,
for example `15.222.10.20`.

Your site's name is that address with dashes, followed by `.sslip.io`, for
example **`15-222-10-20.sslip.io`**. sslip.io is a free service that points
such names at the address inside them, which lets HTTPS work without
buying a domain. If the college gives you a real name later, use that
instead. In the steps below, **HOST** means this name.

## 4. Set up db01

Select `merchant-db01` → **Connect** → **EC2 Instance Connect** tab (username
`ubuntu`) → **Connect**. A terminal opens in a new tab. To paste into it, use
right-click → **Paste** or **Ctrl+Shift+V**. Run (use **app01's** *private* IP;
the database will only accept connections from that address):

```sh
curl -fsSLO https://raw.githubusercontent.com/DweebTest/Merchant/main/deploy/aws/db-server-setup.sh
sudo bash db-server-setup.sh 172.31.x.x
```

It installs MySQL, creates the `merchant` database with a user that can only
connect from app01, shares `/srv/merchant-files` with app01 for attachments,
and sets up a nightly backup in `/srv/backups`. At the end it prints
`DB_HOST`, `DB_PASSWORD` and so on. **Copy those lines**, because you'll
need them on app01.

## 5. Set up app01

Connect to `merchant-app01` the same way and run (use db01's *private* IP):

```sh
curl -fsSLO https://raw.githubusercontent.com/DweebTest/Merchant/main/deploy/aws/app-server-setup.sh
sudo bash app-server-setup.sh 172.31.y.y
```

This installs Docker, mounts db01's attachments share at
`/mnt/merchant-files`, and downloads Merchant into `~/Merchant`. Close the
browser tab and **Connect again**, so Docker works without `sudo`.

### Configure Merchant

```sh
cd ~/Merchant
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # copy the output
nano .env
```

Only you should be able to read this file, since it holds the passwords:

```sh
chmod 600 .env
```

`nano` is a simple editor inside the terminal. Move with the arrow keys; press
**Ctrl+W** and type a name such as `DB_HOST` to jump to that line; delete the
old value with Backspace and paste the new one. Save with **Ctrl+O** then
**Enter**, and exit with **Ctrl+X**. Fill in these lines:

```ini
SECRET_KEY=<the long random string you just printed>
DB_HOST=<from db01's output>
DB_NAME=merchant
DB_USER=merchant
DB_PASSWORD=<from db01's output>
SITE_ADDRESS=HOST
SAML_SP_BASE_URL=https://HOST
```

* `DB_HOST` is **db01's private IP** (172.31…), never the sslip.io name.
* `HOST` is **app01's** sslip.io name, from its Elastic IP.
* No spaces, quotes or `#` at the start of these lines. A line starting with
  `#` is ignored.

Check your work with `grep -E "^(SECRET|DB_|SITE|SAML)" .env`.

Leave `MYSQL_ROOT_PASSWORD` empty, because the database lives on db01.

**Changed `.env` later?** Docker only reads it when it creates the
containers, so apply changes with
`docker compose -f docker-compose.aws.yml up -d --force-recreate`.

**Never run `flask demo-data load` on a cloud server.** The demo accounts share a
published password. If you load demo data to try things out, run
`flask demo-data clear` before anyone real uses the site.

Start it and create your admin account. Use **the email address you'll use
for AWS sign-in**:

```sh
docker compose -f docker-compose.aws.yml up -d --build
docker compose -f docker-compose.aws.yml logs app      # look for "Seed complete"
docker compose -f docker-compose.aws.yml exec app flask create-admin
```

Run these from inside `~/Merchant` (each new terminal starts in your home
folder, so `cd ~/Merchant` first).

In your browser's address bar, open **https://HOST**. The first visit can take a minute while Caddy gets the
HTTPS certificate. Sign in with your password and add an entry with an
attachment. To prove the split works, connect to db01 and run
`sudo ls /srv/merchant-files`. Your file is there.

## 6. Turn on IAM Identity Center

1. Search for **IAM Identity Center** → **Enable**. When asked, choose to enable
   it **with AWS Organizations** (an *organization instance*). Only that kind
   supports SAML for your own apps
   ([AWS](https://docs.aws.amazon.com/singlesignon/latest/userguide/identity-center-instances.html)).
   Organizations is free and just wraps your account.
2. **Users → Add user.** Use the same email as your Merchant admin. Accept the
   invitation email, choose a password and set up MFA. **Settings** shows your
   **AWS access portal URL**. Bookmark it.

### Add Merchant as an application

1. **Applications → Customer managed → Add application → I have an application
   I want to set up → SAML 2.0 → Next.**
2. **Display name:** `Merchant`.
3. Under **IAM Identity Center metadata**, **Download** the *IAM Identity Center
   SAML metadata file*. You'll give this to Merchant.
4. **Application properties → Application start URL:** `https://HOST/login/saml`
   (so the tile in the access portal starts sign-in at Merchant). Leave
   *Relay state* empty.
5. **Application metadata → Manually type your metadata values:**
   * **Application ACS URL:** `https://HOST/login/saml/acs`
   * **Application SAML audience:** `https://HOST/saml/metadata`

   (Or upload the file from `https://HOST/saml/metadata` once step 7 below is
   done. It holds the same two values.)
6. **Submit.**
7. On the application's page, **Actions → Edit attribute mappings**:
   * **Subject** → `${user:subject}`, format **persistent**
   * **Add new attribute mapping** → `email` → `${user:email}`, format **unspecified**

   **Save changes.**
8. **Assign users and groups** → pick yourself (or a group) → **Assign**.

Field names in the AWS console change from time to time. If one doesn't match,
the values above are still what Merchant expects.

### Give Merchant the metadata

Open the downloaded metadata file in Notepad and copy all of it. On app01:

```sh
cd ~/Merchant
nano saml/idp-metadata.xml       # paste, save, exit
nano .env                        # add the line below
```

```ini
SAML_IDP_METADATA_FILE=/app/saml/idp-metadata.xml
```

```sh
docker compose -f docker-compose.aws.yml up -d
```

The sign-in page now shows **Sign in with AWS** (change the wording with
`SAML_BUTTON_LABEL`). Sign out of Merchant and try it, or click the Merchant
tile in your AWS access portal.

## 7. Try the rules

* In Merchant, **Admin → Users**: after an AWS sign-in your account shows
  **SSO linked**.
* Add a second Identity Center user and assign them to the app, but don't add
  them in Merchant. Merchant tells them to ask an administrator.
* Add them in Merchant with **Single sign-on only**. They can now get in with
  AWS but not with a password.
* Set `LOCAL_LOGIN_ENABLED=false` in `.env` and run `up -d` to see a sign-on-only
  login page. Set it back to keep a way in if SSO breaks.

## Day-to-day

* **Update Merchant:** `cd ~/Merchant && git pull && docker compose -f docker-compose.aws.yml up -d --build`
* **Logs:** `docker compose -f docker-compose.aws.yml logs -f app`
* **Backups:** db01 writes one each night to `/srv/backups`. They live on
  the same disk and vanish with the instance, so also protect the disk itself:
  **EC2 → Lifecycle Manager → Create lifecycle policy**, target instances
  tagged `Name = merchant-db01`, daily, keep 7. Snapshots of an encrypted disk
  are encrypted too.
* **Updates:** Ubuntu installs security updates automatically every day.
  Reboot now and then (`sudo reboot`) when the login message says one is needed.
* **Closing SSH (optional):** once everything works you can delete the SSH 22
  rules from both security groups and use **Connect → Session Manager**
  instead. That needs the instance role `AmazonSSMManagedInstanceCore`
  (**Actions → Security → Modify IAM role**).
* **Reset an admin password:** `docker compose -f docker-compose.aws.yml exec app flask create-admin`

## Pausing the lab

Servers cost money only while they run. Between sessions, **EC2 →
Instances**, select both → **Instance state → Stop**. To resume, select both →
**Start**, wait two minutes, and open the site. Disks, the Elastic IP and your
sslip.io name all stay the same, so nothing needs changing. Start db01 first if
you start them one at a time.

## Troubleshooting

| Symptom | Check |
|---|---|
| Site doesn't load at all | `merchant-app` allows 80 and 443; the Elastic IP is attached; `docker compose -f docker-compose.aws.yml ps` |
| Certificate error or `ERR_SSL_PROTOCOL_ERROR` | SITE_ADDRESS matches the address bar exactly (app01's Elastic IP, dashes not dots); after fixing it, `up -d --force-recreate`; `docker compose -f docker-compose.aws.yml logs proxy` should say *certificate obtained successfully* |
| `no such file` from `docker compose` | You're not in `~/Merchant`: run `cd ~/Merchant` |
| Connect says *Error establishing SSH connection* | The security group's SSH rule must come from the `ec2-instance-connect` prefix list (step 2) |
| *explicit deny in a service control policy*, or IAM Identity Center greyed out | The account came from the newer settings.aws.com sign-up; see step 1.1 |
| "Waiting for the database" forever | DB_HOST is db01's **private** IP, and you ran `up -d --force-recreate` after changing it; `merchant-db` allows 3306 from `merchant-app`; db01's script ran without errors |
| Attachments fail | `mount | grep merchant` on app01; `merchant-db` allows 2049 from `merchant-app` |
| "Single sign-on couldn't be verified" | `docker compose ... logs app` shows the reason. Usually the ACS URL or audience in Identity Center doesn't match `https://HOST/...` exactly, or the metadata file is from a different app |
| "isn't set up in Merchant yet" | The Merchant user's email must match the Identity Center user's email |
| AWS says you're not assigned | Step 8 of *Add Merchant as an application* |

## Clean up

When you're done, in this order:

1. **EC2 → Instances**: select both → **Instance state → Terminate**.
2. **EC2 → Elastic IPs**: select it → **Release**. An unattached address still costs money.
3. **EC2 → Security Groups**: delete `merchant-app` and `merchant-db`.
4. **IAM Identity Center → Applications**: delete Merchant. You can leave
   Identity Center itself on, since it has no charge.
5. Check **Billing → Bills** a day later to make sure nothing is still running.
