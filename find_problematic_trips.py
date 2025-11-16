import config
from modules import db, preprocessing, aggregations as agg, plots, outputs
import pandas as pd

def main():
    # -------------------------
    # Load raw data from Mongo 
    # -------------------------
    df = db.load_data(
        start_date=config.START_DATE,
        end_date=config.END_DATE,
        line_ids=config.LINE_IDS
    )

    # -------------------------
    # Preprocess & join with daytypes
    # -------------------------
    df = preprocessing.prepare(df, config.DAYTYPE_FILE)

    # -------------------------
    # Validations per trip/day
    # -------------------------
    df_validations = db.load_validations(
        start_date=config.START_DATE,
        end_date=config.END_DATE,
        line_ids=config.LINE_IDS
    )
    
    df_problematic = db.find_problematic_trips(df_validations)
    df_problematic = preprocessing.prepare_to_zeros(df_problematic, config.DAYTYPE_FILE)

    if df_problematic is not None and not df_problematic.empty:
        suspect_trips = agg.create_suspect_trips(df_problematic)
    else:
        suspect_trips = pd.DataFrame()

    print(config.OUTPUT_EXCEL)
    # -------------------------
    # Save Excel
    # -------------------------
    outputs.save_to_excel(
        config.OUTPUT_EXCEL,
        {
            "Viagens Problematicas": df_problematic, 
            "Viagens Problematicas_v1": suspect_trips, 
        }
    )

    print("✅ Analysis complete!")


if __name__ == "__main__":
    main()
