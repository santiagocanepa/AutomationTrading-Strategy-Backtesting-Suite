import json
import sys
import os
from math import ceil

def split_combinations(input_file, output_dir, batch_size=200):
    """
    Divide un archivo JSON de combinaciones en múltiples archivos más pequeños.

    :param input_file: Ruta al archivo JSON de entrada.
    :param output_dir: Directorio donde se guardarán los archivos JSON divididos.
    :param batch_size: Número de combinaciones por archivo de salida.
    """
    # Verificar que el archivo de entrada exista
    if not os.path.isfile(input_file):
        print(f"Error: El archivo de entrada '{input_file}' no existe.")
        sys.exit(1)

    # Crear el directorio de salida si no existe
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"Directorio de salida '{output_dir}' creado exitosamente.")
        except Exception as e:
            print(f"Error al crear el directorio de salida '{output_dir}': {e}")
            sys.exit(1)

    # Cargar el archivo JSON de entrada
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"Archivo de entrada '{input_file}' cargado exitosamente.")
    except json.JSONDecodeError as e:
        print(f"Error al decodificar el archivo JSON de entrada: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error al leer el archivo de entrada: {e}")
        sys.exit(1)

    # Obtener todas las combinaciones
    all_combinations = list(data.items())
    total_combinations = len(all_combinations)
    total_files = ceil(total_combinations / batch_size)
    print(f"Total de combinaciones: {total_combinations}")
    print(f"Total de archivos a crear: {total_files}")

    for file_index in range(total_files):
        start_idx = file_index * batch_size
        end_idx = start_idx + batch_size
        batch = all_combinations[start_idx:end_idx]

        # Crear el diccionario para el archivo de salida
        output_data = {}
        for local_idx, (original_key, combination) in enumerate(batch, start=1):
            combination_key = f"combination_{local_idx}"
            # Crear una copia de la combinación para evitar modificar el original
            combination_copy = combination.copy()
            # Añadir el campo "name" con el valor del key original
            combination_copy["name"] = original_key
            # Asignar al nuevo diccionario
            output_data[combination_key] = combination_copy

        # Definir el nombre del archivo de salida
        #Cambiar [Activo por el nombre del activo idealmente, por ejemplo si el activo es BTC, se crearan los archivos populationBTC1.json, populationBTC2.json, etc. 
        #En tal caso, se debe introducir BTC en la linea del .env del script puppetier

        output_file = os.path.join(output_dir, f"[Activo]{file_index + 1}.json") #Cambiar [Activo por el nombre del activo idealmente, por ejemplo si el activo es BTC, se crearan los archivos populationBTC1.json, populationBTC2.json, etc. En tal caso, se debe introducir BTC en la linea del .env del script puppetier]

        # Escribir el archivo JSON de salida
        try:
            with open(output_file, 'w', encoding='utf-8') as f_out:
                json.dump(output_data, f_out, ensure_ascii=False, indent=4)
            print(f"Archivo '{output_file}' creado con {len(batch)} combinaciones.")
        except Exception as e:
            print(f"Error al escribir el archivo de salida '{output_file}': {e}")
            sys.exit(1)

    print("Proceso completado exitosamente.")

def main():git config --global user.email "tu-email@ejemplo.com"

    """
    Función principal que maneja la ejecución del script.
    """
    if len(sys.argv) != 3:
        print("Uso: python split_combinations.py <archivo_entrada.json> <directorio_salida>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_dir = sys.argv[2]

    split_combinations(input_file, output_dir)

if __name__ == "__main__":
    main()
