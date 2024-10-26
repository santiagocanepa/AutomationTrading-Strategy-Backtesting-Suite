import { Page } from 'puppeteer';

export async function extractResults(page: Page): Promise<{ [key: string]: string | undefined }> {
    const titlesToExtract = [
        "Beneficio neto",
        "Total operaciones cerradas",
        "Porcentaje de rentabilidad",
        "Factor de ganancias",
        "Máxima serie de perdidas",
        "Prom. barras en operaciones"
    ];

    const extractedResults: { [key: string]: string | undefined } = {};

    const resultContainers = await page.$$eval('div.containerCell-Yvm0jjs7', (containers, titles) => {
        const results: { [key: string]: string | undefined } = {};

        containers.forEach(container => {
            const titleElement = container.querySelector('div.firstRow-Yvm0jjs7 > div.title-Yvm0jjs7');
            const title = titleElement?.textContent?.trim();

            if (title && titles.includes(title)) {
                let valueElement = container.querySelector('div.secondRow-Yvm0jjs7 > div.positiveValue-Yvm0jjs7');

                if (!valueElement) {
                    valueElement = container.querySelector('div.secondRow-Yvm0jjs7 > div:not(.additionalPercent-Yvm0jjs7)');
                }

                const value = valueElement?.textContent?.trim();
                results[title] = value;
            }
        });

        return results;
    }, titlesToExtract);

    return resultContainers;
}

