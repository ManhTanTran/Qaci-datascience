"""First Home Credit walkthrough: import libraries and load application data.

The ``# %%`` markers let VS Code and compatible editors run this file like a
notebook while keeping reusable logic in ``src/credit_scoring``.
"""

# %% 1. Import libraries
from pathlib import Path

import pandas as pd

from credit_scoring.data import (
    audit_home_credit_data,
    default_home_credit_data_dir,
    load_home_credit_data,
)

pd.set_option("display.max_columns", 150)
pd.set_option("display.width", 160)

# %% 2. Configure the local raw-data directory
# Default: <repository>/data/home_credit
# Alternative in PowerShell:
# $env:HOME_CREDIT_DATA_DIR = "D:\path\to\home-credit-default-risk"
DATA_DIR: Path = default_home_credit_data_dir()
print(f"Reading Home Credit data from: {DATA_DIR}")

# %% 3. Load the two application tables
# For a quick smoke test, add nrows=1_000. Do not use sampled data for final metrics.
data = load_home_credit_data(DATA_DIR)
application_train = data["application_train"]
application_test = data["application_test"]

# %% 4. Inspect structure without printing customer-level rows
audit = audit_home_credit_data(data)
print(audit)
print(application_train.dtypes.value_counts())
print(application_train["TARGET"].value_counts(dropna=False, normalize=True))

# %% 5. Confirm train/test relationship
assert "TARGET" in application_train.columns
assert "TARGET" not in application_test.columns
assert application_train["SK_ID_CURR"].is_unique
assert application_test["SK_ID_CURR"].is_unique
