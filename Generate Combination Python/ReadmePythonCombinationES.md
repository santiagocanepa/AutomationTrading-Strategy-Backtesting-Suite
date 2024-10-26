
# Generación y Análisis de Combinaciones para Backtesting

Este directorio contiene todos los scripts de Python necesarios para generar combinaciones de estrategias, preparar poblaciones para backtesting, y analizar los resultados obtenidos. A continuación, se detalla exhaustivamente cada uno de los archivos y su función dentro del proceso.


### Estructura del Directorio

```plaintext
Generate Combination Python/
├── GenerateCombination.ipynb
├── AddComillasJSONFinal.py
├── TotalCombinationToPoblation.py
├── CompararResultsFinalCsvconJsonTotalCombination.py
├── RevisarJsonDuplicadosenDirectorios.py
├── Verificarjsoncompletos200.py
├── ResultsPoblationToCsvTotalResults.py
├── DevolverdeCSVaJsonlosNoResults.py
├── requirements.txt
```

### Requisitos Previos

- **Python 3.x** instalado en el sistema.
- **Jupyter Notebook** para ejecutar archivos `.ipynb`.
- Librerías Python especificadas en `requirements.txt`.
- Conocimientos básicos de Python y manejo de JSON.


### Generación de Combinaciones

- **1. GenerateCombination.ipynb**

    - Este Jupyter Notebook es el punto de partida para generar todas las combinaciones posibles de estrategias basadas en los parámetros deseados.

    - **Descripción**

        - Permite generar combinaciones de indicadores y parámetros según las preferencias del usuario.

    - **Uso**

        1. Abra el archivo `GenerateCombination.ipynb` con Jupyter Notebook.
        2. Configure los parámetros y variables según sus necesidades.
        3. Ejecute todas las celdas para generar el archivo `TotalCombinations.json`.

    - **Notas**

        - Se recomienda consultar el enlace al notebook en Kaggle para ver un ejemplo detallado de cómo se generaron las combinaciones.
        - Asegúrese de que los datos de entrada y las configuraciones sean correctas antes de ejecutar.

- **2. AddComillasJSONFinal.py**

    - Este script agrega las comillas necesarias al archivo JSON generado por el notebook anterior para asegurar su correcta interpretación por el script de Puppeteer.

    - **Descripción**

        - Corrige la sintaxis del JSON para hacerlo compatible con el proceso de backtesting automatizado.

    - **Uso**

        - Ejecute el script desde la línea de comandos:

            ```
            
            python AddComillasJSONFinal.py TotalCombinations.json CombinationsFormatted.json
            
            ```

    - `TotalCombinations.json`: Archivo JSON generado por el notebook.
    - `CombinationsFormatted.json`: Nombre del archivo de salida con las correcciones aplicadas.

    - **Notas**

        - Este paso es crucial para evitar errores durante el backtesting. Verifique que el archivo de salida esté correctamente formateado.

### Preparación de Poblaciones para Backtesting

- **3. TotalCombinationToPoblation.py**

    - Este script divide el archivo de combinaciones totales en múltiples archivos JSON, cada uno conteniendo 200 combinaciones. Esto facilita la gestión y procesamiento durante el backtesting, permitiendo reiniciar desde un punto intermedio en caso de fallos.

    - **Descripción**

        - Genera poblaciones de 200 combinaciones cada una. Enumera las combinaciones del 1 al 200 en cada archivo para un seguimiento sencillo. Asigna a cada combinación un identificador único bajo la clave "name".

    - **Uso**

        - Modifique la línea en el script para nombrar adecuadamente los archivos de salida:

            ```python
            output_file = os.path.join(output_dir, f"population[NombreDelActivo]{file_index + 1}.json")
            ```

            Reemplace `[NombreDelActivo]` con el nombre deseado para identificar el activo o estrategia. Ejecute el script desde la línea de comandos:

            ```bash
            python TotalCombinationToPoblation.py CombinationsFormatted.json Poblaciones
            ```

    - `CombinationsFormatted.json`: Archivo JSON formateado por AddComillasJSONFinal.py.
    - `Poblaciones`: Carpeta donde se guardarán los archivos de población.

    - **Notas**

        - Asegúrese de que la carpeta de salida exista o que el script tenga permisos para crearla. Los archivos generados se deben copiar en la raíz del proyecto de Puppeteer para el backtesting.


### Post-Proceso y Análisis de Resultados

- **4. CompararResultsFinalCsvconJsonTotalCombination.py**

    - Este script compara los archivos en la carpeta results con los de la carpeta Poblaciones para identificar si falta algún archivo o si hay archivos adicionales que no corresponden.

    - **Descripción**

        - Garantiza que todos los archivos de resultados correspondan a sus respectivas poblaciones y que no haya inconsistencias.

    - **Uso**

        - Ejecute el script desde la línea de comandos:

            ```bash
            python CompararResultsFinalCsvconJsonTotalCombination.py
            ```

        - Asegúrese de que las carpetas results y Poblaciones estén en el directorio correcto.

    - **Notas**

        - Útil para verificar la completitud del proceso de backtesting. Genera un reporte indicando archivos faltantes o sobrantes.

