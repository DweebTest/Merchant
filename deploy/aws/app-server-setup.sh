#!/bin/bash
# Sets up the APP server (app01) on Ubuntu 24.04: Docker, the attachments
# share from the database server, and a copy of Merchant in ~/Merchant.
#
#   sudo bash app-server-setup.sh <database server private IP>
set -euo pipefail

DB_IP="${1:?Give the private IP address of the database server, e.g. sudo bash app-server-setup.sh 172.31.9.40}"
OWNER="${SUDO_USER:-ubuntu}"
HOME_DIR=$(getent passwd "$OWNER" | cut -d: -f6)
MOUNT=/mnt/merchant-files

echo "== Installing Docker, git and the NFS client"
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q docker.io docker-compose-v2 git nfs-common
usermod -aG docker "$OWNER"

echo "== Adding 1 GB of swap"
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== Mounting the attachments share from $DB_IP"
mkdir -p "$MOUNT"
grep -q " $MOUNT " /etc/fstab || echo "$DB_IP:/srv/merchant-files $MOUNT nfs defaults,_netdev 0 0" >> /etc/fstab
mount -a
touch "$MOUNT/.write-test" 2>/dev/null && rm "$MOUNT/.write-test" && echo "   share is writable" \
  || echo "   (root can't write there, which is expected; the app container can)"

echo "== Getting Merchant"
if [ ! -d "$HOME_DIR/Merchant" ]; then
  sudo -u "$OWNER" git clone https://github.com/DweebTest/Merchant.git "$HOME_DIR/Merchant"
fi
sudo -u "$OWNER" mkdir -p "$HOME_DIR/Merchant/saml"

echo
echo "Done. Next: sign out and back in (so Docker works without sudo), then"
echo "follow 'Configure Merchant' in docs/aws-lab.md."
