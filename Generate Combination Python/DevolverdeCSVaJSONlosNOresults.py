import pandas as pd
import json
import os

def csv_to_filtered_json(csv_path, json_output_path):
    # Leer el archivo CSV
    df = pd.read_csv(csv_path)

    # Definir las columnas de resultados que deben estar vacías
    result_columns = [
        'Beneficio neto',
        'Total operaciones cerradas',
        'Porcentaje de rentabilidad',
        'Factor de ganancias',
        'Prom. barras en operaciones'
    ]

    # Filtrar filas donde todas las columnas de resultados están vacías
    # Consideramos vacías tanto si son NaN como si son cadenas vacías
    filtered_df = df[df[result_columns].isnull().all(axis=1) | (df[result_columns] == '').all(axis=1)]

    # Alternativamente, si quieres filas donde **cualquier** de las columnas está vacía:
    # filtered_df = df[df[result_columns].isnull().any(axis=1) | (df[result_columns] == '').any(axis=1)]

    # Crear el diccionario para el JSON
    json_dict = {}

    for index, row in filtered_df.iterrows():
        name = row['name']

        # Construir el diccionario de indicadores
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

        # Construir el diccionario de riskManagement
        risk_management = {
            'Porcentaje de toma de ganancias': row['Porcentaje de toma de ganancias'],
            'Multiplier for Take Profit': row['Multiplier for Take Profit']
        }

        # Construir el diccionario de requires
        requires = {
            'Número de Indicadores Opcionales requeridos': row['Número de Indicadores Opcionales requeridos']
        }

        # Asignar al diccionario principal usando el nombre como clave
        json_dict[name] = {
            'indicators': indicators,
            'riskManagement': risk_management,
            'requires': requires
        }

    # Guardar el diccionario como JSON
    with open(json_output_path, 'w', encoding='utf-8') as json_file:
        json.dump(json_dict, json_file, ensure_ascii=False, indent=2)

    print(f"JSON filtrado guardado en {json_output_path}")

# Uso del script
if __name__ == "__main__":
    # Define las rutas de tus archivos
    csv_path = '/home/santiago/Bots/tradingview/Modelo Evolutivo/resultadosSOL4H.csv'  # Reemplaza con la ruta de tu archivo CSV
    json_output_path = '/home/santiago/Bots/tradingview/Modelo Evolutivo/resultados_filtrados.json'  # Reemplaza con la ruta donde quieres guardar el JSON

    # Verificar que el archivo CSV existe
    if not os.path.isfile(csv_path):
        print(f"El archivo CSV en la ruta {csv_path} no existe.")
    else:
        csv_to_filtered_json(csv_path, json_output_path)
