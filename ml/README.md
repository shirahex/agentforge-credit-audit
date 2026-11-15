# ML workspace

| File | Role |
|---|---|
| `prepare_data.py` | Decodes the raw file, derives `sex`, writes the stratified 800 / 200 split |
| `train.py` | Baseline, LightGBM search, calibration, thresholds, both model variants |
| `select_samples.py` | Runs the agent graph on the test set and picks the six demo files |
| `report.py` | Figures, `reports/MODEL_CARD.md`, `reports/summary.json` read by the interface |
| `notebooks/01_eda.ipynb` | Exploratory analysis |
| `models/` | `model_<variant>.txt` (LightGBM text format) and `model_<variant>.json` (calibration, thresholds, metrics) |
| `reports/` | Figures for the written report |

Model artifacts are plain text: no pickle, so they load with any recent
LightGBM version on any machine.

Extra libraries for this folder: `pip install -r ../backend/requirements-ml.txt`.
