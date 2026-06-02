# EC2 Deploy

Target repository:

```text
https://github.com/myungjungcrypto/dimae_index
```

Target server:

```text
ec2-user@43.201.222.151
```

## 1. Install runtime

On Amazon Linux 2023:

```bash
sudo dnf update -y
sudo dnf install -y git python3 nodejs npm
sudo npm install -g pm2
```

## 2. Clone repository

```bash
cd /home/ec2-user
git clone https://github.com/myungjungcrypto/dimae_index.git
cd dimae_index
```

## 3. Create `.env`

Do not commit this file.

```bash
cp .env.example .env
nano .env
chmod 600 .env
```

Required values:

```bash
NAVER_CLIENT_ID=your_client_id
NAVER_CLIENT_SECRET=your_client_secret
```

## 4. Initialize data

```bash
python3 -m sentiment_index.cli init-db
python3 -m sentiment_index.cli collect --no-dcinside --verbose
python3 -m sentiment_index.cli score
python3 -m sentiment_index.cli backfill-datalab --days 30
```

## 5. Start PM2 services

```bash
pm2 start ecosystem.config.cjs
pm2 save
pm2 list
```

Services:

- `dimae-index-dashboard`: dashboard at port `8765`
- `dimae-index-hourly-update`: hourly updater, grouped by KST day

## 6. Enable PM2 on reboot

```bash
pm2 startup systemd
```

PM2 prints a `sudo env ... pm2 startup ...` command. Run that printed command once, then:

```bash
pm2 save
```

## 7. Access dashboard with an SSH tunnel

The safest default is to keep TCP `8765` closed in the EC2 security group and access the dashboard through SSH:

```bash
ssh -i ~/downloads/jung_test.pem -L 8765:127.0.0.1:8765 ec2-user@43.201.222.151
```

Then open the local tunnel URL:

```text
http://127.0.0.1:8765
```

If local port `8765` is already in use, use a different local port:

```bash
ssh -i ~/downloads/jung_test.pem -L 8876:127.0.0.1:8765 ec2-user@43.201.222.151
```

Then open `http://127.0.0.1:8876`.

## Useful commands

```bash
pm2 logs dimae-index-dashboard
pm2 logs dimae-index-hourly-update
pm2 restart ecosystem.config.cjs
pm2 stop dimae-index-hourly-update
pm2 delete ecosystem.config.cjs
```
