# AMATYA Predictive Intelligence & Time-Series Forecasting (Phase 14.7)

## 1. Overview
The Predictive Intelligence module (`core/predictive_intelligence.py`) provides mathematical time-series modeling, automated model selection, uncertainty quantification, and statistical anomaly detection.

---

## 2. Deterministic Forecasting Models

### A. Linear Trend Model (`LinearTrendModel`)
- Fits $y = m x + b$ via polynomial regression.
- Quantifies standard error $S_e = \sqrt{\frac{\sum (y_i - \hat{y}_i)^2}{n - 2}}$.
- Prediction intervals widen over the forecast horizon:
  $$\sigma(h) = S_e \sqrt{1 + \frac{1}{n} + \frac{h^2}{n}}$$

### B. Polynomial Trend Model (`PolynomialTrendModel`)
- Fits degree-$d$ polynomial curve ($d=2$ quadratic default) for accelerating or decelerating series.
- Suitable for degradation curves and non-linear physical accumulation.

### C. Holt's Exponential Smoothing (`ExponentialSmoothingModel`)
- Decomposes series into dynamic level ($L_t$) and trend ($T_t$):
  $$L_t = \alpha y_t + (1 - \alpha)(L_{t-1} + T_{t-1})$$
  $$T_t = \beta (L_t - L_{t-1}) + (1 - \beta) T_{t-1}$$
- Yields responsive forecasts without overfitting noisy historical fluctuations.

---

## 3. Evaluation Metrics & Holdout Selection
Candidate models are benchmarked using strict numerical metrics:
- **Mean Absolute Error (MAE):** $\frac{1}{n}\sum |y_i - \hat{y}_i|$
- **Root Mean Squared Error (RMSE):** $\sqrt{\frac{1}{n}\sum (y_i - \hat{y}_i)^2}$
- **Mean Absolute Percentage Error (MAPE):** $\frac{100\%}{n}\sum \left|\frac{y_i - \hat{y}_i}{y_i}\right|$
- **Coefficient of Determination ($R^2$):** $1 - \frac{SS_{res}}{SS_{tot}}$

When `model_type="auto"`, an 80/20 train/validation split is evaluated across all candidate models, selecting the lowest validation RMSE.

---

## 4. Anomaly & Change-Point Detection
- **Point Anomalies:** Z-score thresholding $|y_i - \mu| / \sigma > 2.0$.
- **Change Points:** CUSUM detection over the first-difference series $|\Delta y_i - \mu_{\Delta}| / \sigma_{\Delta} > 2.5$.

