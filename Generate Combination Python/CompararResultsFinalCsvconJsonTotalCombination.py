import pandas as pd
import json
import os

def cargar_nombres_csv(csv_path):
    """
    Loads the 'name' column from the CSV file and returns a set of names.
    """
    try:
        df = pd.read_csv(csv_path)
        if 'name' not in df.columns:
            raise ValueError("The 'name' column is not found in the CSV file.")
        nombres_csv = set(df['name'].dropna().astype(str).str.strip())
        return nombres_csv
    except Exception as e:
        print(f"Error reading the CSV file: {e}")
        return set()

def cargar_claves_json(json_path):
    """
    Loads the main keys from the JSON file and returns a set of keys.
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        claves_json = set(data.keys())
        return claves_json
    except Exception as e:
        print(f"Error reading the JSON file: {e}")
        return set()

def comparar_combinaciones(nombres_csv, claves_json):
    """
    Compares the sets of names from the CSV and keys from the JSON.
    Returns two sets: missing in CSV and extra in CSV.
    """
    faltantes_en_csv = claves_json - nombres_csv
    extras_en_csv = nombres_csv - claves_json
    return faltantes_en_csv, extras_en_csv

def guardar_resultados(faltantes, extras, output_dir):
    """
    Saves the comparison results in text files.
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        
        # Save missing
        with open(os.path.join(output_dir, 'faltantes_en_csv.txt'), 'w', encoding='utf-8') as f:
            if faltantes:
                f.write("Combinations in JSON that are missing in CSV:\n")
                for combo in sorted(faltantes):
                    f.write(f"{combo}\n")
            else:
                f.write("There are no missing combinations in the CSV.\n")
        
        # Save extras
        with open(os.path.join(output_dir, 'extras_en_csv.txt'), 'w', encoding='utf-8') as f:
            if extras:
                f.write("Names in CSV that do not exist in JSON:\n")
                for nombre in sorted(extras):
                    f.write(f"{nombre}\n")
            else:
                f.write("There are no extra names in the CSV.\n")
        
        print(f"Results saved in the directory: {output_dir}")
    except Exception as e:
        print(f"Error saving the results: {e}")

def main():
    # Define the file paths
    csv_path = '/home/santiago/Bots/tradingview/Modelo Evolutivo/resultadosSOL4HFinal.csv'      # Replace with the path to your CSV file
    json_path = '/home/santiago/Bots/tradingview/Modelo Evolutivo/final_combinations1.json'    # Replace with the path to your JSON file
    output_dir = '/home/santiago/Bots/tradingview/Modelo Evolutivo/comparation.json'     # Replace with the path where you want to save the results
    
    # Check that the files exist
    if not os.path.isfile(csv_path):
        print(f"The CSV file at {csv_path} does not exist.")
        return
    if not os.path.isfile(json_path):
        print(f"The JSON file at {json_path} does not exist.")
        return
    
    # Load the names from the CSV and the keys from the JSON
    nombres_csv = cargar_nombres_csv(csv_path)
    claves_json = cargar_claves_json(json_path)
    
    # Compare the combinations
    faltantes, extras = comparar_combinaciones(nombres_csv, claves_json)
    
    # Display results on the console
    print("\n=== Comparison Results ===\n")
    if faltantes:
        print("Combinations in JSON that are missing in CSV:")
        for combo in sorted(faltantes):
            print(f"- {combo}")
    else:
        print("There are no missing combinations in the CSV.")
    
    print("\n------------------------------------\n")
    
    if extras:
        print("Names in CSV that do not exist in JSON:")
        for nombre in sorted(extras):
            print(f"- {nombre}")
    else:
        print("There are no extra names in the CSV.")
    
    # Save the results in text files
    guardar_resultados(faltantes, extras, output_dir)

if __name__ == "__main__":
    main()
