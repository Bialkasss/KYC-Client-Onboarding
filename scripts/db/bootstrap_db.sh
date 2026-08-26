#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"
find_mysql_client() {
  if [[ -n "${MYSQL_BIN:-}" && -x "$MYSQL_BIN/mysql.exe" ]]; then
    echo "$MYSQL_BIN/mysql.exe"
    return 0
  fi

  local candidates=(
    "/c/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe"
    "/c/Program Files/MySQL/MySQL Server 8.4/bin/mysql.exe"
    "/c/Program Files/MariaDB 11.*/bin/mysql.exe"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if compgen -G "$candidate" > /dev/null; then
      echo $(compgen -G "$candidate" | head -n 1)
      return 0
    fi
  done

  if command -v mysql >/dev/null 2>&1; then
    command -v mysql
    return 0
  fi

  return 1
}

verify_mysql_connection() {
  if ! "$MYSQL_CLIENT" --user="$MYSQL_USER" --password="$MYSQL_PASSWORD" --connect-timeout=5 -e "SELECT 1" >/dev/null 2>&1; then
    echo "Cannot connect to MySQL. Ensure the server is running and credentials are correct."
    exit 1
  fi
  echo "MySQL connection OK."
}

run_sql_file() {
  local mysql_client="$1"
  local sql_file="$2"

  echo "Running $(basename "$sql_file")..."
  "$mysql_client" --user="$MYSQL_USER" --password="$MYSQL_PASSWORD" < "$sql_file"
}

if [[ -z "$MYSQL_PASSWORD" ]]; then
  echo -n "Enter MySQL password for user '$MYSQL_USER': " >/dev/tty
  read -r -s MYSQL_PASSWORD </dev/tty
  echo >/dev/tty
fi

MYSQL_CLIENT="$(find_mysql_client)" || {
  echo "mysql client not found. Set MYSQL_BIN to your MySQL bin directory or add mysql to PATH."
  exit 1
}

echo "Using MySQL client: $MYSQL_CLIENT"
verify_mysql_connection

SQL_DIR="$REPO_ROOT/sql"
run_sql_file "$MYSQL_CLIENT" "$SQL_DIR/00_db_schema.sql"
run_sql_file "$MYSQL_CLIENT" "$SQL_DIR/01_basic_data.sql"
run_sql_file "$MYSQL_CLIENT" "$SQL_DIR/02_more_data.sql"

echo "Database bootstrap completed successfully."

# Optional: replace the SQL-generated sample dataset with a larger, richer
# synthetic dataset (Faker-based) for analysis/ML - opt-in since it truncates
# client/client_address/onboarding_case/document/risk_classification and
# needs Python deps from data_analysis/requirements.txt.
if [[ "${RUN_SANDBOX_GENERATION:-0}" == "1" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-python3}"
  command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
  echo "Running sandbox_generation.py (RUN_SANDBOX_GENERATION=1)..."
  MYSQL_USER="$MYSQL_USER" MYSQL_PASSWORD="$MYSQL_PASSWORD" \
    "$PYTHON_BIN" "$REPO_ROOT/data_analysis/sandbox_generation.py"
  echo "Sandbox dataset generation completed successfully."
else
  echo "Skipping sandbox_generation.py (set RUN_SANDBOX_GENERATION=1 to run it)."
fi

# Populate ML predictions for non-CLOSED cases right after seeding, so they
# show up immediately instead of only after a developer opens/edits a case.
# This is a one-shot batch job (util.RunOpenCasePredictions) - NOT run on
# every app start (see src/KycApiServer.java). Requires the FastAPI ML
# service (data_analysis/app.py) to already be running; skippable via
# RUN_ML_PREDICTIONS=0 if the JDK or ML service aren't available yet.
if [[ "${RUN_ML_PREDICTIONS:-1}" == "1" ]]; then
  if command -v javac >/dev/null 2>&1 && command -v java >/dev/null 2>&1; then
    echo "Compiling and running ML predictions for open cases..."
    mkdir -p "$REPO_ROOT/src/out"
    mapfile -t MAIN_SRC_FILES < <(find "$REPO_ROOT/src" -name "*.java")
    if javac -cp "$REPO_ROOT/src/lib/*" -d "$REPO_ROOT/src/out" "${MAIN_SRC_FILES[@]}" \
        && java -cp "$REPO_ROOT/src/out;$REPO_ROOT/src/lib/*" util.RunOpenCasePredictions; then
      echo "ML prediction step completed."
    else
      echo "Warning: ML prediction step failed - continuing without it."
    fi
  else
    echo "javac/java not found on PATH - skipping ML prediction step (set RUN_ML_PREDICTIONS=0 to silence this)."
  fi
else
  echo "Skipping ML prediction step (RUN_ML_PREDICTIONS=0)."
fi