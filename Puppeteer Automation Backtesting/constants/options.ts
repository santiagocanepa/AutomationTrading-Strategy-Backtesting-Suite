import dotenv from 'dotenv'

dotenv.config()

const userAgent = process.env.USERAGENT || 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.2 Safari/605.1.15'
const width = parseInt(process.env.WIDTH || '2560', 10)
const height = parseInt(process.env.HEIGHT || '1440', 10)

export const puppeteerOptions = {
  headless: true,
  slowMo: 50,
  executablePath: '/usr/bin/google-chrome-stable',
  args: [
    '--lang=en-US',
    `--user-agent=${userAgent}`,
    '--accept-lang=en-US',
    '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-gpu',
      '--disable-dev-shm-usage',
      '--disable-accelerated-2d-canvas',
      '--disable-sync',
      '--mute-audio',
      '--disable-features=site-per-process',
      '--metrics-recording-only'
  ],
  defaultViewport: {
    width,
    height
  }
}
