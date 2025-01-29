import pandas as pd
import json
import os

def csv_to_filtered_json(csv_path, json_output_path):
    # Read the CSV file
    df = pd.read_csv(csv_path)

    # Define the result columns that must be empty
    result_columns = [
        'Beneficio neto',
        'Total operaciones cerradas',
        'Porcentaje de rentabilidad',
        'Factor de ganancias',
        'Prom. barras en operaciones'
    ]

    # Filter rows where all result columns are empty
    # We consider empty both NaN and empty strings
    filtered_df = df[df[result_columns].isnull().all(axis=1) | (df[result_columns] == '').all(axis=1)]

    # Alternatively, if you want rows where **any** of the columns is empty:
    # filtered_df = df[df[result_columns].isnull().any(axis=1) | (df[result_columns] == '').any(axis=1)]

    # Create the dictionary for the JSON
    json_dict = {}

    for index, row in filtered_df.iterrows():
        name = row['name']

        # Build the indicators dictionary
        indicators = {
            'Activar Absolute Strength (Histograma)': row['Activar Absolute Strength (Histograma)'],
            'Activar SSL Channel': row['Activar SSL Channel'],
            'Activar RSI': row['Activar RSI'],
            'Activar Squeeze Momentum': row['Activar Squeeze Momentum'],
            'Activar MACD Signal': row['Activar MACD Signal'],
            'Activar MACD Histograma': row['Activar MACD Histograma'],
            'Activar Condiciones MTF': row['Activar Condiciones MTF'],
            'Activar Condiciones EMAs': row['Activar Condiciones EMAs'],
            'Activar Distancia entre EMAs': row['Activar Distancia entre EMAs'],
            'Activar Distancia Valida StopLoss': row['Activar Distancia Valida StopLoss'],
            'Usar Firestorm': row['Usar Firestorm'],
            'Activar WaveTrend Reversal': row['Activar WaveTrend Reversal'],
            'Activar WaveTrend Divergence': row['Activar WaveTrend Divergence'],
            'Activar Divergencia': row['Activar Divergencia']
        }

        # Build the riskManagement dictionary
        risk_management = {
            'Porcentaje de toma de ganancias': row['Porcentaje de toma de ganancias'],
            'Multiplier for Take Profit': row['Multiplier for Take Profit']
        }

        # Build the requires dictionary
        requires = {
            'Número de Indicadores Opcionales requeridos': row['Número de Indicadores Opcionales requeridos']
        }

        # Assign to the main dictionary using the name as the key
        json_dict[name] = {
            'indicators': indicators,
            'riskManagement': risk_management,
            'requires': requires
        }

    # Save the dictionary as JSON
    with open(json_output_path, 'w', encoding='utf-8') as json_file:
        json.dump(json_dict, json_file, ensure_ascii=False, indent=2)

    print(f"Filtered JSON saved at {json_output_path}")

# Script usage
if __name__ == "__main__":
    # Define your file paths
    csv_path = '/home/santiago/Bots/tradingview/Modelo Evolutivo/resultadosSOL4H.csv'  # Replace with the path to your CSV file
    json_output_path = '/home/santiago/Bots/tradingview/Modelo Evolutivo/resultados_filtrados.json'  # Replace with the path where you want to save the JSON

    # Check that the CSV file exists
    if not os.path.isfile(csv_path):
        print(f"The CSV file at {csv_path} does not exist.")
    else:
        csv_to_filtered_json(csv_path, json_output_path)
