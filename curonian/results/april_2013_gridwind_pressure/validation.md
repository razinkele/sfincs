# April 2013 Nemunas freshet validation

Whole period: 2013-04-05 00:00 to 2013-05-02 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 27 | +0.00 | 0.00 | 1.00 | +0.01 | +19 |
| Nida | 54 | -0.09 | 0.09 | 0.98 | -0.10 | -58 |
| Vente | 54 | +0.05 | 0.06 | 0.97 | +0.05 | -6 |
| Uostadvaris | 27 | +0.07 | 0.11 | 0.94 | +0.05 | +18 |

Scoring window: 2013-04-13 00:00 to 2013-05-02 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 19 | +0.00 | 0.00 | 1.00 | +0.01 | +19 |
| Nida | 38 | -0.07 | 0.08 | 0.98 | -0.10 | -58 |
| Vente | 38 | +0.06 | 0.07 | 0.97 | +0.05 | -6 |
| Uostadvaris | 19 | +0.09 | 0.13 | 0.90 | +0.05 | +18 |

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **60.0 km²**

### Success criteria (spec section 9)
- A1 Uostadvaris peak [2013-04-13 00:00 to 2013-05-02 00:00]: **met** -- model peak 0.59 m vs gauge 0.54 m, err +0.05 m (threshold: peak err within +/-0.15 m)
- A2a filling rate [first crossing of +0.20 m]: **not met** -- model 2013-04-15 18:20 vs gauge (interpolated) 2013-04-19 08:00, dt -86 h (threshold: within +/-24 h of the observed crossing)
- A2b crest timing [2013-04-21 18:00 to 2013-04-24 18:00]: **not met** -- model peak 2013-04-25 00:20; observed plateau 22 Apr-24 Apr (threshold: model peak inside the observed plateau +/-12 h)
- A3 delta-to-sea head [2013-04-22 00:00 to 2013-04-26 00:00]: **met** -- model 0.49 m vs gauge 0.48 m over 5 readings, err +0.01 m (threshold: mean head within +/-0.15 m)
- A4 Klaipeda boundary fit [2013-04-13 00:00 to 2013-05-02 00:00]: **info** -- RMSE 0.001 m against an observed sd of 0.089 m (threshold: n/a -- the sea boundary is fitted to these readings; not an independent test)
- A5 Silute uplands [whole run, delta window (325000, 6105000, 360000, 6145000)]: **met** -- 0.00% of land with ground > 3 m flooded (threshold: < 1 % flooded)
- A6a Rusne rise [2013-04-13 00:00 to 2013-05-02 00:00]: **not met** -- model 1.33 m vs gauge 1.53 m above the 05-11 Apr mean, err -0.20 m (daily values; gauge zero unknown, rise only) (threshold: rise within +/-0.15 m)
- A6b Rusne crest date [19 Apr to 24 Apr]: **met** -- model crest 21 Apr; observed plateau 20 Apr-23 Apr (threshold: model crest inside the observed plateau +/-1 day)
