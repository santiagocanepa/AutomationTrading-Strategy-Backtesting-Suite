
# Indicador/Estrategia de TradingView por icanepa
![image](https://github.com/user-attachments/assets/b010edf3-5c6f-4c78-9410-bbe50daf1c42)
![image](https://github.com/user-attachments/assets/82653854-cd95-4da0-aa40-b7e9961d830e)
![image](https://github.com/user-attachments/assets/8a423216-0c8e-4e37-86bb-aacafb8d35f3)

## 📈 Descripción

Este indicador de TradingView implementa una estrategia de trading avanzada que combina múltiples indicadores osciladores y de tendencia para generar señales de compra y venta. Diseñado para operar por impulso, esta estrategia evita zonas de rango y optimiza la gestión de riesgo mediante configuraciones flexibles y personalizables. Con más de 15 indicadores integrados, permite una personalización extensa para adaptarse a diversas temporalidades y estilos de trading.

## 🔗 Enlace al Indicador en TradingView

## 📜 Código del Indicador

El código fuente del indicador está disponible en este repositorio. A continuación, se detalla cómo funciona la estrategia y las configuraciones disponibles.

## 🛠️ Indicadores Utilizados

## 1. **Absolute Strength (Histograma)**
  - **Descripción:** Oscilador de fuerza absoluta, muy efectivo en todas las temporalidades.
  - **Configuraciones:** 
    - Personalizable desde la interfaz.
  - **Condiciones:**
    - **Compra:** Tendencia alcista fuerte.
    - **Venta:** Tendencia bajista débil.

## 2. **SSL Channel**
  - **Descripción:** Indicador de medias móviles con cruce, utilizado para determinar tendencias.
  - **Configuraciones:**
    - **Longitud:** Ajustable desde la interfaz.
    - **ATR Multiplicador para Firestorm:** Configurable.
  - **Condiciones de Compra y Venta:**
    - **Compra:** `sslUp > sslDown`
    - **Venta:** `sslUp < sslDown`
  
    ```pinescript
    // Condiciones del SSL Channel
    ssl_compra = sslUp > sslDown
    ssl_venta = sslUp < sslDown
  
    if (first_take_profit_hit[1])
        if (ssl_compra)  // Usar señal contraria para cerrar posición corta
            strategy.close('Venta', comment='Trailing S')
  
    if (first_take_profit_hit[1])
        if (ssl_venta)  // Usar señal contraria para cerrar posición larga
            strategy.close('Compra', comment='Trailing L')
    ```


- **Trailing Stop**

  - **Venta**
    - **Stop**: Por encima de `sslDown`.

  - **Compra**
    - **Stop**: Por debajo de `sslDown`.

- **Recomendaciones**
  - No Utilizar cruces en lugar de operadores `>` o `<` para permitir la participación de múltiples indicadores en las condiciones.

## 3. **Firestorm**

- **Descripción**
  - Genera señales de compra y venta basadas en rupturas de niveles definidos.

- **Configuraciones**
  - **Multiplicador Firestorm**:
    - Temporalidades de 1 hora o menores: `≥ 3`.
    - Temporalidades de 4 horas o mayores: `≥ 2`.

- **Condiciones**
  - **Compra**: Ruptura de `up`.
  - **Venta**: Ruptura de `dn`.
  - **Temporalidad de Señales**: Configurable (mantiene la señal por 10 velas, configurable).
  
  ```pinescript
  // Determinación del Stop Loss basado en Firestorm
  stop_loss_price := up * 0.996 
  stop_loss_price := dn * 1.004  
  ```

**Recomendaciones**
  - Multiplicador Firestorm: Utilizar un multiplicador de 3 o más para temporalidades de 1 hora o menores, y de 2 para temporalidades de 4 horas o mayores si se busca una tasa mayor de operaciones.

## 4. **RSI (Relative Strength Index)**

- **Descripción**
  - Oscilador para medir la fuerza de la tendencia.

**Condiciones**
  - **Compra**: RSI > 55.
  - **Venta**: RSI < 45.

**Objetivo**
  - Capturar impulsos en lugar de reversiones.

## 5. Squeeze Momentum

- **Descripción**
  - Indicador de momentum ajustable a diferentes temporalidades.

- **Condiciones**
  - **Compra**: Tendencia alcista fuerte o tendencia bajista débil.
  - **Venta**: Tendencia bajista fuerte o tendencia alcista débil.

- **Configuración Recomendada**
  - Efectivo en temporalidades de 4 horas o mayores.



## 6. MACD Signal

- **Descripción**
  - Oscilador MACD para identificar tendencias.

- **Condiciones**
  - **Compra**: Tendencia alcista fuerte o tendencia bajista débil.
  - **Venta**: Tendencia bajista fuerte o tendencia alcista débil.

## 7. MACD Histograma

- **Descripción**
  - Oscilador MACD Histograma para medir la fuerza de la tendencia.

- **Condiciones**
  - **Compra**: Tendencia alcista fuerte o tendencia bajista débil.
  - **Venta**: Tendencia bajista fuerte o tendencia alcista débil.

## 8. Condiciones MTF (Multi-Time Frame)

- **Descripción**
  - Utiliza 5 medias móviles configurables.

- **Configuraciones**
  - **Longitud y Temporalidad**: Ajustable desde la interfaz.
  - **Estado de las Medias**:
    - Excluyentes: Precio debe estar por encima (compra) o por debajo (venta) de todas.
    - Opcionales: Precio debe estar solo por encima o por debajo de una de las medias habilitadas.
  
- **Recomendaciones**
  - **Longitudes Claves**: 20, 50, 200.
  - **Cantidad de Medias**: Máximo 3.
  - **Temporalidades**: Superiores a la de operación.
  - **Estado**: Opcional.
  
## 9. Condiciones EMAs

- **Descripción**
  - Utiliza 2 EMAs configurables.

- **Configuraciones Predeterminadas**
  - EMAs: 200 y 600.

- **Condiciones**
  - **Compra**: Precio por encima de ambas EMAs.
  - **Venta**: Precio por debajo de ambas EMAs.

## 10. Distancia entre EMAs

- **Descripción**
  - Calcula la distancia entre EMAs 200 y 600.

- **Objetivo**
  - Evitar zonas de rango.

- **Condición**
  - Opera solo si la distancia entre EMAs es mayor que la distancia entre las líneas del SSL Channel.

## 11. Distancia Válida StopLoss

- **Descripción**
  - Evita entradas cuando el precio está muy alejado del stop loss.

- **Objetivo**
  - Mantener stops cortos sin saturar las operaciones.

- **Contras**
  - Pierde operaciones importantes por no entrar en movimientos fuertes.

- **Condición**
  - Compara la distancia del stop loss, basado en Firestorm y las lineas del SSL Channel.

## 12. WaveTrend Reversal

- **Descripción**
  - Oscilador WaveTrend para identificar reversiones.

- **Condiciones**
  - **Compra**: Tendencia alcista fuerte o tendencia bajista débil.
  - **Venta**: Tendencia bajista fuerte o tendencia alcista débil.

## 13. WaveTrend Divergence

- **Descripción**
  - Detecta divergencias en el indicador WaveTrend.

- **Configuraciones**
  - **Selección de Indicadores**: Más de 10 indicadores integrados.
  - **Cantidad de Indicadores Necesarios para Divergencia**: Configurable.
  - **Persistencia de la Señal**: Configurable (se recomienda un margen amplio de velas para mantener la señal).

## 14. Activar Divergencia

- **Descripción**
  - Permite activar o desactivar la detección de divergencias.

## Configuraciones
- **Indicadores Configurables**:
  - Activar Squeeze Momentum
  - Activar MACD Signal
  - Activar MACD Histograma
  - Activar WaveTrend Reversal
  - Activar WaveTrend Divergence
- **Temporalidades**: Configurables en 3 temporalidades distintas.
- **Configuración de Excluyentes/Opcionales**:
  - Excluyentes: Condiciones deben cumplirse en todas las temporalidades marcadas.
  - Opcionales: Condición debe cumplirse en al menos una de las temporalidades habilitadas.

- **Recomendaciones**
  - Utilizar más de una temporalidad, preferentemente superiores a la de operación.
  - Especialmente para Squeeze Momentum y WaveTrend.

## ⚙️ Configuraciones Generales

- **Indicadores Opcionales Requeridos**

- **Descripción**
  - Define cuántos indicadores seleccionados como opcionales son necesarios para mostrar una condición.

- **Recomendaciones**
  - **Rango**: 5 - 8 requeridos por 10 habilitados.

- **Objetivo**
  - Evitar saturación de operaciones con un rango menor.
  - Evitar que los indicadores opcionales sean casi excluyentes con un rango mayor.

## 🛡️ Gestión de Riesgo

- **Multiplier for Take Profit**

  - **Descripción**
    - Basado en el stop loss, se utiliza un multiplicador para calcular el profit.

  - **Funcionamiento**
    - Al ejecutar el take profit, se deja correr una parte de la posición con trailing stop y se ajusta el stop loss al precio de entrada.

  - **Recomendaciones**
    - Temporalidades de 4 horas o más: Multiplicador entre 0.30 y 0.50.
    - Temporalidades menores: Multiplicador un poco más alto.

- **Porcentaje de Toma de Ganancias**
  - **Descripción**
    - Determina el porcentaje de la posición que se cierra al alcanzar el primer take profit.
  
  - **Funcionamiento**
    - Cierra una parte de la posición y deja correr el resto con trailing stop basado en el SSL Channel y ajusta el stop loss al precio de breakeven.
  
  - **Recomendaciones**
    - Rango: 25% - 60%.
  
- **Comisión para Calcular el Breakeven**
  
  - **Descripción**
    - Configura el multiplicador de la comisión para ajustar el nuevo stop al breakeven después del primer take profit.
  
  - **Ejemplo**
    - Crypto en Exchanges como Binance u OKX:
      - Comisión: 0.07% por orden.
      - Multiplicador para Breakeven: 1.0007.
  
  
## 🔧 Uso del Indicador

- **Importar el Script en TradingView**
  1. Abre TradingView y accede a tu cuenta.
  2. Ve a la sección de "Pine Editor".
  3. Copia y pega el contenido de `script.pine`.
  4. Haz clic en "Guardar" y luego en "Agregar al gráfico".

- **Configuración de Parámetros**
  - **Indicadores Opcionales Requeridos**: Selecciona cuántos indicadores opcionales son necesarios para activar una señal.
  - **Multiplicador para Take Profit**: Ajusta según tus objetivos de ganancias.
  - **Porcentaje de Cierre de Posición**: Define el porcentaje de la posición a cerrar al alcanzar el primer take profit.
  - **Comisión para Breakeven**: Configura según las comisiones de tu exchange.
  
## Recomendación adicional
Calcular la comision en propiedades, normalmente 0.07% en exchengue de criptos, o 0.001 en divisas o acciones, segun la liquidez del activo en el broker y el spread.
Para testear correctamente cada estrategia, utilizar un capital ilustrativo y un nominal fijo en dolares que represente un maximo del 20% del capital inicial , un numero mayor a este pudiera generar perdidas que impida a la estrategia seguir generando ordenes y el backtesting no se completara. Definir un porcentaje fijo sobre el capital para cada orden o una cantidad de contratos podria no medir con exactitud la estrategia a lo largo del tiempo, al compara una estrategia con otra, es importante definir estos valores de la misma manera. 
Por ejemplo:

![image](https://github.com/user-attachments/assets/3e99507e-c7e2-4baf-93be-3b997f0cd0bb)

## 📚 Referencias
- [Documentación de Pine Script](https://es.tradingview.com/pine-script-reference/v5/)

## 🧑‍💻 Contribución
- Si deseas contribuir a este indicador, no dudes en contactarme.

## 📞 Contacto
- Santiago Canepa – canepasantiago.ivan@gmail.com
