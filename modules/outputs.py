from pathlib import Path
import pandas as pd

def save_to_excel(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    path = Path(path)

    # Ensure folder exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Temporary file: append ".tmp.xlsx" safely
    temp_path = path.with_name(path.name + ".tmp.xlsx")

    with pd.ExcelWriter(temp_path, engine="xlsxwriter") as writer:
        for sheet_name, df in sheets.items():
            if df is None or df.empty:
                print(f"⚠️ Skipping empty sheet: {sheet_name}")
                continue
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes(1, 0)
            worksheet.set_column(0, len(df.columns) - 1, 15)

    # Replace old file if exists
    if path.exists():
        path.unlink()
    temp_path.rename(path)

    print(f"✅ Excel saved to {path}")
