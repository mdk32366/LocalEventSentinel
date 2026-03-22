#!/bin/bash
# =============================================================================
# oracle_cloud_setup.sh
# Run this on a fresh Oracle Cloud (or any Ubuntu 22.04) VM to install and
# configure PNW Event Monitor as a system service.
#
# Usage:
#   chmod +x oracle_cloud_setup.sh
#   ./oracle_cloud_setup.sh
# =============================================================================

set -e

INSTALL_DIR="$HOME/pnw_event_monitor"
SERVICE_NAME="pnw-monitor"
PYTHON="python3"

echo ""
echo "============================================================"
echo "  PNW Event Monitor — Cloud VM Setup"
echo "============================================================"
echo ""

# --- System packages ---
echo "[1/7] Installing system packages..."
sudo apt-get update -q
sudo apt-get install -y python3 python3-pip python3-venv git curl

# --- Create virtualenv ---
echo "[2/7] Creating Python virtual environment..."
cd "$INSTALL_DIR"
$PYTHON -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
deactivate

# --- Create log directory ---
echo "[3/7] Setting up log directory..."
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/data"

# --- Initialize database ---
echo "[4/7] Initializing database..."
cd "$INSTALL_DIR"
venv/bin/python -c "from database import init_db; init_db(); print('  Database OK')"

# --- Install systemd service ---
echo "[5/7] Installing systemd service..."
SERVICE_FILE="$INSTALL_DIR/scripts/pnw-monitor.service"
CURRENT_USER=$(whoami)
VENV_PYTHON="$INSTALL_DIR/venv/bin/python"

# Patch the service file with actual paths
sed "s|User=pi|User=$CURRENT_USER|g" "$SERVICE_FILE" | \
sed "s|WorkingDirectory=/home/pi/pnw_event_monitor|WorkingDirectory=$INSTALL_DIR|g" | \
sed "s|ExecStart=/home/pi/pnw_event_monitor/venv/bin/python|ExecStart=$VENV_PYTHON|g" | \
sed "s|/home/pi/pnw_event_monitor/logs|$INSTALL_DIR/logs|g" \
> /tmp/pnw-monitor.service

sudo cp /tmp/pnw-monitor.service /etc/systemd/system/pnw-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable pnw-monitor

# --- Configure firewall (Oracle Cloud has its own security groups too) ---
echo "[6/7] Configuring firewall..."
if command -v ufw &> /dev/null; then
    sudo ufw allow 22/tcp comment "SSH"
    echo "  UFW: SSH allowed. No inbound ports needed for event monitor."
fi

# --- Summary ---
echo ""
echo "[7/7] Setup complete!"
echo ""
echo "============================================================"
echo "  NEXT STEPS"
echo "============================================================"
echo ""
echo "1. Edit config.yaml with your email and SMTP settings:"
echo "   nano $INSTALL_DIR/config.yaml"
echo ""
echo "2. Test that email works:"
echo "   cd $INSTALL_DIR && venv/bin/python monitor.py scan"
echo "   cd $INSTALL_DIR && venv/bin/python monitor.py test-email"
echo ""
echo "3. Start the service:"
echo "   sudo systemctl start pnw-monitor"
echo ""
echo "4. Check it's running:"
echo "   sudo systemctl status pnw-monitor"
echo "   tail -f $INSTALL_DIR/logs/monitor.log"
echo ""
echo "5. Useful commands from anywhere:"
echo "   cd $INSTALL_DIR && venv/bin/python monitor.py query"
echo "   cd $INSTALL_DIR && venv/bin/python monitor.py status"
echo ""
