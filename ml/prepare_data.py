"""Data preparation (task M1).

Decodes the raw Statlog German Credit file into readable attributes,
derives the sensitive attribute `sex` from the personal status code and
writes a stratified train / test split.

    python ml/prepare_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.features import BY_NAME, FEATURES  # noqa: E402

RAW = ROOT / "ml" / "data" / "raw" / "german.csv"
OUT = ROOT / "ml" / "data" / "processed"
SEED = 42
TEST_SIZE = 0.2

# Column order of the raw file (see german.names.txt).
RAW_COLUMNS = [
    "checking_status", "duration_months", "credit_history", "purpose", "credit_amount", "savings",
    "employment", "installment_rate", "personal_status", "other_debtors", "residence_since", "property",
    "age", "other_installment_plans", "housing", "existing_credits", "job", "dependents", "telephone",
    "foreign_worker", "target",
]
# A91 male divorced/separated, A92 female divorced/separated/married, A93 male single,
# A94 male married/widowed, A95 female single. Marital status is confounded with sex
# in this coding (no single-female rows), so only sex is kept.
SEX = {"A91": "male", "A92": "female", "A93": "male", "A94": "male", "A95": "female"}


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(RAW, header=None, names=RAW_COLUMNS)
    assert df.shape == (1000, 21), df.shape
    assert not df.isna().any().any()
    return df


def decode(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for f in FEATURES:
        if f.name == "sex":
            out["sex"] = df["personal_status"].map(SEX)
        elif f.name == "telephone":
            out["telephone"] = df["telephone"].eq("A192")
        elif f.name == "foreign_worker":
            out["foreign_worker"] = df["foreign_worker"].eq("A201")
        elif f.kind == "categorical":
            mapping = {code: value for value, _, code in f.categories}
            out[f.name] = df[f.name].map(mapping)
        else:
            out[f.name] = df[f.name].astype(int)
    # 1 = good payer, 2 = bad payer in the raw file. Target: 1 means default.
    out["default"] = df["target"].eq(2).astype(int)
    assert not out.isna().any().any(), out.isna().sum()[out.isna().sum() > 0]
    for f in FEATURES:
        if f.kind == "categorical":
            assert set(out[f.name]) <= set(BY_NAME[f.name].values), f.name
    return out


def main() -> None:
    df = decode(load_raw())
    df.insert(0, "applicant_id", [f"GC-{i + 1:04d}" for i in range(len(df))])
    train, test = train_test_split(df, test_size=TEST_SIZE, stratify=df["default"], random_state=SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "german_credit.csv", index=False)
    train.sort_index().to_csv(OUT / "train.csv", index=False)
    test.sort_index().to_csv(OUT / "test.csv", index=False)
    print(f"all {len(df)}  train {len(train)}  test {len(test)}")
    print(f"default rate: all {df['default'].mean():.3f}  train {train['default'].mean():.3f}  test {test['default'].mean():.3f}")
    print(df.groupby("sex")["default"].agg(["mean", "size"]).round(3))


if __name__ == "__main__":
    main()
