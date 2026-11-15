# ML workspace

Owner: Marouane (tasks M1 and M2).

- `data/`: raw and processed datasets, not versioned (see `data/README.md`)
- `notebooks/`: exploration and experiments, numbered (`01_eda.ipynb`, ...)
- `train.py`: reproducible training script that writes the model and its
  metrics to `models/`
- `models/`: saved model, preprocessing pipeline and model card, not versioned

Install the libraries with `pip install -r ../backend/requirements-ml.txt`.
