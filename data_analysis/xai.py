# Note the empty space between root: and @
DATABASE_URL = "mysql+pymysql://root:@localhost:3306/kyc_db"

# engine = create_engine(DATABASE_URL)
# DATABASE_URL = "jdbc:mysql://localhost:3306/kyc_db"
engine = create_engine(DATABASE_URL)

sql_query_client = text("""SELECT * FROM client;""")
sql_query_cases = text("""SELECT * FROM onboarding_case;""")
sql_query_documents = text("""SELECT * FROM document;""")
sql_query_addresses = text("""SELECT * FROM client_address;""")
sql_query_risk = text("""SELECT * FROM risk_classification;""")


with engine.connect() as conn:
    df_clients = pd.read_sql(sql_query_client, con=conn)
    df_cases = pd.read_sql(sql_query_cases, con=conn)
    df_documents = pd.read_sql(sql_query_documents,con=conn )
    df_addresses = pd.read_sql(sql_query_addresses,con=conn )
    df_risk = pd.read_sql(sql_query_risk, con=conn)

# ---------------------------------------------------------
# 2. FEATURE ENGINEERING & AGGREGATIONS
# ---------------------------------------------------------
# Convert dates
df_clients["date_of_birth"] = pd.to_datetime(df_clients["date_of_birth"])
df_documents["expiry_date"] = pd.to_datetime(df_documents["expiry_date"])
today = pd.to_datetime("today")

# Compute Client Age
df_clients["age"] = (today - df_clients["date_of_birth"]).dt.days // 365

# Aggregate Document-level stats per case
doc_aggregations = df_documents.groupby("case_id").agg(
    total_docs_submitted=("doc_id", "count"),
    verified_docs_count=("verified_flag", "sum"),
    expired_docs_count=("expiry_date", lambda dates: (dates < today).sum()),
    has_unverified_docs=("verified_flag", lambda flags: int((~flags).any()))
).reset_index()

# Check cross-border address vs tax residency
# Drop columns from a previous run of this cell so the merge stays idempotent
df_clients = df_clients.drop(columns=["address_country", "is_cross_border"], errors="ignore")

df_address_primary = df_addresses[df_addresses["address_type"] == "REGISTERED"].drop_duplicates("client_id")
df_clients = df_clients.merge(
    df_address_primary[["client_id", "country"]].rename(columns={"country": "address_country"}),
    on="client_id",
    how="left"
)
df_clients["is_cross_border"] = (df_clients["tax_residency"] != df_clients["address_country"]).astype(int)


# ---------------------------------------------------------
# 3. MERGE INTO A SINGLE ANALYTICAL / ML DATAFRAME
# ---------------------------------------------------------
# Base merge: case -> client
df_analysis = df_cases.merge(
    df_clients,
    on="client_id",
    how="inner",
    suffixes=("_case", "_client")
)

# Merge document aggregations
df_analysis = df_analysis.merge(
    doc_aggregations,
    on="case_id",
    how="left"
)

# Fill any missing doc aggregations (cases with 0 docs)
df_analysis["total_docs_submitted"] = df_analysis["total_docs_submitted"].fillna(0).astype(int)
df_analysis["verified_docs_count"] = df_analysis["verified_docs_count"].fillna(0).astype(int)
df_analysis["expired_docs_count"] = df_analysis["expired_docs_count"].fillna(0).astype(int)
df_analysis["has_unverified_docs"] = df_analysis["has_unverified_docs"].fillna(1).astype(int)

# Target Variable: 1 = APPROVED , 0 = REJECTED
df_analysis["is_approved"] = (df_analysis["status"] == "APPROVED").astype(int)

# ---------------------------------------------------------
# 4. SELECT CLEAN ML/ANALYTICS FEATURE SET
# ---------------------------------------------------------
feature_columns = [
    # Demographics & Entity Info
    "client_type",
    "nationality",
    "jurisdiction_risk",
    "age",
    "annual_income_band",
    "main_source_of_funds",
    "is_pep",
    "adverse_media_hits",
    "is_cross_border",
    # Case & Application Scope
    "product_type",
    # Compliance & Verification Levers
    "total_docs_submitted",
    "verified_docs_count",
    "expired_docs_count",
    "has_unverified_docs",
    # Target
    "is_approved"
]

df_ml = df_analysis[feature_columns].copy()

# ---------------------------------------------------------
# 5. QUICK DATA AUDIT & INSPECTION
# ---------------------------------------------------------
print(f"Shape of flattened dataset: {df_ml.shape}")
print("\n--- CLASS BALANCE (Target: is_approved) ---")
print(df_ml["is_approved"].value_counts(normalize=True).round(3))

print("\n--- SAMPLE ROWS ---")
print(df_ml.head(3).T)

