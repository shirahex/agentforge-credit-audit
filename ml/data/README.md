# Data

## Statlog (German Credit Data)

- Source: UCI Machine Learning Repository, donated by Prof. Hans Hofmann
  (Universität Hamburg). Licence: CC BY 4.0.
- `raw/german.csv`: the original `german.data` file, 1,000 applicants,
  20 coded attributes and the outcome (1 good payer, 2 bad payer).
- `raw/german.names.txt`: the original documentation of the codes and of
  the cost matrix.
- `processed/`: readable attributes produced by `ml/prepare_data.py`
  (`german_credit.csv`, `train.csv` with 800 files, `test.csv` with 200).

## Why this dataset

It is the dataset named by the project brief, and the only public credit
dataset of the brief that carries the protected attributes a fairness audit
needs (sex, age, foreign-worker status) together with attributes an
applicant can act on (amount, duration, guarantor, savings).

The Lending Club data, also named by the brief, is not used: the public
files contain no sex or age, so the fairness audit could not run on them,
and its attributes describe the borrower's credit bureau record more than
choices the applicant can change.

## Known limits

1,000 files from one bank in the 1990s, amounts in Deutsche Mark, accepted
applicants only. Results are a benchmark, not a production estimate.
