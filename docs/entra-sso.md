# Signing in with Microsoft (Entra ID)

Merchant can show a **Sign in with Microsoft** button so staff use their
college account instead of a separate password. Only people an admin has
already added in Merchant can sign in this way. Nobody gets an account just by
having a college login.

There are two parts: IT registers Merchant in the college's Microsoft tenant
(about 10 minutes), then you copy three values into Merchant's `.env`.

## Part 1: what to ask IT for

Send this section to whoever manages Microsoft Entra ID (formerly Azure AD).

> Please create an app registration for an internal web app called Merchant.
>
> 1. **Entra admin center → Identity → Applications → App registrations → New registration**
>    * Name: `Merchant`
>    * Supported account types: **Accounts in this organizational directory only** (single tenant)
>    * Redirect URI: platform **Web**, value
>      `https://<merchant's address>/login/microsoft/callback`
>      (for testing on a laptop, also add `http://localhost:8000/login/microsoft/callback`)
> 2. **Certificates & secrets → New client secret.** Pick an expiry (for example
>    12 or 24 months) and send us the secret's **Value** (not its ID) securely.
> 3. From **Overview**, send the **Application (client) ID** and the
>    **Directory (tenant) ID**.
> 4. **API permissions:** the default `Microsoft Graph → User.Read` (delegated) is
>    all it needs. No admin consent for anything else.
> 5. Recommended: **Enterprise applications → Merchant → Properties →
>    Assignment required = Yes**, then under **Users and groups** assign the
>    people (or a group) who should use Merchant. Everyone else is stopped by
>    Microsoft before they reach Merchant.
>
> Merchant reads only the standard sign-in claims (`oid`, `tid`,
> `preferred_username`, `email`, `name`). No optional claims are needed.

Microsoft only accepts `https://` redirect addresses, except for `localhost`,
so a shared server needs HTTPS before Microsoft sign-in will work there. See
[split-servers.md](split-servers.md#3-https).

## Part 2: turn it on in Merchant

Add the three values to `.env` on the app server:

```ini
ENTRA_TENANT_ID=<Directory (tenant) ID>
ENTRA_CLIENT_ID=<Application (client) ID>
ENTRA_CLIENT_SECRET=<client secret Value>
```

Restart Merchant (`docker compose up -d` with Docker, or restart the service).
The sign-in page now shows **Sign in with Microsoft** above the password form.

If Merchant sits behind a proxy and Microsoft complains that the redirect URI
doesn't match, either set `TRUSTED_PROXIES=1` (see
[split-servers.md](split-servers.md#3-https)) or spell it out:

```ini
ENTRA_REDIRECT_URI=https://merchant.yourcollege.edu/login/microsoft/callback
```

It must match the redirect URI in the app registration exactly.

## Adding people

Under **Admin → Users → Add user**, enter the person's college email address
(the one they sign in to Microsoft with) and pick a **Sign-in method**:

* **Merchant password (and Microsoft, once it's set up)**: the person gets a
  temporary password and can also use the Microsoft button. Good while you're
  testing.
* **Microsoft only**: no password is set and the password form won't let them
  in. This is the usual choice once Microsoft sign-in works.

The first time someone signs in with Microsoft, Merchant matches them by email
and then remembers their Microsoft account ID, so a later name or email change
in Microsoft doesn't lock them out. The Users list shows **Microsoft linked**
for these people. If you change someone's email in Merchant, the link is
cleared and made again at their next sign-in.

People who aren't in Merchant, or whose account is set to inactive, see
"isn't set up in Merchant yet. Ask an administrator to add you."

## Going Microsoft-only

When every admin has signed in with Microsoft at least once, you can hide the
password form completely:

```ini
LOCAL_LOGIN_ENABLED=false
```

Keep a note of how to undo it. If Microsoft sign-in ever breaks, set it back to
`true`, restart, and use `flask create-admin` to reset an admin password.

## When the client secret expires

Client secrets expire on the date IT chose. Before then, ask IT for a new
secret, replace `ENTRA_CLIENT_SECRET` in `.env` and restart. If it does
expire, the Microsoft button shows "Microsoft sign-in didn't work" and password
sign-in still works (unless you turned it off).

## Testing without the college tenant

Microsoft's free developer sandbox now requires a qualifying paid subscription,
and new standalone tenants usually need a paid Azure subscription or a credit
card. The simplest route is asking IT to create the app registration in the
college tenant with **Assignment required** on and only you assigned, plus the
`http://localhost:8000/login/microsoft/callback` redirect so you can test from
Docker on your own machine.