print("\n--- APPROVAL RATE BY JURISDICTION RISK ---")
print(df_ml.groupby("jurisdiction_risk")["is_approved"].mean().round(3))




df = df_ml
# ---------------------------------------------------------
# 1. PREPARE RAW DATA & ORDINAL MAPPINGS
# ---------------------------------------------------------
income_map = {"<25K": 0, "25-50K": 1, "50-100K": 2, "100-250K": 3, "250K+": 4}
risk_map = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

df["annual_income_band_encoded"] = (
    df["annual_income_band"].map(income_map).fillna(0).astype(int)
)
df["jurisdiction_risk_encoded"] = (
    df["jurisdiction_risk"].map(risk_map).fillna(0).astype(int)
)

target = "is_approved"
X = df.drop(
    columns=[target, "annual_income_band", "jurisdiction_risk"]
)  # drop raw text versions
y = df[target]

# Define feature groups for ColumnTransformer
one_hot_cols = ["client_type", "main_source_of_funds"]
high_cardinality_cols = ["nationality", "product_type"]
pass_through_cols = [
    "age",
    "adverse_media_hits",
    "is_pep",
    "is_cross_border",
    "total_docs_submitted",
    "verified_docs_count",
    "expired_docs_count",
    "has_unverified_docs",
    "annual_income_band_encoded",
    "jurisdiction_risk_encoded",
]

# ---------------------------------------------------------
# 2. DEFINE COLUMN TRANSFORMER & FULL PIPELINE
# ---------------------------------------------------------
preprocessor = ColumnTransformer(
    transformers=[
        (
            "one_hot",
            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
            one_hot_cols,
        ),
        (
            "target_enc",
            TargetEncoder(smooth="auto", cv=5),
            high_cardinality_cols,
        ),
        ("num_passthrough", "passthrough", pass_through_cols),
    ]
)

clf = lgb.LGBMClassifier(
    n_estimators=150,
    learning_rate=0.03,
    # Scale down tree complexity
    num_leaves=15,  # Reduced from 31 to prevent early split exhaustion
    max_depth=4,  # Shallower trees for tabular rules
    min_child_samples=30,  # Prevents splitting on tiny subsets
    # Balance the 87% / 13% approval vs rejection skew
    class_weight="balanced",  # Automatically adjusts loss weights inversely proportional to class frequencies
    # Feature & row sampling to encourage diverse splits
    subsample=0.8,
    colsample_bytree=0.8,
    verbose=1,
    # Suppress verbose warnings
    random_state=42,
)

# Bundle preprocessor and LightGBM model together
pipeline = Pipeline(
    steps=[
        ("preprocessor", preprocessor),
        (
            "classifier",
            clf,
        ),
    ]
)



# ---------------------------------------------------------
# 3. SPLIT & TRAIN
# ---------------------------------------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)


# The pipeline automatically transforms X_train and fits the LightGBM classifier
pipeline.fit(X_train, y_train)


## FIX FEATURE NAMES
# Extract the adequate feature names
# feature_names = preprocessor.get_feature_names_out()
# X_train = pd.DataFrame(X_train, columns=feature_names) #REANAME COLUMNS

# ---------------------------------------------------------
# 4. EVALUATE
# ---------------------------------------------------------
y_pred = pipeline.predict(X_test)
y_proba = pipeline.predict_proba(X_test)[:, 1]

print("=== CLASSIFICATION REPORT ===")
print(classification_report(y_test, y_pred, target_names=["REJECTED", "APPROVED"]))
print(f"ROC-AUC Score: {roc_auc_score(y_test, y_proba):.4f}")


# 1. Standard Classification Metrics
print("=== CLASSIFICATION REPORT ===")
print(classification_report(y_test, y_pred, target_names=["REJECTED", "APPROVED"]))

roc_auc = roc_auc_score(y_test, y_proba)
loss = log_loss(y_test, y_proba)
print(f"ROC-AUC Score: {roc_auc:.4f}")
print(f"Log Loss:      {loss:.4f}")

# 2. Confusion Matrix & ROC Curve Plots
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Confusion Matrix
cm = confusion_matrix(y_test, y_pred)
sns.heatmap(
    cm,
    annot=True,
    fmt="d",
    cmap="Blues",
    xticklabels=["REJECTED", "APPROVED"],
    yticklabels=["REJECTED", "APPROVED"],
    ax=axes[0],
)
axes[0].set_title("Confusion Matrix")
axes[0].set_ylabel("Actual Status")
axes[0].set_xlabel("Predicted Status")

# ROC Curve
fpr, tpr, _ = roc_curve(y_test, y_proba)
axes[1].plot(fpr, tpr, color="darkorange", lw=2, label=f"ROC (AUC = {roc_auc:.3f})")
axes[1].plot([0, 1], [0, 1], color="navy", linestyle="--")
axes[1].set_xlim([0.0, 1.0])
axes[1].set_ylim([0.0, 1.05])
axes[1].set_xlabel("False Positive Rate")
axes[1].set_ylabel("True Positive Rate")
axes[1].set_title("ROC Curve")
axes[1].legend(loc="lower right")

