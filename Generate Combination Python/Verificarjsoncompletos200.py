import os
import json
import glob

def verificar_json_en_directorio(dir_path, expected_combinations):
    """
    Verifies JSON files in a specific folder to ensure they contain all expected combinations.

    :param dir_path: Path to the "results" folder.
    :param expected_combinations: Set of expected combinations.
    :return: List of incomplete JSON file names.
    """
    incompletos = []
    # Use glob to find all .json files in the "results" folder
    json_files = glob.glob(os.path.join(dir_path, '*.json'))
    
    for file in json_files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"⚠️ Error reading {os.path.basename(file)}: {e}")
            incompletos.append(os.path.basename(file))
            continue  # Continue with the next file
        
        # Get the combinations present in the JSON
        present_combinations = set(json_data.keys())
        
        # Determine the missing combinations
        missing_combinations = expected_combinations - present_combinations
        
        # If there are missing combinations, add the file to the incomplete list
        if missing_combinations:
            incompletos.append(os.path.basename(file))
    
    return incompletos


def main():
    # Define the paths to the "results" folders
    directories = [
        '/home/santiago/Bots/tradingview/Sol1Diaria/Results',
        '/home/santiago/Bots/tradingview/Sol2Diaria/Results',
        '/home/santiago/Bots/tradingview/Sol3Diaria/Results',
        '/home/santiago/Bots/tradingview/Sol4Diaria/Results',
        '/home/santiago/Bots/tradingview/SolDiaria/Results',
        '/home/santiago/Bots/tradingview/Sol5Diaria/Results'


    ]
    
    # Define the expected combinations
    expected_combinations = {f'combination_{i}' for i in range(1, 201)}
    
    # Iterate over each directory and verify the JSON files
    for dir_path in directories:
        # Get a readable name for the folder (e.g., 'Sol/Results')
        # You can adjust this according to your path structure
        carpeta_nombre = os.path.basename(os.path.dirname(dir_path)) + '/' + os.path.basename(dir_path)
        print(f"\n{carpeta_nombre}:")
        
        if not os.path.exists(dir_path):
            print(f"⚠️ The path {dir_path} does not exist. Please verify the path.")
            continue
        
        incompletos = verificar_json_en_directorio(dir_path, expected_combinations)
        
        if not incompletos:
            print("All JSON files are complete")
        else:
            # Format the list of incomplete files separated by commas
            archivos_incompletos = ', '.join(incompletos)
            print(f"{archivos_incompletos} incomplete")

if __name__ == "__main__":
    main()