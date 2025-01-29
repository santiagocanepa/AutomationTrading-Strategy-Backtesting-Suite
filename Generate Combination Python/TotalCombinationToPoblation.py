import json
import sys
import os
from math import ceil

def split_combinations(input_file, output_dir, batch_size=200):
    """
    Divide a JSON file of combinations into multiple smaller files.

    :param input_file: Path to the input JSON file.
    :param output_dir: Directory where the split JSON files will be saved.
    :param batch_size: Number of combinations per output file.
    """
    # Verify that the input file exists
    if not os.path.isfile(input_file):
        print(f"Error: The input file '{input_file}' does not exist.")
        sys.exit(1)

    # Create the output directory if it does not exist
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"Output directory '{output_dir}' created successfully.")
        except Exception as e:
            print(f"Error creating output directory '{output_dir}': {e}")
            sys.exit(1)

    # Load the input JSON file
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"Input file '{input_file}' loaded successfully.")
    except json.JSONDecodeError as e:
        print(f"Error decoding the input JSON file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading the input file: {e}")
        sys.exit(1)

    # Get all combinations
    all_combinations = list(data.items())
    total_combinations = len(all_combinations)
    total_files = ceil(total_combinations / batch_size)
    print(f"Total combinations: {total_combinations}")
    print(f"Total files to create: {total_files}")

    for file_index in range(total_files):
        start_idx = file_index * batch_size
        end_idx = start_idx + batch_size
        batch = all_combinations[start_idx:end_idx]

        # Create the dictionary for the output file
        output_data = {}
        for local_idx, (original_key, combination) in enumerate(batch, start=1):
            combination_key = f"combination_{local_idx}"
            # Create a copy of the combination to avoid modifying the original
            combination_copy = combination.copy()
            # Add the "name" field with the value of the original key
            combination_copy["name"] = original_key
            # Assign to the new dictionary
            output_data[combination_key] = combination_copy

        # Define the name of the output file
        # Change [Activo] to the name of the asset ideally, for example if the asset is BTC, the files populationBTC1.json, populationBTC2.json, etc. will be created.
        # In that case, BTC should be introduced in the .env line of the puppetier script

        output_file = os.path.join(output_dir, f"[Activo]{file_index + 1}.json") # Change [Activo] to the name of the asset ideally, for example if the asset is BTC, the files populationBTC1.json, populationBTC2.json, etc. will be created. In that case, BTC should be introduced in the .env line of the puppetier script

        # Write the output JSON file
        try:
            with open(output_file, 'w', encoding='utf-8') as f_out:
                json.dump(output_data, f_out, ensure_ascii=False, indent=4)
            print(f"File '{output_file}' created with {len(batch)} combinations.")
        except Exception as e:
            print(f"Error writing the output file '{output_file}': {e}")
            sys.exit(1)

    print("Process completed successfully.")

def main():
    """
    Main function that handles the execution of the script.
    """
    if len(sys.argv) != 3:
        print("Usage: python split_combinations.py <input_file.json> <output_directory>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_dir = sys.argv[2]

    split_combinations(input_file, output_dir)

if __name__ == "__main__":
    main()
