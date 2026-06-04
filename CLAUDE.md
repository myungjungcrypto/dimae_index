# Dimaejipyo Notes

## Sentiment Index Scoring

- The headline dashboard score is a rolling 24-hour observation, not a KST day-to-date cumulative score.
- User-facing labels should say `Greed` and `Fear`. Keep internal field names such as `fomo_score` and `risk_score` for database/API compatibility.
- The 0-100 scale should be calibrated against historical `daily_snapshots`, not against only the current 24-hour window.
- Use up to 90 prior daily checkpoints as the baseline distribution.
- If fewer than 14 baseline days exist, keep `index_score` at 50 and mark the regime as `calibrating`.
- Treat 0 and 100 as distribution-relative extremes, not absolute market truths:
  - 100 means the current 24-hour signal is near the top of the available historical distribution across several Greed components.
  - 0 means the current 24-hour signal is near the bottom of the available historical distribution and/or dominated by Fear components.
- Current composite weights:
  - New weighted mentions percentile: 30%
  - Greed (`fomo_score`) percentile: 25%
  - Sentiment percentile: 15%
  - Search trend momentum percentile: 10%
  - Fear (`risk_score`) inverse percentile: 15%
  - Spam rate inverse percentile: 5%
- Daily snapshots are KST daily checkpoints of the rolling 24-hour score. Hourly snapshots are hourly checkpoints of the same rolling 24-hour score.
- For weekly backtests, compare both `daily_snapshots` and `hourly_snapshots` against KOSPI, Nasdaq, and Bitcoin returns, and avoid overfitting thresholds before enough observed data exists.
