import json
import sys
import os

def convert_numbers_to_strings(data, sections):
    """
    Iterates over the combinations in the JSON and converts numeric values in
    the specified sections to strings.

    :param data: Dictionary representing the content of the JSON.
    :param sections: List of sections where numbers should be converted to strings.
    :return: Modified dictionary with numeric values converted to strings.
    """
    for comb_key, comb_value in data.items():
        for section in sections:
            if (section in comb_value):
                for key, value in comb_value[section].items():
                    if isinstance(value, (int, float)):
                        original_value = comb_value[section][key]
                        comb_value[section][key] = str(value)
                        print(f'Converted "{key}": {original_value} -> "{comb_value[section][key]}"')
    return data

def main():
    """
    Main function that handles reading the input file, converting values,
    and writing the output file.
    """
    if len(sys.argv) != 3:
        print("Usage: python script.py <input_file.json> <output_file.json>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]

    # Verify that the input file exists
    if not os.path.isfile(input_file):
        print(f"Error: The input file '{input_file}' does not exist.")
        sys.exit(1)

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
    
    # Specify the sections where numbers should be converted to strings
    sections_to_convert = ["riskManagement", "requires"]
    modified_data = convert_numbers_to_strings(data, sections_to_convert)
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(modified_data, f, ensure_ascii=False, indent=2)
        print(f"Modified file saved to '{output_file}'.")
    except Exception as e:
        print(f"Error writing the output file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
