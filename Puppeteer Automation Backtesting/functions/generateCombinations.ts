export type IndicatorOption = 'Opcional' | 'Excluyente' | 'Desactivado';
export type TimeframeOption = 'T1' | 'T2' | 'T3';

export interface Indicator {
  name: string;
  mode: IndicatorOption;
  hasTimeframes?: boolean;
}

export interface Combination {
  indicators: {
    name: string;
    mode: IndicatorOption;
    activeTimeframes?: TimeframeOption[];
  }[];
  optionalCount: number;
  profitMultiplier: number;
  closePercentage: number;
}

export function generateCombinations(
  indicators: Indicator[],
  optionalCounts: number[],
  profitMultipliers: number[],
  closePercentages: number[]
): Combination[] {
  const combinations: Combination[] = [];

  const indicatorCombinations = generateIndicatorCombinations(indicators);

  for (const indicatorCombination of indicatorCombinations) {
    for (const optionalCount of optionalCounts) {
      for (const profitMultiplier of profitMultipliers) {
        for (const closePercentage of closePercentages) {
          combinations.push({
            indicators: indicatorCombination,
            optionalCount,
            profitMultiplier,
            closePercentage,
          });
        }
      }
    }
  }

  return combinations;
}

function generateIndicatorCombinations(indicators: Indicator[]): Combination['indicators'][] {
  const results: Combination['indicators'][] = [];

  function recurse(index: number, currentCombination: Combination['indicators']) {
    if (index === indicators.length) {
      results.push([...currentCombination]);
      return;
    }

    const indicator = indicators[index];

    recurse(index + 1, currentCombination);

    currentCombination.push({ name: indicator.name, mode: indicator.mode });
    recurse(index + 1, currentCombination);
    currentCombination.pop();

    if (indicator.hasTimeframes) {
      const timeframeCombinations = generateTimeframeCombinations(['T1', 'T2', 'T3']);
      for (const timeframes of timeframeCombinations) {
        currentCombination.push({
          name: indicator.name,
          mode: indicator.mode,
          activeTimeframes: timeframes,
        });
        recurse(index + 1, currentCombination);
        currentCombination.pop();
      }
    }
  }

  recurse(0, []);
  return results;
}

function generateTimeframeCombinations(timeframes: TimeframeOption[]): TimeframeOption[][] {
  const results: TimeframeOption[][] = [];

  function recurse(index: number, currentCombination: TimeframeOption[]) {
    if (index === timeframes.length) {
      if (currentCombination.length > 0) {
        results.push([...currentCombination]);
      }
      return;
    }

    recurse(index + 1, currentCombination);

    currentCombination.push(timeframes[index]);
    recurse(index + 1, currentCombination);
    currentCombination.pop();
  }

  recurse(0, []);
  return results;
}

const indicators: Indicator[] = [
  { name: 'Absolute Strength', mode: 'Opcional' },
  { name: 'MACD', mode: 'Opcional', hasTimeframes: true },
  { name: 'WaveTrend', mode: 'Opcional', hasTimeframes: true },
  { name: 'RSI', mode: 'Opcional', hasTimeframes: true },
  { name: 'Squeeze Momentum', mode: 'Opcional', hasTimeframes: true },
];

const optionalCounts = [1, 2, 3];
const profitMultipliers = [1.5, 2.0, 3.0];
const closePercentages = [50, 75, 100];

const allCombinations = generateCombinations(indicators, optionalCounts, profitMultipliers, closePercentages);
