#!/bin/bash
set -e

# Usage: ./redeploy.sh [service_name]
# Default service is "gunicorn" (production)
SERVICE_NAME="${1:-gunicorn}"

# Activate virtual environment
source .venv/bin/activate

BACKUP_DIR="backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

echo "Creating backup directory..."
mkdir -p "$BACKUP_DIR"

echo "Backing up databases..."
for dbfile in db.sqlite3 dbproduction.sqlite3; do
    if [ -f "$dbfile" ]; then
        cp "$dbfile" "$BACKUP_DIR/${dbfile%.sqlite3}_$TIMESTAMP.sqlite3"
        echo "Backed up $dbfile to $BACKUP_DIR/${dbfile%.sqlite3}_$TIMESTAMP.sqlite3"
    fi
done

echo "updating requirements"
pip install -r requirements.txt

echo "Running migrations..."
python3 manage.py migrate --noinput

echo "Collecting static files..."
python3 manage.py collectstatic --noinput

echo "Restarting $SERVICE_NAME..."
sudo systemctl restart "$SERVICE_NAME" &
disown
sleep 2

echo "Redeploy complete."
