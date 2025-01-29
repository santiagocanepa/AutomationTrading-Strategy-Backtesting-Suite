import { Page } from 'puppeteer';

export async function applyIndicatorSettings(page: Page, indicators: { [key: string]: string }): Promise<void> {
    for (const [indicatorName, optionToSelect] of Object.entries(indicators)) {
        const result = await page.evaluate(async (indicatorName, optionToSelect) => {
            const descriptionElement = Array.from(document.querySelectorAll('span.label-ZOx_CVY3'))
                .find(el => el.textContent?.trim() === indicatorName);

            if (descriptionElement) {
                const parentDiv = descriptionElement.closest('div.cell-tBgV1m0B')?.nextElementSibling;
                const selectButton = parentDiv?.querySelector('span[role="button"]') as HTMLElement | null;

                if (selectButton) {
                    selectButton.click();

                    return new Promise(resolve => {
                        setTimeout(() => {
                            const optionToClick = Array.from(document.querySelectorAll('div[role="option"]'))
                                .find(el => el.textContent?.trim() === optionToSelect) as HTMLElement | null;
                            if (optionToClick) {
                                optionToClick.click();
                                resolve(`Selected "${optionToSelect}" for "${indicatorName}"`);
                            } else {
                                resolve(`Option not found for: ${optionToSelect}`);
                            }
                        }, 50); 
                    });
                } else {
                    return `Dropdown not found for indicator: ${indicatorName}`;
                }
            } else {
                return `Description element not found for: ${indicatorName}`;
            }
        }, indicatorName, optionToSelect);

        console.log(result);
        await new Promise(resolve => setTimeout(resolve, 20)); 
    }
}
