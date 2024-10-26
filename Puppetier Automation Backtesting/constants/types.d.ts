interface GeneratorType {
  action: string
  error?: Error | unknown
}

export {
  GeneratorType
}

// puppeteer-extension.d.ts
import { ElementHandle, Page } from 'puppeteer';

declare module 'puppeteer' {
  interface Page {
    $x(expression: string): Promise<ElementHandle[]>;
  }
}
