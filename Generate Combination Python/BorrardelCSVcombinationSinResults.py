import pandas as pd
import os

def limpiar_csv(csv_path, csv_output_path):
    # Leer el archivo CSV
    df = pd.read_csv(csv_path)

    # Definir las columnas de resultados
    result_columns = [
        'Beneficio neto',
        'Total operaciones cerradas',
        'Porcentaje de rentabilidad',
        'Factor de ganancias',
        'Prom. barras en operaciones'
    ]

    # Asegurarse de que las columnas de resultados existen en el DataFrame
    for col in result_columns:
        if col not in df.columns:
            raise ValueError(f"La columna '{col}' no se encuentra en el archivo CSV.")

    # Crear una nueva columna que indique si las columnas de resultados tienen datos
    # 1 si alguna de las columnas de resultados tiene datos, 0 si todas están vacías
    df['Tiene_Resultados'] = df[result_columns].notnull().any(axis=1) & (df[result_columns].astype(str).apply(lambda x: x.str.strip()).ne('')).any(axis=1)

    # Ordenar el DataFrame de modo que las filas con resultados aparezcan primero
    df_sorted = df.sort_values(by=['name', 'Tiene_Resultados'], ascending=[True, False])

    # Eliminar duplicados, manteniendo la primera aparición (que tiene resultados si existen)
    df_deduplicated = df_sorted.drop_duplicates(subset='name', keep='first')

    # Eliminar la columna auxiliar
    df_deduplicated = df_deduplicated.drop(columns=['Tiene_Resultados'])

    # Guardar el DataFrame limpio en un nuevo CSV
    df_deduplicated.to_csv(csv_output_path, index=False, encoding='utf-8-sig')

    print(f"Archivo CSV limpio guardado en: {csv_output_path}")

if __name__ == "__main__":
    # Definir las rutas de los archivos
    csv_path = '/home/santiago/Bots/tradingview/Modelo Evolutivo/resultadosSOL4H.csv'          # Reemplaza con la ruta de tu archivo CSV original
    csv_output_path = '/home/santiago/Bots/tradingview/Modelo Evolutivo/resultadosSOL4HFinal.csv'  # Reemplaza con la ruta deseada para el CSV limpio

    # Verificar que el archivo CSV original existe
    if not os.path.isfile(csv_path):
        print(f"El archivo CSV en la ruta {csv_path} no existe.")
    else:
        try:
            limpiar_csv(csv_path, csv_output_path)
        except Exception as e:
            print(f"Ocurrió un error: {e}")
