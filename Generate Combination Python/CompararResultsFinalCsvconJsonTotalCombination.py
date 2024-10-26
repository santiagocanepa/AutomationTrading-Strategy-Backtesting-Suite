import pandas as pd
import json
import os

def cargar_nombres_csv(csv_path):
    """
    Carga la columna 'name' del archivo CSV y devuelve un conjunto de nombres.
    """
    try:
        df = pd.read_csv(csv_path)
        if 'name' not in df.columns:
            raise ValueError("La columna 'name' no se encuentra en el archivo CSV.")
        nombres_csv = set(df['name'].dropna().astype(str).str.strip())
        return nombres_csv
    except Exception as e:
        print(f"Error al leer el archivo CSV: {e}")
        return set()

def cargar_claves_json(json_path):
    """
    Carga las claves principales del archivo JSON y devuelve un conjunto de claves.
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        claves_json = set(data.keys())
        return claves_json
    except Exception as e:
        print(f"Error al leer el archivo JSON: {e}")
        return set()

def comparar_combinaciones(nombres_csv, claves_json):
    """
    Compara los conjuntos de nombres del CSV y claves del JSON.
    Retorna dos conjuntos: faltantes en CSV y extras en CSV.
    """
    faltantes_en_csv = claves_json - nombres_csv
    extras_en_csv = nombres_csv - claves_json
    return faltantes_en_csv, extras_en_csv

def guardar_resultados(faltantes, extras, output_dir):
    """
    Guarda los resultados de la comparación en archivos de texto.
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        
        # Guardar faltantes
        with open(os.path.join(output_dir, 'faltantes_en_csv.txt'), 'w', encoding='utf-8') as f:
            if faltantes:
                f.write("Combinaciones en JSON que faltan en CSV:\n")
                for combo in sorted(faltantes):
                    f.write(f"{combo}\n")
            else:
                f.write("No hay combinaciones faltantes en el CSV.\n")
        
        # Guardar extras
        with open(os.path.join(output_dir, 'extras_en_csv.txt'), 'w', encoding='utf-8') as f:
            if extras:
                f.write("Nombres en CSV que no existen en JSON:\n")
                for nombre in sorted(extras):
                    f.write(f"{nombre}\n")
            else:
                f.write("No hay nombres extra en el CSV.\n")
        
        print(f"Resultados guardados en el directorio: {output_dir}")
    except Exception as e:
        print(f"Error al guardar los resultados: {e}")

def main():
    # Definir las rutas de los archivos
    csv_path = '/home/santiago/Bots/tradingview/Modelo Evolutivo/resultadosSOL4HFinal.csv'      # Reemplaza con la ruta de tu archivo CSV
    json_path = '/home/santiago/Bots/tradingview/Modelo Evolutivo/final_combinations1.json'    # Reemplaza con la ruta de tu archivo JSON
    output_dir = '/home/santiago/Bots/tradingview/Modelo Evolutivo/comparation.json'     # Reemplaza con la ruta donde deseas guardar los resultados
    
    # Verificar que los archivos existen
    if not os.path.isfile(csv_path):
        print(f"El archivo CSV en la ruta {csv_path} no existe.")
        return
    if not os.path.isfile(json_path):
        print(f"El archivo JSON en la ruta {json_path} no existe.")
        return
    
    # Cargar los nombres del CSV y las claves del JSON
    nombres_csv = cargar_nombres_csv(csv_path)
    claves_json = cargar_claves_json(json_path)
    
    # Comparar las combinaciones
    faltantes, extras = comparar_combinaciones(nombres_csv, claves_json)
    
    # Mostrar resultados en la consola
    print("\n=== Resultados de la Comparación ===\n")
    if faltantes:
        print("Combinaciones en JSON que faltan en CSV:")
        for combo in sorted(faltantes):
            print(f"- {combo}")
    else:
        print("No hay combinaciones faltantes en el CSV.")
    
    print("\n------------------------------------\n")
    
    if extras:
        print("Nombres en CSV que no existen en JSON:")
        for nombre in sorted(extras):
            print(f"- {nombre}")
    else:
        print("No hay nombres extra en el CSV.")
    
    # Guardar los resultados en archivos de texto
    guardar_resultados(faltantes, extras, output_dir)

if __name__ == "__main__":
    main()
