# Local Mac Setup

Target: Apple Silicon (including M4 / 16 GB) for paper research.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# optional UI build
cd dashboard_ui && npm install && npm run build && cd ..
trader run --no-browser --demo
```

Dashboard: `http://127.0.0.1:8050`

## Optional ML extras

Phase 8 retraining prefers XGBoost, then scikit-learn RandomForest, then a
deterministic logistic fallback. On constrained Macs, keep ML optional:

```bash
pip install -e ".[ml]"
```

Do not force heavy ML deps for basic paper trading / dashboard use.
