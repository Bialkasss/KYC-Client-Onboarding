# KYC Client Onboarding System

System for managing client identity verification processes (Know Your Customer - KYC). The project includes a MySQL relational database, a Java relay API server, a Python FastAPI ML/XAI microservice for approval prediction and explainability, and a Vite + React frontend.

---

## 📁 Project Structure

```text
KYC-Client-Onboarding/
├── sql/
│   ├── 00_db_schema.sql           # Creates kyc_db and all tables/keys/relationships
│   ├── 01_basic_data.sql          # Officers, admin officer, document types, baseline clients
│   └── 02_more_data.sql           # Stored-procedure-generated synthetic historical dataset
├── scripts/
│   ├── db/
│   │   ├── _lib.sh                  # Shared MySQL client discovery and password helpers
│   │   ├── bootstrap_db.sh          # Full DB setup: runs sql/*.sql, then optionally seeds ML predictions
│   │   ├── db_dump.sh               # Database backup script
│   │   ├── db_reload.sh             # Restore database from backup
│   │   ├── expiring_docs_report.sh  # Generates expiring_docs_report.csv
│   │   ├── kyc_db_backup.sql        # Database backup file (produced by db_dump.sh)
│   │   └── rebuild_indexes.sh       # Optimizes and rebuilds indexes
│   ├── download-test-libs.ps1       # Downloads JUnit5/Mockito jars into lib/test/
│   └── run-tests.ps1                # Compiles src/+test/ and runs the JUnit suite
├── src/
│   ├── lib/                       # MySQL connector, SLF4J, Logback jars
│   ├── controller/                # HTTP handlers (one per resource)
│   ├── repository/                # JDBC data access
│   ├── service/                   # Business logic (incl. MLPredictionService)
│   ├── util/                      # PasswordHasher, CredentialGenerator, RunOpenCasePredictions, ...
│   ├── openapi.yaml               # OpenAPI 3.0 spec, served live at /openapi.yaml
│   ├── logback.xml                # Logging configuration
│   └── KycApiServer.java          # Lightweight HTTP server (Java relay API), port 8080
├── data_analysis/
│   ├── analysis.ipynb             # Trains the LightGBM approval model, produces kyc_model.pkl
│   ├── sandbox_generation.ipynb   # Synthetic dataset generator (Faker) - notebook form
│   ├── sandbox_generation.py      # Same generator as a standalone script (used by bootstrap_db.sh)
│   ├── app.py                     # FastAPI ML/XAI microservice (predictions, SHAP/DiCE, dashboard plots), port 8000
│   └── requirements.txt           # Python dependencies for the microservice/notebooks
├── frontend/                      # Vite + React app (client/officer/admin portals), port 5173
├── test/                          # JUnit 5 + Mockito tests, mirrors src/ package structure
├── EDB Diagram.pdf                # ERD diagram of the database
├── Project-Brief-02-KYC-...pdf     # Business requirements documentation
├── API_DOCUMENTATION.md           # Full request/response reference for every endpoint
├── SETUP.md                       # Step-by-step developer onboarding guide
└── README.md                      # Project documentation
```
---

## 🛠️ Prerequisites

* **MySQL 8.x** — either MySQL Server 8.0 (standalone) or XAMPP
* **Java Development Kit (JDK 17+)**
* **Python 3.10+** (for the ML/XAI microservice in `data_analysis/`)
* **Node.js & npm** (for the Vite + React frontend)
* **Git Bash** or any Unix-like terminal

---

## 🚀 Setup and Execution Instructions

### 1. MySQL Database Setup

All scripts auto-discover the MySQL client. On a standalone **MySQL Server 8.0** install no extra configuration is needed. On **XAMPP**, set `MYSQL_BIN` once per terminal session before running any script:

```bash
export MYSQL_BIN="/c/xampp/mysql/bin"
```

You can also pre-set credentials to skip the password prompt:

```bash
export MYSQL_USER=root
export MYSQL_PASSWORD=your_password
```

Run the bootstrap script to create the database, apply the schema, and seed test data in one step:

```bash
chmod +x scripts/db/*.sh
./scripts/db/bootstrap_db.sh
```

This runs `sql/00_db_schema.sql`, `sql/01_basic_data.sql`, and `sql/02_more_data.sql` in order. As its last step it also tries to (re)populate ML predictions for all non-CLOSED cases by compiling and running `util.RunOpenCasePredictions` (controlled by `RUN_ML_PREDICTIONS`, default `1`) — this needs the Python microservice (section 3.5) already running with a trained model, so on a brand-new checkout run it first with that step disabled:

```bash
RUN_ML_PREDICTIONS=0 ./scripts/db/bootstrap_db.sh
```

Optionally set `RUN_SANDBOX_GENERATION=1` to replace the small SQL-seeded dataset with a larger, richer synthetic dataset (`data_analysis/sandbox_generation.py`, Faker-based, 10k records by default) — useful before (re)training the ML model.

