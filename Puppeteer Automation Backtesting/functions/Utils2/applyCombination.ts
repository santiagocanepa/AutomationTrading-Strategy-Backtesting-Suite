import { Page } from 'puppeteer'
import { applyRiskManagementSettings } from './applyRiskManagementSettings.js'
import { applyIndicatorSettings } from './applyIndicatorSettings.js'
import { timer, getHumanizedWaitTime } from '../Utils/timeUtils.js'

export async function applyCombination (page: Page, combination: any): Promise<void> {
  // Clickear el botón "4 horas" o temporalidad deseada, tambien se puede eliminar la linea y configurar directamente la temporalidad en el diseño del grafico.
  await page.evaluate(() => {
    const button4h = document.querySelector('button[aria-label="4 horas"][role="radio"][data-value="240"]') as HTMLElement
    button4h?.click()
  })

  // Clickear el botón "Abrir Simulador de estrategias"
  await page.evaluate(() => {
    const buttonSimulator = document.querySelector('button[aria-label="Abrir Simulador de estrategias"][data-name="backtesting"]') as HTMLElement
    buttonSimulator?.click()
  })
  // Clickear el botón con icono SVG
  await page.waitForSelector('button svg[viewBox="0 0 18 18"] path[d="M4.73 2h8.54L17 9l-3.73 7H4.73L1 9l3.73-7Zm-2.6 7 3.2-6h7.34l3.2 6-3.2 6H5.33l-3.2-6Z"]', { visible: true });
  await page.evaluate(() => {
    const buttonSvg = document.querySelector('button svg[viewBox="0 0 18 18"] path[d="M4.73 2h8.54L17 9l-3.73 7H4.73L1 9l3.73-7Zm-2.6 7 3.2-6h7.34l3.2 6-3.2 6H5.33l-3.2-6Z"]') as SVGPathElement;
    const buttonElement = buttonSvg?.closest('button') as HTMLElement;
    buttonElement?.click();
  });


  // Aplicar configuración de gestión de riesgo
  await applyRiskManagementSettings(page, { ...combination.riskManagement, ...combination.requires })

  // Aplicar configuración de indicadores
  await applyIndicatorSettings(page, combination.indicators)
  await getHumanizedWaitTime(500, 1000)

  // Hacer clic en el botón "Aceptar"
  const acp = await page.evaluate(() => {
    const acceptButton = Array.from(document.querySelectorAll('button')).find(button => {
      return button.querySelector('span.content-D4RPB3ZC')?.textContent?.trim() === 'Aceptar'
    })

    if (acceptButton) {
      acceptButton.click()
      
      return "Botón 'Aceptar' clickeado con éxito."
    } else {
      return "Botón 'Aceptar' no encontrado."
    }
    
  })

  console.log(acp)
}
