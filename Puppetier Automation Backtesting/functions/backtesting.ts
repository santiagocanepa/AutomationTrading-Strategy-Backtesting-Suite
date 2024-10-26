import { Page } from 'puppeteer';
import { applyCombination } from './Utils2/applyCombination.js';
import { extractResults } from './Utils2/extractResults.js';
import { timer, getHumanizedWaitTime } from './Utils/timeUtils.js';

export async function performBacktesting(page: Page, combination: any): Promise<{ [key: string]: string | undefined }> {
    // Aplicar la combinación de configuraciones
    await applyCombination(page, combination);

    await getHumanizedWaitTime (1700,2500)
    // Extraer y retornar los resultados
    const results = await extractResults(page);

    return results;
}