Re-run bootstrap any time the schema changes — `sql/00_db_schema.sql` drops and recreates the whole database.

---

### 2. Administrative Scripts

All scripts are in `scripts/db/`. They share the same MySQL discovery and password-prompt logic via `_lib.sh`, so `MYSQL_BIN` / `MYSQL_USER` / `MYSQL_PASSWORD` apply to all of them.

* **Backup the database:**
```bash
./scripts/db/db_dump.sh
# Saves to scripts/db/kyc_db_backup.sql
```

* **Restore from backup:**
```bash
./scripts/db/db_reload.sh
# Drops kyc_db, recreates it, and loads scripts/db/kyc_db_backup.sql
```

* **Generate expiring documents CSV report:**
```bash
./scripts/db/expiring_docs_report.sh
# Saves to scripts/db/expiring_docs_report.csv
```

* **Optimize indexes:**
```bash
./scripts/db/rebuild_indexes.sh
```

---

### 3. Java API Server Compilation and Execution

The relay server exposes a local HTTP endpoint that retrieves data directly from the MySQL database.

1. Navigate to the source directory:
```bash
cd src

```


2. Compile the Java server with all dependency jars on the classpath:
```bash
javac -cp "lib/*" -d out $(find . -maxdepth 1 -name "*.java") $(find controller repository service util -name "*.java")

```


3. Run the API server (the working directory must contain `logback.xml`):
* **In Windows environment (Git Bash):**
```bash
java -cp "out;.;lib/*" KycApiServer

```


* **In Linux / macOS environment:**
```bash
java -cp "out:.:lib/*" KycApiServer

```

### 3.5 Python ML/XAI Microservice

A separate FastAPI microservice ([data_analysis/app.py](data_analysis/app.py)) serves case approval predictions, SHAP/DiCE explainability, and the admin dashboard's model diagnostic plots. The Java backend calls it over HTTP (`ML_SERVICE_URL`, default `http://localhost:8000`) and never blocks on it — if it's down, predictions are just skipped/logged.

1. Install dependencies (a venv is recommended):
```bash
cd data_analysis
python -m pip install -r requirements.txt
```

2. **First time only (or to retrain on fresh data):** produce the model artifacts by running [analysis.ipynb](data_analysis/analysis.ipynb) end-to-end (Run All in VS Code/Jupyter). It reads directly from `kyc_db`, so the database must already be bootstrapped, and writes `kyc_model.pkl` + `kyc_train_data.pkl` into `data_analysis/`. Skip this step if those two files already exist.

3. Start the microservice:
```bash
python app.py
```
It listens on `http://localhost:8000` — verify with `curl http://localhost:8000/health`.



---

### 4. Frontend (React) Setup and Execution

The frontend is a Vite + React app in `frontend/` that talks to the Java API server above (default `http://localhost:8080`) and, for admin dashboard plots, directly to the Python microservice (default `http://localhost:8000`, override with `VITE_ML_SERVICE_URL`). Start the API server and the Python microservice first, then run the frontend:

1. Install dependencies (first time only):
```bash
cd frontend
npm install
```

2. Start the dev server:
```bash
npm run dev
```
The app is served at `http://localhost:5173`.

> **Windows PowerShell note:** if `npm run dev` fails because script execution is disabled, use `npm.cmd run dev` instead of `npm run dev`.

By default the frontend calls the API at `http://localhost:8080`. To point it at a different host/port, set `VITE_API_BASE_URL` before starting the dev server, e.g.:
```bash
VITE_API_BASE_URL=http://localhost:9090 npm run dev
```

3. Build for production:
```bash
npm run build
```

---

### 5. Running Tests

Unit and mock tests (JUnit 5 + Mockito) live in `test/`, mirroring the `src/` package structure. There's no Maven/Gradle — dependencies are plain jars and tests run via the JUnit console launcher.

1. One-time setup — download the JUnit5/Mockito jars into `lib/test/`:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\download-test-libs.ps1
```

2. Compile and run the full test suite from the repository root:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\run-tests.ps1
```

This compiles `src/` into `src/out`, compiles `test/` into `testout`, then runs all tests with a tree-style report.

---

### 6. API Documentation, Health Check, and Scheduled Job

