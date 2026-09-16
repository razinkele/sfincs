# April 2013 Nemunas freshet validation

Whole period: 2013-04-05 00:00 to 2013-05-02 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 27 | -0.12 | 0.15 | 0.73 | -0.15 | +19 |
| Nida | 54 | -0.12 | 0.13 | 0.99 | -0.15 | +12 |
| Vente | 54 | +0.01 | 0.04 | 0.97 | -0.02 | -6 |
| Uostadvaris | 27 | -0.16 | 0.21 | 0.92 | -0.23 | +18 |

Scoring window: 2013-04-13 00:00 to 2013-05-02 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 19 | -0.16 | 0.18 | 0.77 | -0.15 | +19 |
| Nida | 38 | -0.13 | 0.14 | 0.99 | -0.15 | +12 |
| Vente | 38 | -0.00 | 0.04 | 0.96 | -0.02 | -6 |
| Uostadvaris | 19 | -0.22 | 0.25 | 0.88 | -0.23 | +18 |

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **81.0 km²**

### Success criteria (spec section 9)
- A1 Uostadvaris peak [2013-04-13 00:00 to 2013-05-02 00:00]: **not met** -- model peak 0.31 m vs gauge 0.54 m, err -0.23 m (threshold: peak err within +/-0.15 m)
- A2a filling rate [first crossing of +0.20 m]: **not met** -- model 2013-04-23 17:20 vs gauge (interpolated) 2013-04-19 08:00, dt +105 h (threshold: within +/-24 h of the observed crossing)
- A2b crest timing [2013-04-21 18:00 to 2013-04-24 18:00]: **not met** -- model peak 2013-04-25 00:10; observed plateau 22 Apr-24 Apr (threshold: model peak inside the observed plateau +/-12 h)
- A3 delta-to-sea head [2013-04-22 00:00 to 2013-04-26 00:00]: **met** -- model 0.35 m vs gauge 0.48 m over 5 readings, err -0.13 m (threshold: mean head within +/-0.15 m)
- A4 Klaipeda control [2013-04-13 00:00 to 2013-05-02 00:00]: **not met** -- RMSE 0.176 m against an observed sd of 0.089 m (threshold: RMSE <= 0.085 m (below the observed sd of 0.089 m: a flat series fails))
- A5 Silute uplands [whole run, delta window (325000, 6105000, 360000, 6145000)]: **met** -- 0.00% of land with ground > 3 m flooded (threshold: < 1 % flooded)
