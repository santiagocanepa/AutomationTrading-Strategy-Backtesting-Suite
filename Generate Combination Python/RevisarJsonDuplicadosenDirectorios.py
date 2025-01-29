import os

# Directories to check
directorios = [
    '/home/santiago/Bots/tradingview/Sol/Results',
    '/home/santiago/Bots/tradingview/Sol1/Results',
    '/home/santiago/Bots/tradingview/Sol2/Results',
    '/home/santiago/Bots/tradingview/Sol3/Results'
]

# Function to get JSON file names from a directory
def obtener_archivos_json(directorio):
    return [archivo for archivo in os.listdir(directorio) if archivo.endswith('.json')]

# Dictionary to store the found files
archivos_json = {}

# Fill the dictionary with files from each directory
for directorio in directorios:
    try:
        archivos_en_directorio = obtener_archivos_json(directorio)
        for archivo in archivos_en_directorio:
            if archivo in archivos_json:
                archivos_json[archivo].append(directorio)
            else:
                archivos_json[archivo] = [directorio]
    except FileNotFoundError:
        print(f"The directory {directorio} was not found.")
    except PermissionError:
        print(f"You do not have permission to access the directory {directorio}.")

# Check for duplicates
duplicados = {archivo: dirs for archivo, dirs in archivos_json.items() if len(dirs) > 1}

if duplicados:
    print("Duplicate JSON files found in multiple directories:")
    for archivo, dirs in duplicados.items():
        print(f"File {archivo} found in directories: {', '.join(dirs)}")
else:
    print("No duplicate JSON files found.")
