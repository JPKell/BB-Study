#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-bb-study}"
APP_DIR="${APP_DIR:-/home/jpk/repos/BB-Study}"
KEY_NAME="${KEY_NAME:-bb-study_ed25519}"

if [[ $EUID -ne 0 ]]; then
    echo "Run this script as root so it can configure the web service user:"
    echo "  sudo bash $0"
    exit 1
fi

RUN_USER="$(systemctl show "$SERVICE_NAME" --property=User --value 2>/dev/null || true)"
if [[ -z "$RUN_USER" ]]; then
    echo "Could not determine the user for ${SERVICE_NAME}.service."
    exit 1
fi

RUN_GROUP="$(id -gn "$RUN_USER")"
USER_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
if [[ -z "$USER_HOME" || ! -d "$USER_HOME" ]]; then
    echo "Could not determine a valid home directory for user ${RUN_USER}."
    exit 1
fi

SSH_DIR="$USER_HOME/.ssh"
KEY_PATH="$SSH_DIR/$KEY_NAME"
PUBLIC_KEY_PATH="${KEY_PATH}.pub"

install -d -m 700 -o "$RUN_USER" -g "$RUN_GROUP" "$SSH_DIR"

if [[ -e "$KEY_PATH" || -e "$PUBLIC_KEY_PATH" ]]; then
    if [[ ! -f "$KEY_PATH" || ! -f "$PUBLIC_KEY_PATH" ]]; then
        echo "Only one part of the key pair exists at ${KEY_PATH}; refusing to overwrite it."
        exit 1
    fi
    echo "Using existing SSH key: $KEY_PATH"
else
    echo "Creating a dedicated SSH key for web service user ${RUN_USER}..."
    runuser -u "$RUN_USER" -- env HOME="$USER_HOME" \
        ssh-keygen -q -t ed25519 -N "" -C "${SERVICE_NAME}@$(hostname)" -f "$KEY_PATH"
fi

chmod 600 "$KEY_PATH"
chmod 644 "$PUBLIC_KEY_PATH"
chown "$RUN_USER:$RUN_GROUP" "$KEY_PATH" "$PUBLIC_KEY_PATH"

ORIGIN_URL="$(git -C "$APP_DIR" remote get-url origin)"
if [[ "$ORIGIN_URL" =~ ^https://github\.com/([^/]+/[^/]+)$ ]]; then
    REPOSITORY_PATH="${BASH_REMATCH[1]%.git}"
    SSH_ORIGIN="git@github.com:${REPOSITORY_PATH}.git"
    git -C "$APP_DIR" remote set-url origin "$SSH_ORIGIN"
    echo "Changed origin to: $SSH_ORIGIN"
elif [[ "$ORIGIN_URL" == git@github.com:* ]]; then
    echo "Origin already uses SSH: $ORIGIN_URL"
else
    echo "Origin is not a recognized GitHub HTTPS URL; leaving it unchanged: $ORIGIN_URL"
fi

# Keep this key repository-specific rather than changing SSH behavior for the user.
git -C "$APP_DIR" config core.sshCommand \
    "ssh -i $KEY_PATH -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
chown "$RUN_USER:$RUN_GROUP" "$APP_DIR/.git/config"

echo
echo "Add the following PUBLIC key to GitHub:"
echo
cat "$PUBLIC_KEY_PATH"
echo
echo "For this repository, add it under:"
echo "  GitHub repository > Settings > Deploy keys > Add deploy key"
echo "Enable \"Allow write access\" so the navbar button can push."
echo
echo "After adding the key, verify it with:"
echo "  sudo -u $RUN_USER git -C $APP_DIR push --dry-run origin HEAD"
