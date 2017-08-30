#!/bin/bash -e

if [ "$EUID" -ne 0 ]
  then echo "Please run as root"
  exit
fi

set -e
set -x

sudo apt update

if [ ! -f /usr/bin/rpi-update ]; then
    sudo apt install -y rpi-update
    sudo SKIP_WARNING=1 rpi-update
    sudo apt-get -o Dpkg::Options::='--force-confold' --force-yes -fuy dist-upgrade

    reboot

    exit
fi

# Setup ansible
sudo mkdir -p /etc/ansible
echo -e "[local]\nlocalhost ansible_connection=local" | sudo tee /etc/ansible/hosts > /dev/null

if [ ! -f /etc/locale.gen ]; then
  # No locales found. Creating locales with default UK/US setup.
  echo -e "en_GB.UTF-8 UTF-8\nen_US.UTF-8 UTF-8" | sudo tee /etc/locale.gen > /dev/null
  sudo locale-gen
fi

# Install basic dependencies
sudo apt purge -y python-setuptools python-pip python-pyasn1
sudo apt install -y python-dev git-core libffi-dev libssl-dev apt-transport-https
curl -s https://bootstrap.pypa.io/get-pip.py | sudo python
sudo pip install ansible==2.1.0.0

# Clone the source
sudo -u pi git clone https://github.com/enflow-nl/cast-viewer.git /home/pi/cast-viewer
cd /home/pi/cast-viewer

LATEST_TAG=$(git describe --tags `git rev-list --tags --max-count=1`)
sudo -u pi git checkout $LATEST_TAG

cd /home/pi/cast-viewer/ansible
ansible-playbook site.yml

# Cleanup
sudo apt-get autoclean
sudo apt-get clean
sudo find /usr/share/doc -depth -type f ! -name copyright -delete
sudo find /usr/share/doc -empty -delete
sudo rm -rf /usr/share/man /usr/share/groff /usr/share/info /usr/share/lintian /usr/share/linda /var/cache/man
sudo find /usr/share/locale -type f ! -name 'en' ! -name 'de*' ! -name 'es*' ! -name 'ja*' ! -name 'fr*' ! -name 'zh*' -delete
sudo find /usr/share/locale -mindepth 1 -maxdepth 1 ! -name 'en*' ! -name 'de*' ! -name 'es*' ! -name 'ja*' ! -name 'fr*' ! -name 'zh*' -exec rm -r {} \;

# Set a random password
PASSWORD=`head /dev/urandom | tr -dc A-Za-z0-9 | head -c 13 ; echo ''`
echo "$PASSWORD" > /boot/password.txt
echo "pi:$PASSWORD" | chpasswd

reboot
