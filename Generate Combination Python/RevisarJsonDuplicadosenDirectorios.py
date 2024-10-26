import os

# Directorios a verificar
directorios = [
    '/home/santiago/Bots/tradingview/Sol/Results',
    '/home/santiago/Bots/tradingview/Sol1/Results',
    '/home/santiago/Bots/tradingview/Sol2/Results',
    '/home/santiago/Bots/tradingview/Sol3/Results'

]

# Función para obtener los nombres de archivos JSON de un directorio
def obtener_archivos_json(directorio):
    return [archivo for archivo in os.listdir(directorio) if archivo.endswith('.json')]

# Diccionario para almacenar los archivos encontrados
archivos_json = {}

# Llenar el diccionario con los archivos de cada directorio
for directorio in directorios:
    try:
        archivos_en_directorio = obtener_archivos_json(directorio)
        for archivo in archivos_en_directorio:
            if archivo in archivos_json:
                archivos_json[archivo].append(directorio)
            else:
                archivos_json[archivo] = [directorio]
    except FileNotFoundError:
        print(f"El directorio {directorio} no fue encontrado.")
    except PermissionError:
        print(f"No tienes permisos para acceder al directorio {directorio}.")

# Verificar duplicados
duplicados = {archivo: dirs for archivo, dirs in archivos_json.items() if len(dirs) > 1}

if duplicados:
    print("Se encontraron archivos JSON duplicados en múltiples directorios:")
    for archivo, dirs in duplicados.items():
        print(f"Archivo {archivo} encontrado en los directorios: {', '.join(dirs)}")
else:
    print("No se encontraron archivos JSON duplicados.")
