import { Page, ElementHandle } from 'puppeteer';

export async function applyRiskManagementSettings(
  page: Page,
  settings: { [key: string]: string }
): Promise<void> {
  // Extraer todos los elementos de descripción y sus textos en una sola llamada
  const descriptions = await page.$$eval('div[class*="first-"]', elements =>
    elements.map(el => el.textContent?.trim() || '')
  );

  // Obtener todos los elementos de descripción en paralelo
  const descriptionElements = await page.$$('div[class*="first-"]');

  for (const [description, newValue] of Object.entries(settings)) {
    console.log(`\nIntentando actualizar: "${description}" a "${newValue}"`);

    // Encontrar el índice del elemento que coincide con la descripción
    const index = descriptions.indexOf(description);

    if (index === -1) {
      console.log(`Elemento de descripción no encontrado para: "${description}"`);
      continue; // Pasar al siguiente setting
    }

    const descriptionElementHandle = descriptionElements[index];
    console.log(`Elemento de descripción encontrado para: "${description}"`);

    // Encontrar el contenedor padre que contiene el input
    const parentDivHandle = await descriptionElementHandle.evaluateHandle(el =>
      el.closest('div[class^="cell-"]')
    ) as ElementHandle<Element> | null;

    if (!parentDivHandle) {
      console.log(`Contenedor padre no encontrado para la descripción: "${description}"`);
      continue;
    }

    // Acceder al siguiente elemento hermano (nextElementSibling)
    const nextSiblingHandle = await parentDivHandle.evaluateHandle(el =>
      el.nextElementSibling
    ) as ElementHandle<Element> | null;

    if (!nextSiblingHandle) {
      console.log(`Siguiente hermano no encontrado para el contenedor padre de: "${description}"`);
      continue;
    }

    // Buscar el input dentro del siguiente hermano
    const inputElementHandle = await nextSiblingHandle.$('input.input-RUSovanF');

    if (!inputElementHandle) {
      console.log(`Elemento de input no encontrado para la descripción: "${description}"`);
      continue;
    }

    console.log(`Elemento de input encontrado para: "${description}"`);

    // Enfocar y seleccionar el texto existente
    await inputElementHandle.click({ clickCount: 3 });


    // Esperar 70 ms antes de escribir el nuevo valor
    await new Promise(resolve => setTimeout(resolve, 1)); // 5 milisegundos

    // Escribir el nuevo valor de manera rápida y eficiente
    await inputElementHandle.type(newValue, { delay: 1 }); // Delay reducido para mayor velocidad


    console.log(`Actualizado "${description}" a "${newValue}"`);


  }
}
