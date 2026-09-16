# Xaver 2013 validation

Whole period: 2013-11-28 00:00 to 2013-12-11 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 13 | -0.01 | 0.08 | 0.90 | +0.12 | +26 |
| Nida | 26 | -0.01 | 0.06 | 0.92 | -0.02 | +2 |
| Vente | 26 | +0.05 | 0.08 | 0.85 | +0.05 | +2 |
| Uostadvaris | 13 | -0.06 | 0.07 | 0.96 | -0.11 | -0 |

Storm window: 2013-12-05 00:00 to 2013-12-09 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 4 | -0.03 | 0.12 | 0.72 | +0.12 | +26 |
| Nida | 8 | -0.06 | 0.09 | 0.86 | -0.05 | +0 |
| Vente | 8 | +0.03 | 0.09 | 0.78 | +0.04 | +0 |
| Uostadvaris | 4 | -0.10 | 0.11 | 0.96 | -0.11 | -0 |

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **130.6 km²**

### Success criteria (spec section 9)
- C1 Uostadvaris peak [2013-12-05 00:00 to 2013-12-09 00:00]: **met** -- model peak 2013-12-06 05:40, peak err -0.11 m, dt -0.3 h (threshold: peak err within +/-0.15 m and |dt| <= 6 h)
- C2 Nida 8 Dec rise [2013-12-07 06:00 to 2013-12-08 18:00]: **met** -- model 0.43 m -> 0.79 m vs gauge 0.84 m, err -0.05 m, rise reproduced (threshold: err within +/-0.15 m (<=0.10 m for a clean 'met'), rise reproduced in sign)
- C3 Klaipeda RMSE [2013-12-05 00:00 to 2013-12-09 00:00]: **met** -- storm RMSE 0.12 m (whole-period RMSE 0.08 m) (threshold: storm-window RMSE <= 0.15 m)
- C4 Silute uplands [delta window (325000, 6105000, 360000, 6145000)]: **met** -- 0.00% of land with ground > 3 m flooded (threshold: < 1 % flooded)
- Info: Uostadvaris 8 Dec 06:00 [2013-12-08 06:00]: **info** -- model 0.70 m vs gauge 0.83 m, err -0.13 m (threshold: n/a (context only))
- Info: Nida 8 Dec 06:00 [2013-12-08 06:00]: **info** -- model 0.63 m vs gauge 0.74 m, err -0.11 m (threshold: n/a (context only))
