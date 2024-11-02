
### 📊 Visualizaciones
![image](https://github.com/user-attachments/assets/b010edf3-5c6f-4c78-9410-bbe50daf1c42)
![image](https://github.com/user-attachments/assets/a2c2bcb7-57b1-437f-ae41-f87ae1348f32)
![image](https://github.com/user-attachments/assets/8a423216-0c8e-4e37-86bb-aacafb8d35f3)
![image](https://github.com/user-attachments/assets/39c03c50-b0b7-42fb-b6ed-0861bab68386)

### 📈 Descripción
Este proyecto integral de trading automatizado combina estrategias avanzadas de TradingView con scripts de Python para la generación y análisis de combinaciones de indicadores, y utiliza Puppeteer para realizar backtesting automatizado. La arquitectura modular permite una personalización extensa y una optimización eficiente de estrategias, facilitando la identificación de configuraciones rentables y la gestión de riesgos.

   - **🔗 Enlaces Rápidos**
       - [Generate Combination Python](https://github.com/santiagocanepa/AutomationTrading-Strategy-Backtesting-Suite/blob/main/Generate%20Combination%20Python/README_ES.md)
       - [Puppeteer Automation Backtesting](https://github.com/santiagocanepa/AutomationTrading-Strategy-Backtesting-Suite/blob/main/Puppeteer%20Automation%20Backtesting/README_ES.md)
       - [Indicator Strategy of TradingView](https://github.com/santiagocanepa/AutomationTrading-Strategy-Backtesting-Suite/blob/main/Indicator%20Strategy%20of%20TradingView/README_ES.md)


### 🚀 Características
   - **Estrategia Avanzada en TradingView**
       - Implementa más de 15 indicadores configurables para generar señales de compra y venta precisas.
   - **Generación y Análisis de Combinaciones con Python**
       - Automatiza la creación de combinaciones de indicadores y parámetros, optimizando el espacio de búsqueda para identificar las configuraciones más efectivas.
   - **Backtesting Automatizado con Puppeteer**
       - Ejecuta pruebas históricas de manera eficiente, gestionando grandes volúmenes de combinaciones y almacenando resultados detallados para su posterior análisis.
   - **Análisis de Resultados**
       - Herramientas para convertir resultados en formatos analizables y realizar estudios estadísticos avanzados para evaluar la eficacia de las estrategias.


### 📁 Estructura del Proyecto
El proyecto está organizado en tres componentes principales, cada uno con su propia funcionalidad específica pero interrelacionada para proporcionar una solución de trading completa.

```plaintext
AutomationTrading-Strategy-Backtesting-Suite/
├── GenerateCombinationPython/
│   └── README.md
│   └── Generate Combination Python/
│   └── GenerateCombination.ipynb
│   └── AddComillasJSONFinal.py
│   └── TotalCombinationToPoblation.py
│   └── CompararResultsFinalCsvconJsonTotalCombination.py
│   └── RevisarJsonDuplicadosenDirectorios.py
│   └── Verificarjsoncompletos200.py
│   └── ResultsPoblationToCsvTotalResults.py
│   └── DevolverdeCSVaJsonlosNoResults.py
│   └── requirements.txt
│
├── PuppeteerAutomationBacktesting/
│   └── README.md
│   └──constants/
│       ├── options.ts
│       ├── selectors.ts
│       └── types.d.ts
│   └── cookies/
│   └── dist/
│   └── functions/
│       └── Util2/
│           ├── appendResultToFile.ts
│           ├── applyCombination.ts
│           ├── applyIndicatorSettings.ts
│           ├── applyRiskManagementSettings.ts
│           ├── extractResults.ts
│           └── nuevaPublicacion.ts
│       └── backtesting.ts
│       └── generateCombinations.ts
│       └── index.ts
│       └── login.ts
│       └── main.ts
│       └── node_modules/
│       └── Poblaciones/
│       └── Results/
│       └── .env
│       └── .eslintrc.json
│       └── .gitignore
│       └── package-lock.json
│       └── package.json
│       └── pnpm-lock.yaml
│       └── tsconfig.json
│
├── TradingViewStrategy/
│   └── README.md
│   └── Strategy-Indicators.pinescript
├── .gitignore
├── LICENSE
└── README.md
```

   - **🔧 Integración de Componentes**
       1. Estrategia de TradingView
           - Desarrolla una estrategia de trading robusta utilizando Pine Script en TradingView, con más de 15 indicadores configurables. Esta estrategia genera señales de compra y venta basadas en condiciones complejas, optimizadas para diferentes temporalidades y estilos de trading.
       2. Generación y Análisis de Combinaciones (Python)
           - Utiliza scripts de Python para crear combinaciones de indicadores y parámetros, optimizando el espacio de búsqueda para identificar configuraciones rentables. Este módulo incluye:
               - Generación de Combinaciones: Crea combinaciones exhaustivas de indicadores y parámetros.
               - Preparación de Poblaciones: Organiza combinaciones en grupos manejables para backtesting.
               - Análisis de Resultados: Convierte resultados de backtesting en formatos analizables y realiza estudios estadísticos avanzados.
       3. Backtesting Automatizado (Puppeteer)
           - Implementa Puppeteer para automatizar el proceso de backtesting en TradingView, gestionando grandes volúmenes de combinaciones y almacenando resultados detallados. Este módulo incluye:
               - Automatización del Backtesting: Configura y ejecuta backtests automáticamente.
               - Gestión de Resultados: Almacena y organiza resultados para análisis posterior.
               - Optimización de Procesos: Asegura la eficiencia y la integridad de los datos durante el backtesting.

               

### 🛠️ Instalación
   - **🔍 Requisitos Previos**
       - TradingView: Cuenta activa para utilizar el script de Pine.
       - Python 3.x: Para ejecutar los scripts de generación y análisis de combinaciones.
       - Node.js: Para ejecutar los scripts de Puppeteer.
       - Jupyter Notebook: Para ejecutar y visualizar los notebooks de Python.
   - **📝 Pasos de Instalación**
       - Clonar el Repositorio
           ```
           git clone https://github.com/santiagocanepa/AutomationTrading-Strategy-Backtesting-Suite.git
           cd AutomationTrading-Strategy-Backtesting-Suite
           ```
       - Configurar cada Componente
           - Generación y Análisis de Combinaciones (Python)
               ```
               cd GenerateCombinationPython
               python -m venv env
               source env/bin/activate  # En Windows: env\Scripts\activate
               pip install -r requirements.txt
               ```
           - Backtesting Automatizado (Puppeteer)
               ```
               cd ../PuppeteerAutomationBacktesting
               npm install  # o pnpm install
               ```
           - Estrategia de TradingView
               - Importa el script de Pine en TradingView siguiendo las instrucciones en TradingViewStrategy/README.md.

### 🧩 Uso
   - **1. Configurar la Estrategia en TradingView**
       - Importa y configura el script de Pine en TradingView según tus preferencias y parámetros deseados. Consulta el README de TradingView para detalles específicos.
   - **2. Generar Combinaciones de Estrategias**
       - Utiliza los scripts de Python para generar combinaciones de indicadores y parámetros optimizados. Detalles y ejemplos de uso están disponibles en GenerateCombinationPython/README.md.
   - **3. Realizar Backtesting Automatizado**
       - Ejecuta el script de Puppeteer para realizar backtesting de las combinaciones generadas. Sigue las instrucciones detalladas en PuppeteerAutomationBacktesting/README.md.
   - **4. Analizar los Resultados**
       - Una vez completado el backtesting, utiliza las herramientas de análisis de Python para evaluar la eficacia de las combinaciones. Consulta el notebook y scripts de análisis en GenerateCombinationPython/README.md.


### 🧑‍💻 Contribución
¡Las contribuciones son bienvenidas! Si deseas colaborar, por favor sigue estos pasos:
   - Fork el repositorio.
   - Crea una nueva rama para tu característica (git checkout -b feature/nueva-funcionalidad).
   - Realiza tus cambios y haz commit (git commit -m 'Añadir nueva funcionalidad').
   - Haz push a la rama (git push origin feature/nueva-funcionalidad).
   - Abre un Pull Request.
   - Consulta CONTRIBUTING.md para más detalles.

### 📄 Licencia
Este proyecto está licenciado bajo la Licencia MIT. Consulta el archivo [LICENSE](https://github.com/santiagocanepa/AutomationTrading-Strategy-Backtesting-Suite/blob/main/LICENSE) para más información.

### 📞 Contacto
   - **Santiago Canepa**
       - Correo electrónico: ```canepasantiago.ivan@gmail.com```
       - GitHub: [santiagocanepa](https://github.com/santiagocanepa)
