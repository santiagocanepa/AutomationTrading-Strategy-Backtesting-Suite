import { Page, ElementHandle } from 'puppeteer';

export async function applyRiskManagementSettings(
  page: Page,
  settings: { [key: string]: string }
): Promise<void> {
  const descriptions = await page.$$eval('div[class*="first-"]', elements =>
    elements.map(el => el.textContent?.trim() || '')
  );

  const descriptionElements = await page.$$('div[class*="first-"]');

  for (const [description, newValue] of Object.entries(settings)) {
    console.log(`\nIntentando actualizar: "${description}" a "${newValue}"`);

    const index = descriptions.indexOf(description);

    if (index === -1) {
      console.log(`Elemento de descripción no encontrado para: "${description}"`);
      continue; 
    }

    const descriptionElementHandle = descriptionElements[index];
    console.log(`Elemento de descripción encontrado para: "${description}"`);

    const parentDivHandle = await descriptionElementHandle.evaluateHandle(el =>
      el.closest('div[class^="cell-"]')
    ) as ElementHandle<Element> | null;

    if (!parentDivHandle) {
      console.log(`Contenedor padre no encontrado para la descripción: "${description}"`);
      continue;
    }

    const nextSiblingHandle = await parentDivHandle.evaluateHandle(el =>
      el.nextElementSibling
    ) as ElementHandle<Element> | null;

    if (!nextSiblingHandle) {
      console.log(`Siguiente hermano no encontrado para el contenedor padre de: "${description}"`);
      continue;
    }

    const inputElementHandle = await nextSiblingHandle.$('input.input-RUSovanF');

    if (!inputElementHandle) {
      console.log(`Elemento de input no encontrado para la descripción: "${description}"`);
      continue;
    }

    console.log(`Elemento de input encontrado para: "${description}"`);

    await inputElementHandle.click({ clickCount: 3 });


    await new Promise(resolve => setTimeout(resolve, 1)); 

    await inputElementHandle.type(newValue, { delay: 1 });


    console.log(`Actualizado "${description}" a "${newValue}"`);


  }
}
