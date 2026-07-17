#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/jpk/repos/BB-Study"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="bb-study"
PORT="5164"
RUN_USER="jpk"
RUN_GROUP="jpk"

if [[ $EUID -ne 0 ]]; then
    echo "Run this script with sudo:"
    echo "  sudo bash $0"
    exit 1
fi

if [[ ! -d "$APP_DIR" ]]; then
    echo "Application directory not found: $APP_DIR"
    exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "Python virtual environment not found: $VENV_DIR"
    exit 1
fi

echo "Installing Gunicorn in the virtual environment..."
"$VENV_DIR/bin/python" -m pip install --upgrade gunicorn

# Detect a likely Flask application module.
if [[ -f "$APP_DIR/wsgi.py" ]]; then
    APP_MODULE="wsgi:app"
elif [[ -f "$APP_DIR/app.py" ]]; then
    APP_MODULE="app:app"
elif [[ -f "$APP_DIR/main.py" ]]; then
    APP_MODULE="main:app"
elif [[ -f "$APP_DIR/run.py" ]]; then
    APP_MODULE="run:app"
else
    echo "Could not detect the Flask entry point."
    echo
    echo "Expected one of:"
    echo "  $APP_DIR/wsgi.py containing: app = ..."
    echo "  $APP_DIR/app.py containing: app = ..."
    echo "  $APP_DIR/main.py containing: app = ..."
    echo "  $APP_DIR/run.py containing: app = ..."
    exit 1
fi

echo "Using Flask application: $APP_MODULE"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=BB Study Flask Application
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${APP_DIR}

Environment="PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"

ExecStart=${VENV_DIR}/bin/gunicorn \\
    --workers 2 \\
    --bind 0.0.0.0:${PORT} \\
    --access-logfile - \\
    --error-logfile - \\
    --timeout 120 \\
    ${APP_MODULE}

Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd..."
systemctl daemon-reload

echo "Enabling service at startup..."
systemctl enable "$SERVICE_NAME"

echo "Starting service..."
systemctl restart "$SERVICE_NAME"

echo
echo "Service status:"
systemctl --no-pager --full status "$SERVICE_NAME"

echo
echo "The application should be available at:"
echo "  http://SERVER_IP:${PORT}"
echo
echo "Monitor its logs with:"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