plt.tight_layout()
plt.show()

# # 3. Native LightGBM Feature Importance
# lgb.plot_importance(clf, max_num_features=10, importance_type="gain", figsize=(8, 5))
# plt.title("Top 10 Features by Information Gain")
# plt.show()



# 1. Get raw feature names and clean transformer prefixes
raw_names = pipeline.named_steps["preprocessor"].get_feature_names_out()
clean_names = [name.split("__")[-1] for name in raw_names]

# 2. Extract importance values (gain)
classifier = pipeline.named_steps["classifier"]
importances = classifier.booster_.feature_importance(importance_type="gain")

# 3. Build DataFrame and select top 10
importance_df = pd.DataFrame(
    {"Feature": clean_names, "Gain": importances}
).sort_values(by="Gain", ascending=False).head(10)

# 4. Plot
plt.figure(figsize=(9, 5))
sns.barplot(
    data=importance_df, x="Gain", y="Feature", hue="Feature", legend=False, palette="viridis"
)
plt.title("Top 10 Features by Information Gain")
plt.xlabel("Gain")
plt.ylabel("Feature")
plt.tight_layout()
plt.show()



# Access the fitted preprocessor step from the pipeline
preprocessor_step = pipeline.named_steps["preprocessor"]

# Extract the generated feature names
feature_names = preprocessor_step.get_feature_names_out()

print(f"Total Transformed Features: {len(feature_names)}")
for idx, name in enumerate(feature_names):
    print(f"{idx:02d}: {name}")
    
    
    import matplotlib.pyplot as plt
import pandas as pd
import shap

# 1. Transform raw test data into the numeric matrix LightGBM actually sees
X_test_transformed = preprocessor_step.transform(X_test)
X_test_df = pd.DataFrame(X_test_transformed, columns=feature_names)

# 2. Extract the trained LightGBM model from the pipeline
lgbm_model = pipeline.named_steps["classifier"]

# 3. Compute SHAP Values
explainer = shap.TreeExplainer(lgbm_model)
shap_values = explainer.shap_values(X_test_df)

# For binary classification, shap_values is a list [class_0, class_1] or a single matrix
shap_vals_target = shap_values[1] if isinstance(shap_values, list) else shap_values

# 4. Global Feature Importance (Beeswarm Summary Plot)
plt.figure(figsize=(10, 6))
shap.summary_plot(shap_vals_target, X_test_df, show=False)
plt.title("Global Feature Attribution (Impact on Approval)", fontsize=14)
plt.tight_layout()
plt.show()

# 5. Local Explanation for a Single Rejected Applicant
rejected_idx = (y_test == 0).values.nonzero()[0][0]
shap.force_plot(
    explainer.expected_value[1]
    if isinstance(explainer.expected_value, (list, np.ndarray))
    else explainer.expected_value,
    shap_vals_target[rejected_idx, :],
    X_test_df.iloc[rejected_idx, :],
    matplotlib=True,
)


import dice_ml

# 1. Prepare raw training data for DiCE (includes target column)
train_dataset = pd.concat([X_train, y_train], axis=1)

# List continuous/numeric columns present in raw X
continuous_raw_cols = [
    "age",
    "adverse_media_hits",
    "total_docs_submitted",
    "verified_docs_count",
    "expired_docs_count",
    "annual_income_band_encoded",
    "jurisdiction_risk_encoded",
]

# 2. Initialize DiCE Data and Model objects
dice_data = dice_ml.Data(
    dataframe=train_dataset,
    continuous_features=continuous_raw_cols,
    outcome_name="is_approved",
)

# Pass the complete Sklearn Pipeline so DiCE feeds raw inputs through preprocessing
dice_model = dice_ml.Model(model=pipeline, backend="sklearn")
exp = dice_ml.Dice(dice_data, dice_model, method="random")

# 3. Select a Rejected Sample from Raw X_test
rejected_applicant = X_test[y_test == 0].iloc[[0]]
print("--- ORIGINAL REJECTED APPLICANT ---")
print(rejected_applicant.to_dict(orient="records")[0])

# 4. Generate Counterfactuals
# Lock immutable attributes (client_type, nationality, age, is_pep)
# Allow only actionable compliance levers to vary
cf = exp.generate_counterfactuals(
    rejected_applicant,
    total_CFs=2,
    desired_class=1,  # Target: Flip outcome to APPROVED
    features_to_vary=[
        "verified_docs_count",
        "expired_docs_count",
        "has_unverified_docs",
        "annual_income_band_encoded",
    ],
)

# Display the required minimal changes
cf.visualize_as_dataframe(show_only_changes=True)