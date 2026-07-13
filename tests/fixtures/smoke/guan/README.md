# Guan Smoke Fixture

This directory documents the synthetic fixture shape used by Phase 2C and Phase 2D tests.

The tests generate tiny Excel files in a temporary directory from obviously fake values:

- `billing_food.xlsx`
- `billing_retail.xlsx`
- `crowd_cost.xlsx`

The generated records are not copied from real company data. Order IDs, merchant IDs, names, and amounts are synthetic and only prove that the safe public entrypoint can traverse the real field mapping, normalization, income, fee, crowd-cost extraction, report, manifest, and result-contract boundaries.
