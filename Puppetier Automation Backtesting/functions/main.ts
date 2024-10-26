import { Page } from 'puppeteer';
import { nuevaPoblacion } from './Utils2/nuevaPoblacion.js';
import { init } from './login.js';
import { performBacktesting } from './backtesting.js';
import { appendResultToFile } from './Utils2/appendResultToFile.js';
import { timer, getHumanizedWaitTime } from './Utils/timeUtils.js';

interface CombinationData {
    name: string;
    indicators: { [key: string]: string };
    riskManagement: { [key: string]: string | number };
    requires: { [key: string]: number };
}

export async function main(): Promise<void> {
    while (true) {  // Bucle infinito para repetir el proceso hasta que se detenga manualmente
        const { browser, page } = await init();

        // Obtener la nueva población a procesar
        const { poblacionFileName, poblacionData, resultFileName } = await nuevaPoblacion();

        if (!poblacionData) {
            console.log('No hay nuevas poblaciones para procesar.');
            await browser.close();
            break;
        }

        // Procesar combinaciones
        for (const [combinationId, combinationData] of Object.entries(poblacionData)) {
            const data = combinationData as CombinationData;  // Asegurar el tipo
            await getHumanizedWaitTime (1700,2500)

            const result = await performBacktesting(page as Page, data);

            // Guardar los resultados en el archivo JSON inmediatamente después de cada backtesting
            await appendResultToFile({
                id: combinationId,
                name: data.name,  // Pasar el nombre de la combinación
                combination: data,
                result,
                jsonFileName: resultFileName  // Pasar el nombre del archivo JSON de resultados
            });

        }

        await browser.close();
    }
}
