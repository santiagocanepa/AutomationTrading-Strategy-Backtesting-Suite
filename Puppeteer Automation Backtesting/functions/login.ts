import puppeteer, { Browser, Page } from 'puppeteer'
import { existsSync } from 'node:fs'
import { readFile, writeFile } from 'node:fs/promises'
import { selectors, paths, url } from '../constants/selectors.js'
import { puppeteerOptions } from '../constants/options.js'
import { timer, getHumanizedWaitTime } from './Utils/timeUtils.js'

const { loginSelectors } = selectors

async function loadCookies (page: Page): Promise<void> {
  if (existsSync(paths.cookiesPath)) {
    const cookies = JSON.parse(await readFile(paths.cookiesPath, 'utf-8'))
    await page.setCookie(...cookies)
  }
  await page.goto(url.mainUrl)
  await getHumanizedWaitTime(1000, 2000)
}

async function saveCookies (page: Page): Promise<void> {
  const cookies = await page.cookies()
  await writeFile(paths.cookiesPath, JSON.stringify(cookies), 'utf-8')
}

async function manualLogin (page: Page): Promise<void> {
  console.log('Por favor, inicia sesión manualmente en el siguiente minuto...')
  await timer(90000) // Espera 60 segundos para que puedas iniciar sesión manualmente
  console.log('Guardando cookies...')
  await saveCookies(page)
  console.log('Cookies guardadas exitosamente.')
}

async function isLogin (page: Page): Promise<void> {
  if (existsSync(paths.cookiesPath)) {
    console.log('Archivo de cookies encontrado.')
  } else {
    await manualLogin(page)
  }
}

export async function init (): Promise<{ browser: Browser, page: Page }> {
  const browser = await puppeteer.launch(puppeteerOptions)
  const page = await browser.newPage()
  await loadCookies(page)
  await isLogin(page)

  return { browser, page }
}
