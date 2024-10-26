# Puppeteer Automation Backtesting 🚀


![image](https://github.com/user-attachments/assets/0af766af-7fd1-4f04-b1cc-5bacf512cccb)

![image](https://github.com/user-attachments/assets/843c5235-02f6-437c-a490-f11ff855e210)

This directory contains the **Puppeteer** script designed to perform **automated backtesting** of trading strategies in **TradingView**. Below is the project structure, the functionality of each folder and key file, as well as a detailed explanation of the script workflow.

## 📁 Directory Structure
```
PuppeteerAutomationBacktesting/.
├── constants/
│ ├── options.ts
│ │ ├─── selectors.ts
│ └└── types.d.ts
├── cookies/
├── dist/
├── functions/
│ └└── Util2/
│ ├─── appendResultToFile.ts
│ │ ├─── applyCombination.ts
│ ├──── applyIndicatorSettings.ts
│ ├─├── applyRiskManagementSettings.ts
│ ├├── extractResults.ts
│ └└── newPublication.ts
├─── backtesting.ts
├─── generateCombinations.ts
├── index.ts
├── login.ts
├─── main.ts
├─── node_modules/
├─── Populations/
├── Results/
├─── .env
├─── .eslintrc.json
├─── .gitignore
├─── package-lock.json
├── package.json
├── pnpm-lock.yaml
└─── tsconfig.json
```


### 📂 Description of Folders and Key Files.

1. `constants/` 📜
  - Contains configuration files and constants used in the project.
    - `options.ts`: Defines options for the Puppeteer browser, such as headless settings, window size, and other launch parameters.
    - selectors.ts`: Stores the page selectors used to interact with the TradingView interface, either via XPath or DOM selectors.
    - `types.d.ts`: Defines custom TypeScript types to ensure data integrity and improve auto-completion in the editor.
2. `cookies/` 🍪
  - This folder stores the cookies necessary for the script to automatically log into TradingView once. This avoids having to enter credentials each time the script is run.
3. `dist/` 🗂️
  - Compilation directory where the code transpiled to JavaScript from TypeScript is generated. This directory should not be modified manually.
4. `functions/` ⚙️
  - Contains reusable functions and utilities for backtesting.
    - `Util2/` 🔧
      - `appendResultToFile.ts`: Adds each backtesting result to the result JSON file.
      - `applyCombination.ts`: General module to apply a specific combination to the TradingView interface.
      - `applyIndicatorSettings.ts`: Applies indicators in optional and exclude states according to the strategy settings.
      - `applyRiskManagementSettings.ts`: Configures risk management in the TradingView strategy.
      - `extractResults.ts`: Extracts the backtesting results from the TradingView interface and prepares them for storage.
      - `newPublication.ts`: Compares the Populations and Results directories to identify which results JSON files are missing and need to be generated.
5. `Main Scripts` 📝
  - `backtesting.ts`: General module in charge of orchestrating the backtesting process. It is called by the main `main.ts` file.
  - `GenerateCombinations.ts`: Generates new populations through API calls, useful for running genetic or evolutionary models when you have a very large space of combinations.
  - `index.ts`: Initialization module that configures and prepares the environment for backtesting execution.
  - `login.ts`: Manages the login process, loading and/or saving cookies to avoid unnecessary re-authentications.
  - `main.ts`: The main module that executes the complete backtesting flow, from login to test execution and results storage.
6. `node_modules/` 📦.
  - Directory where the project dependencies are installed. This directory is automatically managed by the package manager and must not be modified manually.
7. `Populations/` 📊
  - Directory where the JSON files of populations to be backtested are stored. Each file contains multiple combinations of indicators and configurable parameters.
8. `Results/` 📈
  - Directory where the results of the backtests corresponding to each population are stored. Each JSON file in this folder has the same name as its corresponding file in `Populations/` and contains the detailed results for each combination.
9. `Configuration Files` 🛠️
  - `.env`: File containing environment variables, such as TradingView credentials (`USERNAME` and `PASSWORD`). This file should be kept private and should not be uploaded to the repository.
  - `.eslintrc.json`: ESLint configuration to maintain code quality and consistency.
  - `.gitignore`: Specifies which files and folders should be ignored by Git, such as `node_modules/`, `dist/`, and `cookies/`.
  - `package-lock.json`, `package.json`, `pnpm-lock.yaml`: Project dependency and script management files.
  - `tsconfig.json`: TypeScript configuration to compile the code correctly.


# 🔄 Script Workflow
The Puppeteer Automation Backtesting script follows a structured workflow to perform backtesting in an efficient and automated manner. The following is a step-by-step description of how the process works:

### Script Startup (`main.ts`):

The main module `main.ts` starts the backtesting process by calling the backtesting.ts module.

### Automatic Login (`login.ts`):

The script checks if an active session already exists by checking for the presence of cookies in the cookies/ folder.
If there are no cookies, it uses the credentials stored in the `.env` file to log in to TradingView.
In case of errors in the interface, you can adjust the timeout and change the headless option to false to log in manually.
Once successfully logged in, cookies are saved for future executions, avoiding the need to re-authenticate.

**Comparison of Populations and Results:**.

The script compares the JSON file names in the Populations/ folder with the files in Results/ to identify which populations have not yet been backtested.
Only populations that do not have corresponding results are processed, ensuring that each population file is backtested once.

**Backtesting run:** 

For each JSON file in **Populations/**, the script performs the following:

**Load Combinations:** Reads the combinations of indicators and parameters from the JSON file.


Setting the Strategy in TradingView:** **Settings
Navigate to the assigned chart using the link specified in `selectors.ts`.
Open the strategy settings and apply the parameters for each combination using the functions in the functions/Util2/ folder.

**Backtest Execution:** Start the backtest and wait for the results to be completed.
**Extract and Store Results:** Extracts the backtest results and stores them in a JSON file in the Results/ folder with the same name as the original population file.

**Completion of the Process:**

Once all populations have been processed and their results stored, the script terminates.
If new populations are added in the future, the script will automatically identify them on the next run and perform the corresponding backtests.

# 🛠️ Installation and Configuration
### 🔧 Prerequisites.
**Node.js** (v14 or higher).
**Puppeteer**: It will be installed automatically with the project dependencies.
**TypeScript**: To compile and execute the TypeScript code.
### 📝 Installation Steps.

**Clone the Repository**.

```git clone https://github.com/santiagocanepa/mi-proyecto-trading.git```
```cd mi-proyecto-trading/PuppeteerAutomationBacktesting```

### Install Dependencies


```npm install```

or if you use pnpm

```pnpm install```

### Configure Environment Variables

Create an .env file in the root of the PuppeteerAutomationBacktesting/ directory with the following content:
```
USERNAME=
PASSWORD=
USERAGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:104.0) Gecko/20100101 Firefox/104.0' #Cambiar a gusto
WIDTH=1366
HEIGHT=768
RESULTS_DIR='/home/user/PuppeteerAutomationBacktesting/Results' #Directorio de Resultados
POBLACION_DIR='/home/user/PuppeteerAutomationBacktesting/Poblaciones' #Directorio de Poblaciones
ASSET_NAME=  # O el nombre del activo que desees usar

# URL de la API
API_URL='http://localhost:5500/generate_population'
```

### Compile TypeScript Code

```npm run build```
or if you use pnpm
```pnpm build```

### 🚀 Usage
### 1. Start the Backtesting
Run the main script to start the backtesting process:

```npm run init```
or if you use pnpm
```pnpm run init```.

### 2. Backtesting Process
**Session Login:** The script will try to login automatically using the saved cookies. If no cookies are found, it will use the `.env` credentials to log in and save the `cookies` for future runs.
**Populations Processing:** Identifies populations that have not yet been backtested by comparing the files in Populations/ and Results/.
**Backtest Run:** Configures and runs the backtest for each combination in the selected populations.
**Save Results:** Save the results in the Results/ folder with the same name as the corresponding population.
#### 3. Verify Results
After the run, the results will be available in the `Results/` folder. Each JSON file contains the detailed results of the backtested combinations.

### 🛡️ Error Handling and Debugging
**Login Errors:** If the script fails to login due to changes in the TradingView interface, adjust the timeout in the `login.ts` module and consider changing the headless option to false to manually login, after login and timeout, the script will save the cookies so as not to repeat the process.
Selectors Issues: If page elements change, update the selectors in constants/selectors.ts to reflect the new DOM or XPath selectors.
**Logs and Debugging:** Review logs generated during execution to identify and fix specific problems.


### 📞 Contact
Santiago Canepa - ```canepasantiago.ivan@gmail.com```

Thank you for using the Puppeteer Automation Backtesting script! If you have any questions or suggestions, feel free to contact me.
