# Model Retraining

Default every 100 trades. Prefers XGBoost when installed; falls back to
RandomForest or deterministic logistic. Uses Phase 6 WalkForwardValidator for
validation bookkeeping. Seeds + dataset/feature/config hashes recorded.
