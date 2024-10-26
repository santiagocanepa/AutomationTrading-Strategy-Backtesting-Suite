// min-max = Son el minimo y el maximo del rango aleatorio
// stdDevPercentage = Desviaciòn estadar expresada porcentualmente sobre el rango min-max y representa la oscilaciòn desde la media.
// deviationMultiplier = Multiplica el rango para crear una desviaciòn exponencial.
//significantDeviationProbability = Probabilidad de que la desviaciòn exponencial ocurra.
export function getHumanizedNumber(
  min: number = 700,
  max: number = 1700,
  stdDevPercentage: number = 0.9, 
  deviationMultiplier: number = 1.25,
  significantDeviationProbability: number = 0.1 
): number {
  function getRandomNormal(mean: number, stdDev: number) {
    let u = 0, v = 0;
    while(u === 0) u = Math.random(); 
    while(v === 0) v = Math.random(); 
    return mean + stdDev * Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  }

  function getRandomExponential(rate: number) {
    let u = Math.random();
    return -Math.log(1 - u) / rate;
  }

  const mean = (min + max) / 2;
  const range = max - min;
  const stdDev = range * stdDevPercentage;

  let result = getRandomNormal(mean, stdDev);
  
  if (Math.random() < significantDeviationProbability) { 
    const maxExponentialDeviation = (max - mean) * deviationMultiplier;
    const exponentialDeviation = getRandomExponential(1 / stdDev) * stdDev;
    result += Math.min(exponentialDeviation, maxExponentialDeviation);
  }

  if (result < min) result = min;
  if (result > max) result = max;

  return Math.floor(result);
}




export function getRandom(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min
}

export function getHumanizedWaitTime(
  min: number = 700,
  max: number = 1700,
  stdDevPercentage: number = 0.9, 
  deviationMultiplier: number = 1.25,
  significantDeviationProbability: number = 0.1 
): Promise<void> {
  function getRandomNormal(mean: number, stdDev: number) {
    let u = 0, v = 0;
    while(u === 0) u = Math.random(); 
    while(v === 0) v = Math.random(); 
    return mean + stdDev * Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  }

  function getRandomExponential(rate: number) {
    let u = Math.random();
    return -Math.log(1 - u) / rate;
  }

  const mean = (min + max) / 2;
  const range = max - min;
  const stdDev = range * stdDevPercentage;

  let result = getRandomNormal(mean, stdDev);
  
  if (Math.random() < significantDeviationProbability) { 
    const maxExponentialDeviation = (max - mean) * deviationMultiplier;
    const exponentialDeviation = getRandomExponential(1 / stdDev) * stdDev;
    result += Math.min(exponentialDeviation, maxExponentialDeviation);
  }

  if (result < min) result = min;
  if (result > max) result = max;

  return new Promise((resolve) => setTimeout(resolve, Math.floor(result)));
}



export const timer = (waitTime: number): Promise<void> => {
  return new Promise((resolve) => setTimeout(resolve, waitTime));
}