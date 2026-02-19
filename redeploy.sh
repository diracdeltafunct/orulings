#!/bin/bash
set -e

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

echo "Running migrations..."
python3 manage.py migrate --noinput

echo "Collecting static files..."
python3 manage.py collectstatic --noinput

echo "Restarting gunicorn..."
sudo systemctl restart gunicorn &
sleep 2

echo "Redeploy complete."
