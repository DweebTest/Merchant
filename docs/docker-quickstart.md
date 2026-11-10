# Try Merchant on your computer with Docker

This guide is for someone who has never used Docker. It takes about 20
minutes, most of it waiting for downloads.

**What Docker does here:** it runs two small, self-contained "containers" on
your computer: one with the MySQL database and one with the Merchant web app.
You don't install MySQL or Python yourself, and removing them later leaves
nothing behind.

## 1. Install Docker Desktop

1. Go to https://www.docker.com/products/docker-desktop/ and download Docker
   Desktop for your system (Windows or Mac).
2. Run the installer and accept the defaults. On Windows it may ask to enable
   WSL 2 and restart. Say yes.
3. Open **Docker Desktop**. You can skip signing in. Wait until the bottom-left
   corner says **Engine running**.

> On a college-managed computer you may need IT to install Docker Desktop
> for you, because it needs administrator rights.

## 2. Download the Merchant code

1. Go to the code on GitHub (signed in):
   https://github.com/DweebTest/Merchant
2. Click the green **Code** button, then **Download ZIP**.
   (Until step 1 is merged, first switch the branch dropdown at the top-left
   from `main` to `step-1-database-login-groups`.)
3. Unzip it somewhere easy to find, such as `C:\Merchant` or your Documents
   folder. Make sure you open the unzipped folder that contains
   `docker-compose.yml`.

## 3. Create your settings file

The app reads its passwords from a file named `.env`.

1. In the Merchant folder, find `.env.example`. Make a copy and rename the copy
   to exactly `.env` (nothing before the dot).
   *Windows tip:* in File Explorer turn on **View → Show → File name
   extensions**, so Notepad doesn't secretly save it as `.env.txt`.
2. Open `.env` in Notepad (or TextEdit on a Mac) and fill in these three lines.
   Any values work for testing; just don't leave them blank:

   ```
   SECRET_KEY=type-a-long-random-string-of-at-least-40-characters-here
   DB_PASSWORD=pick-a-database-password
   MYSQL_ROOT_PASSWORD=pick-a-different-password
   ```

3. Save and close. Leave every other line as it is.

## 4. Start Merchant

1. Open a terminal in the Merchant folder:
   * **Windows:** open the folder in File Explorer, click the address bar,
     type `powershell` and press Enter.
   * **Mac:** right-click the folder in Finder and choose
     **New Terminal at Folder**.
2. Type this and press Enter:

   ```
   docker compose up -d --build
   ```

   The first run downloads MySQL and Python and takes a few minutes. When it
   finishes you'll see `Container ... Started` lines.

3. Create your administrator account:

   ```
   docker compose exec app flask create-admin
   ```

   It asks for your email, a display name and a password (at least 10
   characters; nothing shows on screen while you type the password, which is
   normal).

4. Open http://localhost:8000 in your browser and sign in.

## Everyday commands

Run these in the same Merchant folder.

| To | Type |
|---|---|
| Stop Merchant (your data is kept) | `docker compose down` |
| Start it again | `docker compose up -d` |
| See what's running | `docker compose ps` |
| See the app's log if something looks wrong | `docker compose logs app` |
| Update after downloading new code | `docker compose up -d --build` |
| **Erase everything** and start fresh | `docker compose down -v` |

You can also start and stop the containers from the **Containers** tab in
Docker Desktop.

## If something goes wrong

* **"docker is not recognized" or "cannot connect to the Docker daemon"**:
  Docker Desktop isn't running. Open it and wait for **Engine running**.
* **"Set DB_PASSWORD in .env"**: the `.env` file is missing, misnamed
  (`.env.txt`), or that line is blank.
* **"port is already allocated"**: something else uses port 8000. In
  `docker-compose.yml` change `"8000:8000"` to `"8080:8000"` and use
  http://localhost:8080.
* **The page doesn't load right after starting**: wait 30 seconds; the
  database takes a moment on first start. Check `docker compose logs app`.
* **Forgot the admin password**: run `docker compose exec app flask create-admin`
  again with the same email to set a new one.
