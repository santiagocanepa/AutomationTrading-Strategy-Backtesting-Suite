import os
import json
import pandas as pd
import glob

def clean_numeric_value(value):
    if isinstance(value, str):
        # Reemplazar el signo negativo especial si existe
        value = value.replace('−', '-').strip()
        
        # Eliminar unidades monetarias y otros sufijos comunes, incluyendo '%'
        suffixes = [' USD', 'USDT', ' usd', 'usdt', '%']
        for suffix in suffixes:
            if value.endswith(suffix):
                value = value[:-len(suffix)]
                break  # Asumimos solo un sufijo por valor
        
        # Eliminar separadores de miles (puntos)
        value = value.replace('.', '')
        
        # Reemplazar la coma decimal por un punto
        value = value.replace(',', '.')
        
        try:
            return float(value)
        except ValueError:
            print(f"Error al convertir el valor: {value}")
            return None
    return value
# Lista de rutas a los directorios que contienen las carpetas "results"
directories = [
    '/home/santiago/Bots/tradingview/Sol/Results',
    '/home/santiago/Bots/tradingview/Sol1/Results',
    '/home/santiago/Bots/tradingview/Sol2/Results',
    '/home/santiago/Bots/tradingview/Sol3/Results',
    '/home/santiago/Bots/tradingview/SolDiaria/Results'
    '/home/santiago/Bots/tradingview/Sol1Diaria/Results'
    '/home/santiago/Bots/tradingview/Sol2Diaria/Results'
    '/home/santiago/Bots/tradingview/Sol3Diaria/Results'


]

data = []

for dir_path in directories:
    # Usar glob para encontrar todos los archivos .json en la carpeta "results"
    json_files = glob.glob(os.path.join(dir_path, '*.json'))
    
    for file in json_files:
        with open(file, 'r', encoding='utf-8') as f:
            try:
                json_data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error al leer {file}: {e}")
                continue  # Salta al siguiente archivo si hay un error
            
            for combination_key, combination_value in json_data.items():
                # Extraer el nombre desde combination['name']
                name = combination_value.get('name', None)
                
                # Extraer indicadores
                indicators = combination_value.get('combination', {}).get('indicators', {})
                
                # Extraer gestión de riesgo
                risk_management = combination_value.get('combination', {}).get('riskManagement', {})
                
                # Extraer requisitos
                requires = combination_value.get('combination', {}).get('requires', {})
                
                # Extraer resultados
                result = combination_value.get('result', {})
                
                # Limpiar los valores numéricos en 'result'
                for key in result:
                    result[key] = clean_numeric_value(result[key])
                
                # Construir un diccionario plano
                row = {
                    'name': name
                }
                
                # Añadir indicadores al diccionario
                row.update(indicators)
                
                # Añadir gestión de riesgo
                row.update(risk_management)
                
                # Añadir requisitos
                row.update(requires)
                
                # Añadir resultados
                row.update(result)
                
                # Añadir la fila a la lista de datos
                data.append(row)

# Crear el DataFrame
df = pd.DataFrame(data)

# Definir el orden de las columnas
column_order = [
    'name',
    'Activar Absolute Strength (Histograma)',
    'Activar SSL Channel',
    'Activar RSI',
    'Activar Squeeze Momentum',
    'Activar MACD Signal',
    'Activar MACD Histograma',
    'Activar Condiciones MTF',
    'Activar Condiciones EMAs',
    'Activar Distancia entre EMAs',
    'Activar Distancia Valida StopLoss',
    'Usar Firestorm',
    'Activar WaveTrend Reversal',
    'Activar WaveTrend Divergence',
    'Activar Divergencia',
    'Porcentaje de toma de ganancias',
    'Multiplier for Take Profit',
    'Número de Indicadores Opcionales requeridos',
    'Beneficio neto',
    'Total operaciones cerradas',
    'Porcentaje de rentabilidad',
    'Factor de ganancias',
    'Prom. barras en operaciones'
]

# Reordenar las columnas si existen en el DataFrame
existing_columns = [col for col in column_order if col in df.columns]
df = df[existing_columns]

# Guardar el DataFrame en un archivo CSV
output_csv = 'resultadosSOL4H.csv'
df.to_csv(output_csv, index=False, encoding='utf-8-sig')
print(f"CSV unificado guardado como {output_csv}")