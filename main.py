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
        line_ids=config.LINE_IDS,
        agency_ids=config.AGENCY_IDS
    )

    # -------------------------
    # Preprocess & join with daytypes
    # -------------------------
    df = preprocessing.prepare(df, config.DAYTYPE_FILE)
    
    # -------------------------
    # Aggregations
    # -------------------------
    df_monthly = agg.agg_monthly_summary(df)
    df_daytype_month_avg = agg.agg_daytype_monthly_avg(df)
    df_daytype_date = agg.agg_daytype_date(df)
    df_lineid = agg.agg_lineid_summary(df)

    # -------------------------
    # Validations per trip/day
    # -------------------------
    df_validations = db.load_validations(
        start_date=config.START_DATE,
        end_date=config.END_DATE,
        line_ids=config.LINE_IDS,
        agency_ids=config.AGENCY_IDS
    )
    
    
    # -------------------------
    # Save Excel
    # -------------------------
    outputs.save_to_excel(
        config.OUTPUT_EXCEL,
        {
            "Circulacoes_por Dia Tipo": df_daytype_month_avg,
            "Circulacoes_por Data": df_daytype_date,
            "Total por mês": df_monthly,
            "Circulacoes por Linha": df_lineid,
            "Validacoes por Viagem": df_validations
        }
    )

    # -------------------------
    # Plots
    # -------------------------
    plots.plot_monthly_rides(df_monthly, config.OUTPUT_PLOT_RIDES)
    plots.plot_monthly_extensions(df_monthly, config.OUTPUT_PLOT_EXTENSIONS)
    plots.plot_daytype_bar(df_daytype_month_avg, config.OUTPUT_PLOT_DAYTYPE)

    print("✅ Analysis complete!")


if __name__ == "__main__":
    main()
