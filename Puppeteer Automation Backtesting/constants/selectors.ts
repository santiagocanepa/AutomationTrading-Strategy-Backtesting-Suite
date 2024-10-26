import { join } from 'node:path'
import { config } from 'dotenv'

config()

export const selectors = {


  loginSelectors: {
    usernameInput: 'input[aria-label="Phone number, username, or email"]',
    passwordInput: 'input[aria-label="Password"',
    isLoginSelector: 'span.xuxw1ft'
  },
};

export const paths = {
  cookiesPath: join(process.cwd(), 'cookies', 'cookies.json')
}



const paginasAdicionales: string[] = [
  'https://www.google.com',
  'https://www.linkedin.com',
  'https://drive.google.com',
  'https://mail.google.com',
  'https://www.tradingview.com',
  'https://www.github.com',
  'https://www.youtube.com',
  'https://www.twitter.com',
  'https://www.reddit.com',
  'https://www.amazon.com',
];

// Función para obtener una página aleatoria
function obtenerPaginaAleatoria(): string {
  const indiceAleatorio = Math.floor(Math.random() * paginasAdicionales.length);
  return paginasAdicionales[indiceAleatorio];
}

export const url = {
  mainUrl: `https://es.tradingview.com/chart/TozXby3G/`, #Link del grafico a utilizar
  chartUrl: `https://es.tradingview.com/chart/TozXby3G/` #Link del grafico a utilizar
}