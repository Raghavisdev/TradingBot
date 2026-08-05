# Solana Trading & Data Engineering Bot

A production-grade Telegram signal parser, live market snapshot collector, AI decision engine, and automated outcome generator built for 24/7 unattended deployment on Linux VPS.

---

## 🚀 VPS Deployment Instructions

### 1. Clone Repository & Setup Virtual Environment
```bash
git clone <repository_url>
cd TradingBot
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration
```bash
cp .env.example .env
nano .env
```
Fill in mandatory credentials:
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`

### 4. First-Time Interactive Telegram Authorization
Run `main.py` once interactively to enter your phone number and Telegram verification code:
```bash
python main.py
```
After verifying `Authorized: True` and confirming session file creation (`TradingBot.session`), press `Ctrl+C` to stop.

### 5. Systemd Service Setup (Unattended 24/7 Running)
Create systemd service configuration file:
```bash
sudo nano /etc/systemd/system/tradingbot.service
```

Paste the following configuration (adjust path if your user is not `ubuntu`):
```ini
[Unit]
Description=Solana Trading Bot Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/TradingBot
ExecStart=/home/ubuntu/TradingBot/venv/bin/python main.py
Restart=always
RestartSec=5
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
```

Enable and start the systemd service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable tradingbot
sudo systemctl start tradingbot
```

---

## 🛠 Operation & Monitoring Commands

### View Live Service Status
```bash
sudo systemctl status tradingbot
```

### View Application Logs
```bash
# View systemd journal logs
sudo journalctl -u tradingbot -f

# View rotating production file logs
tail -f logs/bot.log
```

### Restart Service
```bash
sudo systemctl restart tradingbot
```

### Stop Service
```bash
sudo systemctl stop tradingbot
```

---

## 📊 Dataset Builder (ML Export)
To build the ML training dataset from collected SQLite snapshots and outcomes:
```bash
python -m analytics.build_dataset
```
This generates `training_dataset.csv`.
