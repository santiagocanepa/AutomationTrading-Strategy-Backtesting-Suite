# Puppeteer Automation Backtesting 🚀


![image](https://github.com/user-attachments/assets/2dd94083-ca7d-4e98-a233-d7fcc14dea9f)

![image](https://github.com/user-attachments/assets/8716460b-608a-4b2e-9e75-ecd1ec58e629)


Este directorio contiene el script de **Puppeteer** diseñado para realizar **backtesting automatizado** de estrategias de trading en **TradingView**. A continuación, se detalla la estructura del proyecto, la funcionalidad de cada carpeta y archivo clave, así como una explicación detallada del flujo de trabajo del script.

## 📁 Estructura del Directorio
    
    PuppeteerAutomationBacktesting/
    ├── constants/
    │   ├── options.ts
    │   ├── selectors.ts
    │   └── types.d.ts
    ├── cookies/
    ├── dist/
    ├── functions/
    │   └── Util2/
    │       ├── appendResultToFile.ts
    │       ├── applyCombination.ts
    │       ├── applyIndicatorSettings.ts
    │       ├── applyRiskManagementSettings.ts
    │       ├── extractResults.ts
    │       └── nuevaPublicacion.ts
    ├── backtesting.ts
    ├── generateCombinations.ts
    ├── index.ts
    ├── login.ts
    ├── main.ts
    ├── node_modules/
    ├── Poblaciones/
    ├── Results/
    ├── .env
    ├── .eslintrc.json
    ├── .gitignore
    ├── package-lock.json
    ├── package.json
    ├── pnpm-lock.yaml
    └── tsconfig.json
    


### 📂 Descripción de Carpetas y Archivos Clave
1. `constants/` 📜
   - Contiene archivos de configuración y constantes utilizadas en el proyecto.
     - `options.ts`: Define las opciones para el navegador de Puppeteer, como configuración de headless, tamaño de la ventana, y otros parámetros de lanzamiento.
     - `selectors.ts`: Almacena los selectores de la página utilizados para interactuar con la interfaz de TradingView, ya sea mediante XPath o selectores de DOM.
     - `types.d.ts`: Define tipos TypeScript personalizados para asegurar la integridad de los datos y mejorar la autocompletación en el editor.
2. `cookies/` 🍪
   - Esta carpeta almacena las cookies necesarias para que el script inicie sesión automáticamente en TradingView una sola vez. Esto evita tener que ingresar las credenciales cada vez que se ejecuta el script.
3. `dist/` 🗂️
   - Directorio de compilación donde se genera el código transpilado a JavaScript desde TypeScript. Este directorio no debe modificarse manualmente.
4. `functions/` ⚙️
   - Contiene funciones reutilizables y utilidades para el backtesting.
     - `Util2/` 🔧
       - `appendResultToFile.ts`: Añade cada resultado de backtesting al archivo JSON de resultados.
       - `applyCombination.ts`: Módulo general para aplicar una combinación específica a la interfaz de TradingView.
       - `applyIndicatorSettings.ts`: Aplica los indicadores en estados opcional y excluyente según la configuración de la estrategia.
       - `applyRiskManagementSettings.ts`: Configura la gestión de riesgo en la estrategia de TradingView.
       - `extractResults.ts`: Extrae los resultados del backtesting desde la interfaz de TradingView y los prepara para el almacenamiento.
       - `nuevaPublicacion.ts`: Compara los directorios Poblaciones y Results para identificar qué archivos JSON de resultados faltan y necesitan ser generados.
5. `Scripts Principales` 📝
   - `backtesting.ts`: Módulo general que se encarga de orquestar el proceso de backtesting. Es llamado por el archivo principal `main.ts`.
   - `generateCombinations.ts`: Genera nuevas poblaciones a través de llamadas a una API, útil para ejecutar modelos genéticos o evolutivos cuando se tiene un espacio muy grande de combinaciones.
   - `index.ts`: Módulo de inicialización que configura y prepara el entorno para la ejecución del backtesting.
   - `login.ts`: Gestiona el proceso de inicio de sesión, cargando y/o guardando cookies para evitar re-autenticaciones innecesarias.
   - `main.ts`: El módulo principal que ejecuta el flujo completo de backtesting, desde el inicio de sesión hasta la ejecución de los tests y el almacenamiento de resultados.
6. `node_modules/` 📦
   - Directorio donde se instalan las dependencias del proyecto. Este directorio es gestionado automáticamente por el gestor de paquetes y no debe ser modificado manualmente.
7. `Poblaciones/` 📊
   - Directorio donde se guardan los archivos JSON de poblaciones que serán backtesteadas. Cada archivo contiene múltiples combinaciones de indicadores y parámetros configurables.
8. `Results/` 📈
   - Directorio donde se almacenan los resultados de los backtests correspondientes a cada población. Cada archivo JSON en esta carpeta tiene el mismo nombre que su correspondiente archivo en `Poblaciones/` y contiene los resultados detallados de cada combinación.
9. `Archivos de Configuración` 🛠️
   - `.env`: Archivo que contiene variables de entorno, como las credenciales de TradingView (`USERNAME` y `PASSWORD`). Este archivo debe mantenerse privado y no debe subirse al repositorio.
   - `.eslintrc.json`: Configuración de ESLint para mantener la calidad y consistencia del código.
   - `.gitignore`: Especifica qué archivos y carpetas deben ser ignorados por Git, como `node_modules/`, `dist/`, y `cookies/`.
   - `package-lock.json`, `package.json`, `pnpm-lock.yaml`: Archivos de gestión de dependencias y scripts del proyecto.
   - `tsconfig.json`: Configuración de TypeScript para compilar el código correctamente.
    

# 🔄 Flujo de Trabajo del Script
El script de Puppeteer Automation Backtesting sigue un flujo de trabajo estructurado para realizar backtesting de manera eficiente y automatizada. A continuación, se describe paso a paso cómo funciona el proceso:

### Inicio del Script (main.ts):

El módulo principal `main.ts` inicia el proceso de backtesting llamando al módulo backtesting.ts.

### Inicio de Sesión Automático (`login.ts`):

El script verifica si ya existe una sesión activa comprobando la presencia de cookies en la carpeta cookies/.
Si no hay cookies, utiliza las credenciales almacenadas en el archivo `.env` para iniciar sesión en TradingView.
En caso de errores en la interfaz, se puede ajustar el tiempo de espera y cambiar la opción headless a false para iniciar sesión manualmente.
Una vez iniciada la sesión exitosamente, las cookies se guardan para futuras ejecuciones, evitando la necesidad de re-autenticarse.

**Comparación de Poblaciones y Resultados:**

El script compara los nombres de los archivos JSON en la carpeta Poblaciones/ con los archivos en Results/ para identificar qué poblaciones aún no han sido backtesteadas.
Solo se procesan las poblaciones que no tienen resultados correspondientes, asegurando que cada archivo de población se backtesteé una vez.

**Ejecución de Backtesting:**

Para cada archivo JSON en **Poblaciones/**, el script realiza lo siguiente:

**Carga de Combinaciones:** Lee las combinaciones de indicadores y parámetros desde el archivo JSON.

**Configuración de la Estrategia en TradingView:**
Navega al gráfico asignado utilizando el enlace especificado en `selectors.ts`.
Abre la configuración de la estrategia y aplica los parámetros de cada combinación utilizando las funciones en la carpeta functions/Util2/.

**Ejecución del Backtest:** Inicia el backtest y espera a que se completen los resultados.
**Extracción y Almacenamiento de Resultados:** Extrae los resultados del backtest y los guarda en un archivo JSON en la carpeta Results/ con el mismo nombre que el archivo de población original.

**Finalización del Proceso:**

Una vez que todas las poblaciones han sido procesadas y sus resultados almacenados, el script finaliza.
Si se agregan nuevas poblaciones en el futuro, el script las identificará automáticamente en la próxima ejecución y realizará los backtests correspondientes.

# 🛠️ Instalación y Configuración
### 🔧 Requisitos Previos
**Node.js** (v14 o superior)
**Puppeteer**: Se instalará automáticamente con las dependencias del proyecto.
**TypeScript**: Para compilar y ejecutar el código TypeScript.
### 📝 Pasos de Instalación
**Clonar el Repositorio**


```git clone https://github.com/santiagocanepa/AutomationTrading-Strategy-Backtesting-Suite.git```
```cd AutomationTrading-Strategy-Backtesting-Suite/PuppeteerAutomationBacktesting```
### Instalar Dependencias


```npm install```

o si usas pnpm

```pnpm install```

### Configurar Variables de Entorno

Crea un archivo .env en la raíz del directorio PuppeteerAutomationBacktesting/ con el siguiente contenido:
```

USERNAME=
PASSWORD=
USERAGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:104.0) Gecko/20100101 Firefox/104.0' #Cambiar a gusto
WIDTH=1366
HEIGHT=768
RESULTS_DIR='/home/usuario/PuppeteerAutomationBacktesting/Activo/Results' #Directorio de Resultados
POBLACION_DIR='/home/usuario/PuppeteerAutomationBacktesting/Activo/Poblaciones' #Directorio de Poblaciones
ASSET_NAME=SOL  # O el nombre del activo que desees usar

# URL de la API
API_URL='http://localhost:5500/generate_population'
```
### Compilar el Código TypeScript

```npm run build```
o si usas pnpm
```pnpm build```

### 🚀 Uso
### 1. Iniciar el Backtesting
Ejecuta el script principal para comenzar el proceso de backtesting:

```npm run init```
o si usas pnpm
```pnpm run init```

### 2. Proceso de Backtesting
**Inicio de Sesión:** El script intentará iniciar sesión automáticamente utilizando las cookies guardadas. Si no encuentra cookies, usará las credenciales de `.env` para iniciar sesión y guardará las `cookies` para futuras ejecuciones.
**Procesamiento de Poblaciones:** Identifica las poblaciones que aún no han sido backtesteadas comparando los archivos en Poblaciones/ y Results/.
**Ejecución del Backtest:** Configura y ejecuta el backtest para cada combinación en las poblaciones seleccionadas.
**Almacenamiento de Resultados:** Guarda los resultados en la carpeta Results/ con el mismo nombre que la población correspondiente.
#### 3. Verificar Resultados
Después de la ejecución, los resultados estarán disponibles en la carpeta `Results/`. Cada archivo JSON contiene los resultados detallados de las combinaciones backtesteadas.

### 🛡️ Manejo de Errores y Depuración
**Errores de Inicio de Sesión:** Si el script falla al iniciar sesión debido a cambios en la interfaz de TradingView, ajusta el tiempo de espera en el módulo `login.ts` y considera cambiar la opción headless a false para iniciar sesión manualmente, luego del inicio de sesion y el tiempo de espera transcurrido, el script guardara las cookies para no repetir el proceso.
Problemas con Selectores: Si los elementos de la página cambian, actualiza los selectores en constants/selectors.ts para reflejar los nuevos selectores de DOM o XPath.
**Logs y Depuración:** Revisa los logs generados durante la ejecución para identificar y solucionar problemas específicos.


### 📞 Contacto
Santiago Canepa – ```canepasantiago.ivan@gmail.com```

¡Gracias por utilizar el script de Puppeteer Automation Backtesting! Si tienes alguna pregunta o sugerencia, no dudes en contactarme.

