### 📊 Visualizations
![image](https://github.com/user-attachments/assets/f16f1dee-80c6-46ed-85c5-56d6484a9728)
![image](https://github.com/user-attachments/assets/8931ad4c-c0ac-4f7c-af9f-e73682ca1efb)
![image](https://github.com/user-attachments/assets/f42b43fe-efc5-4a93-adb9-99e7c976ed7a)
![image](https://github.com/user-attachments/assets/7dcef661-932b-4e2b-8529-2f0a2d3e16c0)

### 📈 Description.
This comprehensive automated trading project combines advanced TradingView strategies with Python scripts for indicator combination generation and analysis, and uses Puppeteer for automated backtesting. The modular architecture allows extensive customization and efficient optimization of strategies, facilitating identification of profitable setups and risk management.

   - **🔗 Quick Links**.
       - [Generate Combination Python](https://github.com/santiagocanepa/AutomationTrading-Strategy-Backtesting-Suite/blob/main/Generate%20Combination%20Python/README.md)
       - [Puppetier Automation Backtesting](https://github.com/santiagocanepa/AutomationTrading-Strategy-Backtesting-Suite/blob/main/Puppetier%20Automation%20Backtesting/README.md)
       - [Indicator Strategy of TradingView](https://github.com/santiagocanepa/AutomationTrading-Strategy-Backtesting-Suite/blob/main/Indicator%20Strategy%20of%20TradingView/README.md)


### 🚀 Features.
   - **Advanced TradingView Strategy**.
       - Implements more than 15 configurable indicators to generate accurate buy and sell signals.
   - **Generation and Analysis of Combinations with Python**
       - Automates the creation of indicator and parameter combinations, optimizing the search space to identify the most effective configurations.
   - **Automated Backtesting with Puppeteer**
       - Runs historical tests efficiently, managing large volumes of combinations and storing detailed results for further analysis.
   - **Results Analysis**
       - Tools to convert results into analyzable formats and perform advanced statistical studies to evaluate the effectiveness of strategies.


### 📁 Project Structure
The project is organized into three main components, each with its own specific but interrelated functionality to provide a complete trading solution.


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



   - **🔧 Component Integration** 1.
       1. TradingView Strategy.
           - Develop a robust trading strategy using Pine Script in TradingView, with over 15 configurable indicators. This strategy generates buy and sell signals based on complex conditions, optimized for different timeframes and trading styles.
       2. Combination Generation and Analysis (Python)
           - Uses Python scripts to create combinations of indicators and parameters, optimizing the search space to identify profitable setups. This module includes:
               - Combination Generation: Creates comprehensive combinations of indicators and parameters.
               - Population Preparation: Organize combinations into manageable groups for backtesting.
               - Results Analysis: Convert backtesting results into analyzable formats and perform statistical studies.
       3. Automated Backtesting (Puppeteer)
           - Implements Puppeteer to automate the backtesting process in TradingView, managing large volumes of combinations and storing detailed results. This module includes:
               - Backtesting Automation: Configures and runs backtests automatically.
               - Results Management: Stores and organizes results for further analysis.
               - Process Optimization: Ensures efficiency and data integrity during backtesting.

### 🛠️ Installation
   - **🔍 Prerequisites**
       - TradingView: Active account to use the Pine script.
       - Python 3.x: To run the combination generation and analysis scripts.
       - Node.js: To run Puppeteer scripts.
       - Jupyter Notebook: To run and visualize Python notebooks.
   - **📝 Installation Steps**.
       - Clonar el repositorio
           ```
           git clone https://github.com/santiagocanepa/AutomationTrading-Strategy-Backtesting-Suite.git
           cd AutomationTrading-Strategy-Backtesting-Suite
           ```

       - Configure each Component
           - Generation and Analysis of Combinations (Python)
               ```
               cd GenerateCombinationPython
               python -m venv env
               source env/bin/activate # On Windows: env/scripts/activate
               pip install -r requirements.txt
               ```
           - Automated Backtesting (Puppeteer)
               ```
               cd ../PuppeteerAutomationBacktesting
               npm install # or pnpm install
               ```
           - TradingView Strategy
               - Import the Pine script into TradingView following the instructions in TradingViewStrategy/README.md.

### 🧩 Usage
   - **1. **Configure the Strategy in TradingView**
       - Import and configure the Pine script in TradingView according to your preferences and desired parameters. Refer to the TradingView README for specific details.
   - **2. **Generate Strategy Combinations**
       - Use Python scripts to generate optimized indicator and parameter combinations. Details and examples of use are available in GenerateCombinationPython/README.md.
   - **3. **Perform Automated Backtesting**
       - Run the Puppeteer script to perform backtesting of the generated combinations. Follow the instructions detailed in PuppeteerAutomationBacktesting/README.md.
   - **4. **Analyze the Results**
       - Once the backtesting is complete, use Python's analysis tools to evaluate the effectiveness of the combinations. See the notebook and analysis scripts in GenerateCombinationPython/README.md.
    

### 🧑‍💻 Contribution
Contributions are welcome! If you wish to contribute, please follow these steps:
   - Fork the repository.
   - Create a new branch for your feature (git checkout -b feature/new-feature).
   - Make your changes and commit (git commit -m 'Add new feature').
   - Push to the branch (git push origin feature/new-feature).
   - Open a Pull Request.
   - See CONTRIBUTING.md for more details.

### 📄 License
This project is licensed under the MIT License. See the [LICENSE](https://github.com/santiagocanepa/AutomationTrading-Strategy-Backtesting-Suite/blob/main/LICENSE) file for more information.