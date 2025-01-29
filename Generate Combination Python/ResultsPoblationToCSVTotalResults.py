import os
import json
import pandas as pd
import glob

def clean_numeric_value(value):
    if isinstance(value, str):
        # Replace special negative sign if it exists
        value = value.replace('−', '-').strip()
        
        # Remove monetary units and other common suffixes, including '%'
        suffixes = [' USD', 'USDT', ' usd', 'usdt', '%']
        for suffix in suffixes:
            if value.endswith(suffix):
                value = value[:-len(suffix)]
                break  # Assume only one suffix per value
        
        # Remove thousand separators (dots)
        value = value.replace('.', '')
        
        # Replace decimal comma with a dot
        value = value.replace(',', '.')
        
        try:
            return float(value)
        except ValueError:
            print(f"Error converting value: {value}")
            return None
    return value

# List of paths to directories containing the "results" folders
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
    # Use glob to find all .json files in the "results" folder
    json_files = glob.glob(os.path.join(dir_path, '*.json'))
    
    for file in json_files:
        with open(file, 'r', encoding='utf-8') as f:
            try:
                json_data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error reading {file}: {e}")
                continue  # Skip to the next file if there's an error
            
            for combination_key, combination_value in json_data.items():
                # Extract the name from combination['name']
                name = combination_value.get('name', None)
                
                # Extract indicators
                indicators = combination_value.get('combination', {}).get('indicators', {})
                
                # Extract risk management
                risk_management = combination_value.get('combination', {}).get('riskManagement', {})
                
                # Extract requirements
                requires = combination_value.get('combination', {}).get('requires', {})
                
                # Extract results
                result = combination_value.get('result', {})
                
                # Clean numeric values in 'result'
                for key in result:
                    result[key] = clean_numeric_value(result[key])
                
                # Build a flat dictionary
                row = {
                    'name': name
                }
                
                # Add indicators to the dictionary
                row.update(indicators)
                
                # Add risk management
                row.update(risk_management)
                
                # Add requirements
                row.update(requires)
                
                # Add results
                row.update(result)
                
                # Add the row to the data list
                data.append(row)

# Create the DataFrame
df = pd.DataFrame(data)

# Define the order of the columns
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

# Reorder the columns if they exist in the DataFrame
existing_columns = [col for col in column_order if col in df.columns]
df = df[existing_columns]

# Save the DataFrame to a CSV file
output_csv = 'resultadosSOL4H.csv'
df.to_csv(output_csv, index=False, encoding='utf-8-sig')
print(f"Unified CSV saved as {output_csv}")
