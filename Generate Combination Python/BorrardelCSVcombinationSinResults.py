import pandas as pd
import os

def limpiar_csv(csv_path, csv_output_path):
    # Read the CSV file
    df = pd.read_csv(csv_path)

    # Define the result columns
    result_columns = [
        'Beneficio neto',
        'Total operaciones cerradas',
        'Porcentaje de rentabilidad',
        'Factor de ganancias',
        'Prom. barras en operaciones'
    ]

    # Ensure that the result columns exist in the DataFrame
    for col in result_columns:
        if col not in df.columns:
            raise ValueError(f"The column '{col}' is not found in the CSV file.")

    # Create a new column indicating if the result columns have data
    # 1 if any of the result columns have data, 0 if all are empty
    df['Tiene_Resultados'] = df[result_columns].notnull().any(axis=1) & (df[result_columns].astype(str).apply(lambda x: x.str.strip()).ne('')).any(axis=1)

    # Sort the DataFrame so that rows with results appear first
    df_sorted = df.sort_values(by=['name', 'Tiene_Resultados'], ascending=[True, False])

    # Remove duplicates, keeping the first occurrence (which has results if they exist)
    df_deduplicated = df_sorted.drop_duplicates(subset='name', keep='first')

    # Remove the auxiliary column
    df_deduplicated = df_deduplicated.drop(columns=['Tiene_Resultados'])

    # Save the cleaned DataFrame to a new CSV
    df_deduplicated.to_csv(csv_output_path, index=False, encoding='utf-8-sig')

    print(f"Clean CSV file saved at: {csv_output_path}")

if __name__ == "__main__":
    # Define the file paths
    csv_path = '/home/santiago/Bots/tradingview/Modelo Evolutivo/resultadosSOL4H.csv'          # Replace with the path to your original CSV file
    csv_output_path = '/home/santiago/Bots/tradingview/Modelo Evolutivo/resultadosSOL4HFinal.csv'  # Replace with the desired path for the cleaned CSV

    # Check that the original CSV file exists
    if not os.path.isfile(csv_path):
        print(f"The CSV file at {csv_path} does not exist.")
    else:
        try:
            limpiar_csv(csv_path, csv_output_path)
        except Exception as e:
            print(f"An error occurred: {e}")
