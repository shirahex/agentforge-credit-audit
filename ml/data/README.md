# Datasets

Files in this folder are ignored by Git. Each machine downloads them once.

| Dataset | Source | Use |
|---|---|---|
| Statlog (German Credit Data) | UCI Machine Learning Repository | Main dataset: 1,000 applicants, 20 attributes |
| Lending Club loan data | Kaggle archive | Scale test on a sampled subset |

Expected layout:

```
data/raw/german_credit.csv
data/raw/lending_club_sample.csv
data/processed/
```

The download and preparation steps are scripted in task M1 so that both
machines produce identical processed files.
