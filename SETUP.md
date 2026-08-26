# KYC Client Onboarding System: Developer Onboarding Guide

Welcome to the **KYC Client Onboarding System** project! This guide will help you set up your local development environment, build the backend and database, and run the full stack in **under 15 minutes**.

---

## ⏱️ Quick Start Checklist (Under 15 Minutes)

1. **Prerequisites Verification** (~2 mins)
2. **Database Bootstrapping** (~2 mins)
3. **Python ML/XAI Microservice Setup & Startup** (~5 mins, first time only for model training)
4. **Backend API Server Compilation & Startup** (~2 mins)
5. **Running Automated Tests** (~2 mins)
6. **Frontend Development Server Startup** (~2 mins)

---

## 🛠️ Step 1: Prerequisites

Ensure you have the following installed on your machine:

* **MySQL 8.x** (Standalone MySQL Server 8.0 or XAMPP)
* **Java Development Kit (JDK 17+)**
* **Python 3.10+** (for the ML/XAI microservice, `data_analysis/`)
* **Node.js & npm** (for the Vite + React frontend)
* **Git Bash** or any Unix-like terminal (recommended for Windows users)

---

## 🗄️ Step 2: MySQL Database Setup

1. If using **XAMPP**, configure your MySQL binary path in your terminal session:
```bash
export MYSQL_BIN="/c/xampp/mysql/bin"
```


2. (Optional) Set your credentials to bypass prompts:
```bash
export MYSQL_USER=root
export MYSQL_PASSWORD=your_password
```


3. Run the automated bootstrap script to create the database (`kyc_db`), apply the DDL schema, load stored procedures/views, and seed initial test data:
```bash
chmod +x scripts/db/*.sh
./scripts/db/bootstrap_db.sh
```

The script runs `sql/00_db_schema.sql`, `sql/01_basic_data.sql`, and `sql/02_more_data.sql` in order. As its **last step it also tries to populate ML predictions** for all non-CLOSED cases (`RUN_ML_PREDICTIONS=1` by default) — this requires the Python ML microservice from Step 3 to already be running with a trained model. On a brand-new checkout neither exists yet, so for the *first* run, disable that step:
```bash
RUN_ML_PREDICTIONS=0 ./scripts/db/bootstrap_db.sh
```
Once Step 3 is done (model trained, `app.py` running), you can re-run `./scripts/db/bootstrap_db.sh` normally, or just re-run the prediction step on its own (see Step 3.4).

> Optional: set `RUN_SANDBOX_GENERATION=1` to replace the small SQL-seeded dataset with a larger, richer synthetic dataset (`data_analysis/sandbox_generation.py`) — useful before (re)training the ML model in Step 3.

---

## 🤖 Step 3: Python ML/XAI Microservice Setup & Startup

The compliance-officer/admin dashboards and case ML predictions are served by a separate FastAPI microservice (`data_analysis/app.py`), not the Java backend. It needs a trained model file before it can start.

1. Install dependencies:
```bash
cd data_analysis
pip install -r requirements.txt
```

2. **Train the model (only needed once, or whenever you want to retrain on fresh data)** — the model is produced by `data_analysis/analysis.ipynb`, which reads directly from the `kyc_db` MySQL database, so the DB must already be seeded (Step 2):
   * Open `data_analysis/analysis.ipynb` in VS Code (or Jupyter) and **Run All** cells.
   * This produces `kyc_model.pkl` and `kyc_train_data.pkl` in `data_analysis/`, which `app.py` loads on startup.
   * If these two files already exist (e.g. from a teammate or a previous run) you can skip this step.

3. Start the microservice:
```bash
python app.py
```
It listens on `http://localhost:8000`. Verify it's up:
```bash
curl http://localhost:8000/health
```

4. (Optional) Now that the model + service are ready, (re-)populate ML predictions for existing non-CLOSED cases without re-running the whole DB bootstrap:
```bash
cd ..
javac -cp "src/lib/*" -d src/out $(find src -name "*.java")
java -cp "src/out;src/lib/*" util.RunOpenCasePredictions
```

---

## ☕ Step 4: Java API Server Startup

1. Navigate to the source directory:
```bash
cd src
```


2. Compile the Java server classes with all dependencies on the classpath:
```bash
javac -cp "lib/*" -d out $(find . -maxdepth 1 -name "*.java") $(find controller repository service util -name "*.java")
```


3. Start the API server (ensure your working directory contains `logback.xml`):
* **Windows (Git Bash):**
```bash
java -cp "out;.;lib/*" KycApiServer
```


* **Linux / macOS:**
```bash
java -cp "out:.:lib/*" KycApiServer
```




4. Verify the server is running by hitting the health check endpoint in a new terminal:
```bash
curl http://localhost:8080/health
```



---

## 🧪 Step 5: Running the Test Suite

Unit and mock tests (JUnit 5 + Mockito) verify the domain logic (such as risk classification rules and case state transitions).

1. Download test libraries (one-time setup):
```powershell
powershell -ExecutionPolicy Bypass -File scripts\download-test-libs.ps1
```


2. Run the test suite from the repository root:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\run-tests.ps1
```



---

## 💻 Step 6: Frontend (React) Setup & Execution

1. Open a new terminal and navigate to the frontend directory:
```bash
cd frontend
```


2. Install dependencies (first time only):
```bash
npm install
```


3. Start the development server:
```bash
npm run dev
```


* *Note for Windows PowerShell users:* If script execution is restricted, use `npm.cmd run dev`.


4. Access the user interface in your browser at `http://localhost:5173`. It automatically communicates with the backend API running at `http://localhost:8080`, which in turn calls the Python ML microservice at `http://localhost:8000` for case predictions/recommendations (Step 3) — the admin dashboard also calls the ML microservice directly for its charts.

---

## 📞 Quick API Verification (`curl`)

You can test core endpoints immediately after starting the backend:

* **List all clients:**
```bash
curl http://localhost:8080/api/clients
```


* **Check expiring documents:**
```bash
curl http://localhost:8080/api/clients/expiring-documents?days=30
```



