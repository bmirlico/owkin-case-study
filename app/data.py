from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {"cancer_indication", "gene", "median_value"}


def load_dataframe(path: str) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(
            f"CSV not found at {csv_path.resolve()}. "
            "Place owkin_take_home_data.csv in data/ before starting the app."
        )
    df = pd.read_csv(csv_path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"CSV at {csv_path} is missing required columns: {sorted(missing)}. "
            f"Found: {list(df.columns)}"
        )
    return df


def get_available_cancer_types(df: pd.DataFrame) -> list[str]:
    return sorted(df["cancer_indication"].dropna().astype(str).unique().tolist())