* **OpenAPI spec** — `src/openapi.yaml` documents every endpoint below. Once the server is running, fetch it live at `http://localhost:8080/openapi.yaml` and paste it into [Swagger Editor](https://editor.swagger.io) or a local Swagger UI to explore/try the API.
* **Health / readiness check** — `GET http://localhost:8080/health` checks database connectivity and returns `200 {"status":"UP","database":"UP"}` when the service can accept traffic, or `503 {"status":"DOWN", ...}` when the database is unreachable.
* **Scheduled document expiry check** — on server startup, a daemon background job runs automatically at **07:00 local time every day** (and every 24h afterwards), checking for documents expiring within 30 days and logging the result via `logback.xml`. No manual trigger is needed; check the server logs for entries from `service.DocumentExpiryScheduledJob`.

---

### 7. Calling the API (curl examples)

Full request/response reference for every endpoint (with sample JSON) is in [API_DOCUMENTATION.md](API_DOCUMENTATION.md). A few quick examples:

```bash
# List all clients
curl http://localhost:8080/api/clients

# Create a client
curl -X POST http://localhost:8080/api/clients \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Jane Doe","client_type":"INDIVIDUAL","nationality":"GB","country_of_birth":"GB","date_of_birth":"1985-03-14","tax_residency":"GB","status":"PENDING","is_active":false}'
# -> {"message":"Client created successfully","client_id":11}

# Update a case status
curl -X PATCH http://localhost:8080/api/onboarding/cases/1/status \
  -H "Content-Type: application/json" \
  -d '{"case_status":"AWAITING_DOCUMENTS"}'
# -> {"message":"Case status updated successfully","case_id":1,"case_status":"AWAITING_DOCUMENTS"}
```



---

## 🌐 API Endpoints

Full request/response reference (with sample JSON) is in [API_DOCUMENTATION.md](API_DOCUMENTATION.md). Summary of every endpoint:

### Java relay API — `http://localhost:8080`

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| `POST` | `/api/auth/login` | Authenticates a client/compliance officer/admin officer by username+password |
| `GET`  | `/api/clients` | Returns a summary list of all clients |
| `GET`  | `/api/clients/{id}` | Returns the full record for a single client by ID |
| `GET`  | `/api/clients/expiring-documents?days={n}` | Returns documents expiring within the given day window (defaults to 30 days) |
| `POST` | `/api/clients` | Creates a new client |
| `GET`  | `/api/onboarding/cases?status={s}&assigned_officer_id={id}&limit={n}&offset={n}` | Paginated, filterable list of onboarding cases (`{total, offset, limit, cases}`) |
| `GET`  | `/api/onboarding/cases/{id}` | Returns case details, client info, ML prediction/recommendations, and all submitted documents |
| `POST` | `/api/onboarding/cases` | Opens a new onboarding case for an existing client |
| `POST` | `/api/onboarding/cases/open` | Atomically creates client + address + case (+ documents, + officer assignment) in one call, auto-provisioning client login credentials |
| `POST` | `/api/onboarding/cases/predict-all` | Triggers a background bulk ML prediction run over every case (`202 Accepted`) |
| `PATCH` | `/api/onboarding/cases/{id}/status` | Updates the status of a case |
| `PATCH` | `/api/onboarding/cases/{id}/officer` | Assigns or unassigns the compliance officer handling a case |
| `PATCH` | `/api/onboarding/cases/{id}/risk-classification` | Records a new risk classification for a case |
| `POST` | `/api/onboarding/cases/{id}/documents` | Submits a new document for a case |
| `PATCH` | `/api/onboarding/cases/{id}/documents/{docId}/verify` | Marks a case document as verified |
| `GET`  | `/api/officers` | Lists compliance officers (`officer_id`, `full_name`) |
| `GET`  | `/api/document-types` | Lists document types (`doc_type_id`, `doc_type_name`) |
| `GET`  | `/health` | Readiness check — reports whether the service and database can accept traffic |
| `GET`  | `/openapi.yaml` | Machine-readable OpenAPI 3.0 spec for all endpoints |

### Python ML/XAI microservice — `http://localhost:8000`

Called by the Java backend (prediction endpoints) and directly by the frontend admin dashboard (plot endpoints). See [data_analysis/app.py](data_analysis/app.py).

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| `GET`  | `/health` | Liveness check |
| `POST` | `/api/v1/predict-and-explain` | Predicts APPROVED/REJECTED for a case + DiCE recommendations when rejected |
| `POST` | `/api/v1/explain/shap-plot` | Local SHAP bar plot (base64 PNG) for a single case |
| `GET`  | `/api/v1/explain/feature-importance-plot` | Bar plot of top features driving approval decisions (base64 PNG) |
| `GET`  | `/api/v1/eval/confusion-matrix-plot` | Confusion matrix on the held-out test split (base64 PNG) |
| `GET`  | `/api/v1/eval/roc-curve-plot` | ROC curve on the held-out test split (base64 PNG) |
| `GET`  | `/api/v1/eval/approval-rate-plot` | Historical approved-vs-rejected bar chart (base64 PNG) |
| `GET`  | `/api/v1/eval/probability-distribution-plot` | Histogram of predicted approval probabilities (base64 PNG) |
| `GET`  | `/api/v1/eval/top-rejection-factors-plot` | Most common DiCE-recommended factors across sampled rejected cases (base64 PNG) |
| `POST` | `/api/v1/debug/echo` | Debug-only: echoes back the raw request body/headers |