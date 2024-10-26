import os
import json
import glob

def verificar_json_en_directorio(dir_path, expected_combinations):
    """
    Verifica los archivos JSON en una carpeta específica para asegurar que contengan todas las combinaciones esperadas.

    :param dir_path: Ruta a la carpeta "results".
    :param expected_combinations: Conjunto de combinaciones esperadas.
    :return: Lista de nombres de archivos JSON incompletos.
    """
    incompletos = []
    # Usar glob para encontrar todos los archivos .json en la carpeta "results"
    json_files = glob.glob(os.path.join(dir_path, '*.json'))
    
    for file in json_files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"⚠️ Error al leer {os.path.basename(file)}: {e}")
            incompletos.append(os.path.basename(file))
            continue  # Continúa con el siguiente archivo
        
        # Obtener las combinaciones presentes en el JSON
        present_combinations = set(json_data.keys())
        
        # Determinar las combinaciones faltantes
        missing_combinations = expected_combinations - present_combinations
        
        # Si faltan combinaciones, añadir el archivo a la lista de incompletos
        if missing_combinations:
            incompletos.append(os.path.basename(file))
    
    return incompletos


def main():
    # Definir las rutas a las carpetas "results"
    directories = [
        '/home/santiago/Bots/tradingview/Sol1Diaria/Results',
        '/home/santiago/Bots/tradingview/Sol2Diaria/Results',
        '/home/santiago/Bots/tradingview/Sol3Diaria/Results',
        '/home/santiago/Bots/tradingview/Sol4Diaria/Results',
        '/home/santiago/Bots/tradingview/SolDiaria/Results',
        '/home/santiago/Bots/tradingview/Sol5Diaria/Results'


    ]
    
    # Definir las combinaciones esperadas
    expected_combinations = {f'combination_{i}' for i in range(1, 201)}
    
    # Iterar sobre cada directorio y verificar los JSON
    for dir_path in directories:
        # Obtener un nombre legible para la carpeta (por ejemplo, 'Sol/Results')
        # Puedes ajustar esto según la estructura de tus rutas
        carpeta_nombre = os.path.basename(os.path.dirname(dir_path)) + '/' + os.path.basename(dir_path)
        print(f"\n{carpeta_nombre}:")
        
        if not os.path.exists(dir_path):
            print(f"⚠️ La ruta {dir_path} no existe. Por favor, verifica la ruta.")
            continue
        
        incompletos = verificar_json_en_directorio(dir_path, expected_combinations)
        
        if not incompletos:
            print("Todos los json están completos")
        else:
            # Formatear la lista de archivos incompletos separados por comas
            archivos_incompletos = ', '.join(incompletos)
            print(f"{archivos_incompletos} incompleto")

if __name__ == "__main__":
    main()