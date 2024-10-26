# TradingView Indicator/Strategy by icanepa
![image](https://github.com/user-attachments/assets/f16f1dee-80c6-46ed-85c5-56d6484a9728)
![image](https://github.com/user-attachments/assets/8931ad4c-c0ac-4f7c-af9f-e73682ca1efb)
![image](https://github.com/user-attachments/assets/f42b43fe-efc5-4a93-adb9-99e7c976ed7a)

## 📈 Description.

This TradingView indicator implements an advanced trading strategy that combines multiple oscillator and trend indicators to generate buy and sell signals. Designed for momentum trading, this strategy avoids range zones and optimizes risk management through flexible and customizable settings. With more than 15 built-in indicators, it allows extensive customization to suit various time frames and trading styles.


## 📜 Indicator Code

The source code of the indicator is available in this repository. The following details how the strategy works and the available configurations.

## 🛠️ Indicators Used

## 1. **Absolute Strength (Histogram)** 
  - **Description:** Absolute strength oscillator, very effective in all time frames.
    - **Configurations:** Customizable from the interface. 
  - **Conditions:** **Buying conditions:** **Buying conditions:**
    - **Buy:** Strong uptrend.
    - **Sell:** Weak bearish trend.


## 2. **SSL Channel**
  - **Description:** Moving average indicator with crossover, used to determine trends.
  - **Settings:** Adjustable from the interface.
    - **Length:** Adjustable from the interface.
  - **Buying and Selling Conditions**: 
    - **Buy:** `sslUp > sslDown`.
    - **Sale:** `sslUp < sslDown`.


```pinescript
// SSL Channel conditions
ssl_purchase = sslUp > sslDown
ssl_sale = sslUp < sslDown

if (first_take_profit_hit[1])
if (ssl_buy) // Use counter signal to close short position
strategy.close('Sell', comment='Trailing S')

if (first_take_profit_hit[1])
if (ssl_sell) // Use contrarian signal to close long position
strategy.close('Buy', comment='Trailing L')
```

  - **Trailing Stop**
    
    - **Sell**
      - **Stop**: Above `sslDown`.
    
    - **Buy**
      - **Stop**: Below `sslDown`.
  
  - **Recommendations**
    - Do not use crosses instead of `>` or `<` operators to allow multiple indicators to participate in the conditions.

## 3. **Firestorm**

- **Description**
Generates buy and sell signals based on breakouts of defined levels.

- **Configurations**
  - **Firestorm Multiplier**:
    - Timings of 1 hour or less: `≥ 3`.
    - Timeframes of 4 hours or greater: `≥ 2`.

- **Conditions**
  - **Buy**: Breakage of `up`.
    - **Sale**: Break of `dn`.
    - **Signal Timing**: Configurable (keeps signal for 10 candles, configurable).

```pinescript
// Determination of Stop Loss based on Firestorm
stop_loss_price := up * 0.996 
stop_loss_price := dn * 1.004 
```


- **Recommendations**
  - Firestorm Multiplier: Use a multiplier of 3 or more for 1-hour or shorter timeframes, and 2 for 4-hour or longer timeframes if a higher trading rate is sought.

## 4. **RSI (Relative Strength Index)**

- **Description**
  - Oscillator to measure trend strength.

- **Conditions**
  - **Buy**: RSI > 55.
  - **Sell**: RSI < 45.

- **Objective**
  - To capture impulses instead of reversals.


## 5. **Squeeze Momentum**

- **Description**
  - Momentum indicator adjustable to different timeframes.

- **Conditions**
  - **Buy**: Strong uptrend or weak downtrend.
  - **Sell**: Strong downtrend or weak uptrend.

- **Recommended Settings**
  - Effective in 4 hour time frames or longer.

## 6. **MACD Signal**

- **Description**
  - MACD oscillator to identify trends.

- **Conditions**
  - **Buy**: Strong uptrend or weak downtrend.
  - **Sell**: Strong downtrend or weak uptrend.

## 7. **MACD Histogram**

- **Description**
  - MACD Oscillator Histogram to measure trend strength.

- **Conditions**
  - **Buy**: Strong uptrend or weak downtrend.
  - **Sell**: Strong downtrend or weak uptrend.


## 8. **MTF conditions (Multi-Time Frame)**

- **Description**
  - Uses 5 configurable moving averages.

- **Configurations**
  - **Length and Timing**: Adjustable from the interface.
  - **State of the Averages**:
    - Exclusive: Price must be above (buy) or below (sell) all.
    - Optional: Price must be only above or below one of the enabled averages.

- **Recommendations**
  - **Key Lengths**: 20, 50, 200.
  - **Number of Averages**: Maximum 3.
  - **Seasonalities**: Greater than operating season.
  - **Status**: Optional.


## 9. **EMA conditions**

- **Description**
  - Uses 2 configurable EMAs.

- **Default Settings**
  - EMAs: 200 and 600.

- **Conditions**
  - **Buy**: Price above both EMAs.
  - **SELL**: Price below both EMAs.

## 10. **Distance between EMAs**

- **Description**
  - Calculates the distance between EMAs 200 and 600.

- **Objective**
  - Avoid range zones.

- **Condition**
  - Operates only if the distance between EMAs is greater than the distance between SSL Channel lines.


## 11. **Valid Distance StopLoss**

- **Description**
  - Prevents entries when the price is too far away from the stop loss.

- **Objective**
  - To maintain short stops without saturating trades.

- **Cons**
  - Loses important trades by not entering in strong movements.
- **Condition**
  - Compare stop loss distance, based on Firestorm and SSL Channel lines.

## 12. **WaveTrend Reversal**

- **Description**
  - WaveTrend oscillator to identify reversals.

- **Conditions**
  - **Buy**: Strong uptrend or weak downtrend.
  - **Sell**: Strong downtrend or weak uptrend.

## 13. **WaveTrend Divergence**

- **Description**
  - Detects divergence in the WaveTrend indicator.

- **Settings**
  - **Indicator Selection**: More than 10 built-in indicators.
  - **Number of Indicators needed for Divergence**: Configurable.
  - **Signal Persistence**: Configurable (a wide candlestick range is recommended to maintain the signal).

## 14. **Activate Divergence**

- **Description**
  - Enables or disables divergence detection.

- **Configurations**
  - Configurable indicators:
  - Enable Squeeze Momentum
  - Enable MACD Signal
  - Enable MACD Histogram
  - Enable WaveTrend Reversal
  - Enable WaveTrend Divergence
    - **Seasonalities**: Configurable in 3 different seasonalities.
    - **Excluders/Options** configuration:
    - Excludable: Conditions must be fulfilled in all marked temporalities.
    - Optional: Condition must be fulfilled in at least one of the enabled temporalities.

- **Recommendations**
  - Use more than one seasonality, preferably higher than the trading season.
  - Especially for Squeeze Momentum and WaveTrend.


## **⚙️ General Settings**

- ## Optional Indicators Required

- **Description**
  - Defines how many indicators selected as optional are required to display a condition.

- **Recommendations**
  - **Range**: 5 - 8 required for 10 enabled.

- **Objective**
  - Avoid saturation of operations with a lower range.
  - Avoid optional indicators being almost exclusive with a higher rank.

## **🛡️ Risk Management**

  - ## Multiplier for Take Profit
  
    - **Description**
      - Based on the stop loss, a multiplier is used to calculate the profit.
  
    - **Operation**
      - When executing the take profit, a portion of the position with trailing stop is allowed to run and the stop loss is adjusted to the entry price.
    
    - **Recommendations**
      - Time frames of 4 hours or more: Multiplier between 0.30 and 0.50.
      - Smaller time frames: Multiplier a little higher.
  
  - ## Percentage of Profit Taking
  
    - ##Description##
      - Determines the percentage of the position that is closed when the first take profit is reached.
  
    - **Operation**
      - Closes a part of the position and lets the rest run with trailing stop based on the SSL Channel and adjusts the stop loss to the breakeven price.
  
  - **Recommendations**
    - Range: 25% - 60%.
  
  - ## Commission to Calculate the Breakeven
  
    - **Description**
      - Set the commission multiplier to adjust the new stop to the breakeven after the first take profit.
  
    - **Example:**
      - Crypto on Exchanges like Binance or OKX:
      - Commission: 0.07% per order.
      - Multiplier for Breakeven: 1.0007.


## 🔧 **Using the Indicator**

  - **Import the Script into TradingView**
    1. Open TradingView and log in to your account.
    2. Go to the “Pine Editor” section.
    3. Copy and paste the contents of `script.pine`.
    4. Click “Save” and then “Add to Chart”.


  - **Parameter Settings**
    - **Optional Indicators Required**: Select how many optional indicators are required to trigger a signal.
    - **Take Profit Multiplier**: Adjust according to your profit targets.
    - **Position Close Percentage**: Define the percentage of the position to close when the first take profit is reached.
    - **Commission for Breakeven**: Set according to the commissions of your exchange.

## **Additional recommendation**
  - Calculate the commission in properties, normally 0.07% in crypto exchange, or 0.001 in currencies or stocks, depending on the liquidity of the asset in the broker and the spread.
    To properly test each strategy, use an illustrative capital and a fixed nominal in dollars that represents a maximum of 20% of the initial capital, a number higher than this could generate losses that prevent the strategy to 
    continue generating orders and the backtesting could not be completed. Defining a fixed percentage on the capital for each order or a number of contracts may not accurately measure the strategy over time, when comparing one     
    strategy to another, it is important to define these values in the same way. 
    For example:

![image](https://github.com/user-attachments/assets/3e99507e-c7e2-4baf-93be-3b997f0cd0bb)

# 📚 References.
  - [Pine Script Documentation](https://es.tradingview.com/pine-script-reference/v5/)

# 🧑‍💻 Contribution
  - If you would like to contribute to this pointer, feel free to contact me.

# 📞 Contact
  - Santiago Canepa - canepasantiago.ivan@gmail.com


