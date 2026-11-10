# Security review (November 2026)

A review of Merchant and the AWS lab setup before putting it in the cloud.
It covered sign-in, sessions and permissions; entries, search, attachments
and reports; the libraries Merchant uses; and the Docker, server and AWS
setup.

## Fixed

| Issue | Risk | Fix |
|---|---|---|
| Deactivating someone didn't sign them out. Their session, and a "keep me signed in" cookie that lasted a year, kept working. | High | Each person now has a session token. Deactivating them, resetting or changing their password, or changing their email or sign-in method ends all their sessions. "Keep me signed in" now lasts 14 days (`REMEMBER_DAYS`). |
| A sign-in link with `next=/\evil.example` could send people to another site after signing in. | Medium | One shared, stricter check for every redirect after sign-in. |
| Several libraries had published vulnerabilities (Flask, cryptography, python-dotenv, pytest). | Medium | Upgraded. `pip-audit` now reports none. |
| No Content Security Policy, so a future bug that let someone inject HTML could also run scripts. | Low | Added a strict policy (scripts only from Merchant itself) and moved the little bit of inline JavaScript into `static/js/ui.js`. Also added HSTS on HTTPS setups, a Permissions-Policy, and no caching of signed-in pages. |

Everyone has to sign in again once after this update.

## Checked and fine

* **Attachments:** stored under random names, outside the web folder, with an
  allowed list of file types, and always downloaded rather than opened in
  the browser.
* **Database:** all queries go through SQLAlchemy, and search terms are
  escaped, so no SQL injection.
* **Pages and PDFs:** text people type is escaped in pages and in reports.
* **Forms:** every form has CSRF protection. The only exception is the SAML
  return address, which is protected by its signed assertion instead.
* **Passwords:** hashed with scrypt, with lockout after repeated failures.
* **Single sign-on:** Microsoft sign-in checks state and tenant; SAML requires
  signed assertions, the right audience and a request Merchant started. Only
  people an administrator added can get in.
* **Permissions:** admin pages check for administrators; people can only edit
  or delete their own entries unless they're an administrator.
* **Docker:** the app runs as an ordinary user, not root. In the AWS setup only
  Caddy is reachable from outside.

## Known, not fixed (low risk)

* **No limit per IP address on sign-in attempts.** Lockout stops guessing one
  account, but someone could try one common password across many accounts,
  or lock a person out on purpose. Using single sign-on with MFA avoids
  both. A limit in Caddy or the app could be added later.
* **Small hints that an account exists**, such as the "locked" message.
* **A captured SAML response could be replayed** within its few-minute
  lifetime. That needs someone to intercept HTTPS traffic first.
* **Traffic between the servers isn't encrypted** (MySQL and NFS). That's
  fine inside one AWS VPC. On the college network, consider MySQL over TLS.
* **The local `docker-compose.yml` listens on all network interfaces** on
  port 8000. Fine on a laptop. Don't use that file on a shared server.
* **sslip.io** is a free third-party name service. Use a real college domain
  for anything beyond the lab.

## Before going live

- [ ] A new random `SECRET_KEY`, and `chmod 600 .env`
- [ ] HTTPS only (`SESSION_COOKIE_SECURE=true`, which the AWS setup sets)
- [ ] No demo data (`flask demo-data clear`)
- [ ] Disks encrypted and IMDSv2 required (see the AWS guide)
- [ ] Backups copied off the database server, and a restore tested once
- [ ] Root account has MFA and isn't used day to day
- [ ] SSH limited to your IP, or closed in favour of Session Manager
- [ ] Single sign-on working, with one local admin kept as a way back in
- [ ] Run `pip-audit -r requirements.txt` before each update
