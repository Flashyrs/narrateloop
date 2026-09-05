#!/bin/bash
set -e

echo "⚙️ Configuring Nginx reverse proxy for narrateloop.duckdns.org..."
sudo cp /home/ubuntu/narrateloop/scripts/nginx_narrateloop.conf /etc/nginx/sites-available/narrateloop
sudo ln -sf /etc/nginx/sites-available/narrateloop /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t
sudo systemctl restart nginx
echo "✅ Nginx restarted successfully."

# Setup DuckDNS cron updater
echo "⚙️ Setting up DuckDNS cron updater..."
mkdir -p /home/ubuntu/duckdns
cat << 'CRON_EOF' > /home/ubuntu/duckdns/duck.sh
#!/bin/bash
echo url="https://www.duckdns.org/update?domains=narrateloop&token=4f253800-f3a1-4a47-914b-2d49892547fc&ip=" | curl -k -o /home/ubuntu/duckdns/duck.log -K -
CRON_EOF
chmod 700 /home/ubuntu/duckdns/duck.sh
/home/ubuntu/duckdns/duck.sh

(crontab -l 2>/dev/null | grep -v "duckdns" ; echo "*/5 * * * * /home/ubuntu/duckdns/duck.sh >/dev/null 2>&1") | crontab -
echo "✅ DuckDNS updater active in crontab."

# Obtain Let's Encrypt SSL Certificate
echo "🔒 Requesting Let's Encrypt SSL Certificate for narrateloop.duckdns.org..."
sudo certbot --nginx -d narrateloop.duckdns.org --non-interactive --agree-tos -m flashyrs@gmail.com --redirect || echo "⚠️ Certbot challenge will retry if DNS is propagating."

echo "🚀 Setup complete! Visit https://narrateloop.duckdns.org"