- **5. RevisarJsonDuplicadosenDirectorios.py**

    - Cuando se utilizan múltiples scripts o cuentas en paralelo, este script ayuda a verificar que no haya archivos JSON duplicados en los directorios especificados.

    - **Descripción**

        - Evita conflictos y redundancias al asegurar que cada combinación se procese una sola vez.

    - **Uso**

        - Ejecute el script indicando los directorios a verificar:

            ```bash
            python RevisarJsonDuplicadosenDirectorios.py directorio1 directorio2
            ```

        - `directorio1`, `directorio2`: Rutas de los directorios a comparar.

    - **Notas**

        - Ideal para entornos donde se distribuye la carga de procesamiento. Asegura la integridad de los datos y resultados.

- **6. Verificarjsoncompletos200.py**

    - Este script verifica que cada archivo JSON en las poblaciones contenga exactamente 200 combinaciones.

    - **Descripción**

        - Garantiza la consistencia de los archivos de población antes del backtesting.

    - **Uso**

        - Ejecute el script en la carpeta que contiene las poblaciones:

            ```bash
            python Verificarjsoncompletos200.py
            ```
    - **Notas**

        - Si algún archivo no tiene las 200 combinaciones, el script reportará cuáles son para su corrección.

### Análisis Avanzado en Jupyter Notebook

- Una vez obtenidos los resultados del backtesting y generados los archivos CSV, se puede proceder a un análisis más profundo utilizando Jupyter Notebook.

- **Objetivo**

    - Identificar las mejores combinaciones. Medir la eficacia de cada indicador y ajustar parámetros de gestión de riesgo.

- **Metodología**

    - Utilizar el beneficio neto como métrica principal. Si bien este no suele ser relevante, y lo que mas nos importa es el factor de ganancia y el numero de operaciones realizadas, en este caso en particular, dado que todas las estrategias se probaron con el mismo capital inicial la variable Beneficio Neto sintetiza bien la combinación de estas dos. Analizar la eficacia de cada indicador cuando aparece en modo opcional, para aislar su impacto. Introducir la entropía de cada combinación para considerar la interdependencia entre indicadores.

- **Pasos**

    1. Abra un nuevo Jupyter Notebook.
    2. Importe el CSV generado:

        ```python
        import pandas as pd
        df = pd.read_csv('resultados_totales.csv')
        ```

    3. Segmente el DataFrame según indicadores, gestión de riesgo y resultados.
    4. Realice análisis estadísticos y visualizaciones para extraer insights.

- **Notas**

    - La columna "name" es esencial para identificar y rastrear cada combinación. Considere utilizar técnicas de análisis multivariante para comprender mejor las interacciones entre variables.

### Requisitos del Entorno

- Para garantizar el correcto funcionamiento de todos los scripts, asegúrese de instalar las librerías especificadas en requirements.txt.

- **Instalación de Librerías**

    ```bash
    pip install -r requirements.txt
    ```


### Notas Adicionales

- **Organización de Carpetas**

    - Mantenga una estructura ordenada de las carpetas Poblaciones, results, y cualquier otra utilizada en el proceso. Esto facilita la localización de archivos y evita confusiones durante el procesamiento.

- **Respaldos**

    - Realice copias de seguridad periódicas de los archivos JSON y CSV para prevenir pérdidas de datos.

- **Manejo de Errores**

    - Esté atento a posibles errores durante la ejecución de los scripts y revise los logs o mensajes de error para solucionarlos.

- **Optimización**

    - En caso de que su conocimiento para introducir sesgo humano sea limitado, recomiendo utilizar mi configuración del jupyter para la gestion de riesgo y los rangos de indicadores opcionales habilitados, modificando unicamente los indicadores que desea combinar tanto en estado de opcional como excluyente. Considerando todos los parametros configurables y manipulables por el script de puppetier, el espacio total de combinaciones es de 1.4 mil millones. Si cuenta con conocimiento para introducir sesgo humano puede ajustar la creación del espacio para procesar más combinaciones por archivo si su entorno lo permite (utilizando multiples cuentas), pero tenga en cuenta que archivos muy grandes pueden ser difíciles de manejar, el script de puppetier esta optimizado al maximo posible para poder interactuar con la interfaz y es capaz de realizar 6 backtestings por minuto. En caso de generar un dataset con más de 50 mil combinaciones seria ideal utilizar un modelo genetico/evolutivo, pero se debe tener en cuenta la considerable interdependencia que existe entre los indicadores y la posibilidad de que estos modelos se queden durante mucho tiempo atascados en optimos locales. 

# Contacto

Para consultas o sugerencias relacionadas con estos scripts, puede contactarnos a través de:

- **Email**: `canepasantiago.ivan@gmail.com`
