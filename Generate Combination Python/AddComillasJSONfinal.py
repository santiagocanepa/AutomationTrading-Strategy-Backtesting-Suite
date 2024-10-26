import json
import sys
import os

def convert_numbers_to_strings(data, sections):
    """
    Recorre las combinaciones en el JSON y convierte los valores numéricos en
    las secciones especificadas a cadenas de texto.

    :param data: Diccionario que representa el contenido del JSON.
    :param sections: Lista de secciones donde se deben convertir los números a strings.
    :return: Diccionario modificado con los valores numéricos convertidos a strings.
    """
    for comb_key, comb_value in data.items():
        for section in sections:
            if section in comb_value:
                for key, value in comb_value[section].items():
                    if isinstance(value, (int, float)):
                        original_value = comb_value[section][key]
                        comb_value[section][key] = str(value)
                        print(f'Convertido "{key}": {original_value} -> "{comb_value[section][key]}"')
    return data

def main():
    """
    Función principal que maneja la lectura del archivo de entrada, la conversión de valores
    y la escritura del archivo de salida.
    """
    if len(sys.argv) != 3:
        print("Uso: python script.py <archivo_entrada.json> <archivo_salida.json>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]

    # Verificar que el archivo de entrada exista
    if not os.path.isfile(input_file):
        print(f"Error: El archivo de entrada '{input_file}' no existe.")
        sys.exit(1)

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
    
    # Especificar las secciones donde se deben convertir los números a strings
    sections_to_convert = ["riskManagement", "requires"]
    modified_data = convert_numbers_to_strings(data, sections_to_convert)
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(modified_data, f, ensure_ascii=False, indent=2)
        print(f"Archivo modificado guardado en '{output_file}'.")
    except Exception as e:
        print(f"Error al escribir el archivo de salida: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
