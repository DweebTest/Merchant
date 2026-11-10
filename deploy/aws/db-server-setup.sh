#!/bin/bash
# Sets up the DATABASE server (db01) on Ubuntu 24.04: MySQL 8 plus a shared
# attachments folder, both reachable only from the app server.
#
#   sudo bash db-server-setup.sh <app server private IP>
#
# Prints the database password at the end; put it in the app server's .env.
set -euo pipefail

APP_IP="${1:?Give the private IP address of the app server, e.g. sudo bash db-server-setup.sh 172.31.5.20}"
DB_NAME=merchant
DB_USER=merchant
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -hex 20)}"
FILES=/srv/merchant-files

echo "== Installing MySQL and the NFS file server"
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q mysql-server nfs-kernel-server

echo "== Adding 1 GB of swap (small instances have little memory)"
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== Letting MySQL accept network connections"
sed -i -E 's/^(bind-address|mysqlx-bind-address)\s*=.*/\1 = 0.0.0.0/' /etc/mysql/mysql.conf.d/mysqld.cnf
systemctl restart mysql

echo "== Creating the database and a user that can only connect from $APP_IP"
mysql <<SQL
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'$APP_IP' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER '$DB_USER'@'$APP_IP' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL ON \`$DB_NAME\`.* TO '$DB_USER'@'$APP_IP';
FLUSH PRIVILEGES;
SQL

echo "== Sharing $FILES with the app server"
mkdir -p "$FILES"
chown 1000:1000 "$FILES"          # the user the Merchant container runs as
chmod 750 "$FILES"
mkdir -p /etc/exports.d
echo "$FILES $APP_IP(rw,sync,no_subtree_check,root_squash)" > /etc/exports.d/merchant.exports
exportfs -ra
systemctl enable --now nfs-server

echo "== Nightly backup of the database and attachments to /srv/backups (keeps 14 days)"
mkdir -p /srv/backups
cat > /etc/cron.daily/merchant-backup <<CRON
#!/bin/sh
day=\$(date +%F)
mysqldump --single-transaction --routines $DB_NAME | gzip > /srv/backups/merchant-\$day.sql.gz
tar -czf /srv/backups/merchant-files-\$day.tar.gz -C $FILES .
find /srv/backups -type f -mtime +14 -delete
CRON
chmod +x /etc/cron.daily/merchant-backup

echo
echo "Done. Put these in the app server's .env:"
echo "  DB_HOST=$(hostname -I | awk '{print $1}')"
echo "  DB_NAME=$DB_NAME"
echo "  DB_USER=$DB_USER"
echo "  DB_PASSWORD=$DB_PASSWORD"
