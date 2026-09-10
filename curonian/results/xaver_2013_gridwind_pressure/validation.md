# Xaver 2013 validation

Whole period: 2013-11-28 00:00 to 2013-12-11 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 13 | -0.01 | 0.09 | 0.90 | +0.12 | +26 |
| Nida | 26 | -0.00 | 0.10 | 0.76 | -0.08 | +48 |
| Vente | 26 | +0.06 | 0.11 | 0.75 | +0.16 | -60 |
| Uostadvaris | 13 | -0.06 | 0.09 | 0.88 | +0.04 | +0 |

Storm window: 2013-12-05 00:00 to 2013-12-09 00:00

| station | n | bias m | RMSE m | r | peak err m | peak dt h |
|---|---|---|---|---|---|---|
| Klaipeda | 4 | -0.03 | 0.12 | 0.72 | +0.12 | +26 |
| Nida | 8 | -0.02 | 0.14 | 0.38 | -0.12 | -68 |
| Vente | 8 | +0.07 | 0.14 | 0.35 | +0.16 | -60 |
| Uostadvaris | 4 | -0.05 | 0.11 | 0.77 | +0.04 | +0 |

Flooded land in the delta window (depth > 5 cm, ground > 0 m): **140.8 km²**

### Success criteria (spec section 9)
- C1 Uostadvaris peak [2013-12-05 00:00 to 2013-12-09 00:00]: **met** -- model peak 2013-12-06 06:10, peak err +0.04 m, dt +0.2 h (threshold: peak err within +/-0.15 m and |dt| <= 6 h)
- C2 Nida 8 Dec rise [2013-12-07 06:00 to 2013-12-08 18:00]: **met (marginal)** -- model 0.48 m -> 0.71 m vs gauge 0.84 m, err -0.13 m, rise reproduced (threshold: err within +/-0.15 m (<=0.10 m for a clean 'met'), rise reproduced in sign)
- C3 Klaipeda RMSE [2013-12-05 00:00 to 2013-12-09 00:00]: **met** -- storm RMSE 0.12 m (whole-period RMSE 0.09 m) (threshold: storm-window RMSE <= 0.15 m)
- C4 Silute uplands [delta window (325000, 6105000, 360000, 6145000)]: **met** -- 0.00% of land with ground > 3 m flooded (threshold: < 1 % flooded)
- Info: Uostadvaris 8 Dec 06:00 [2013-12-08 06:00]: **info** -- model 0.62 m vs gauge 0.83 m, err -0.21 m (threshold: n/a (context only))
- Info: Nida 8 Dec 06:00 [2013-12-08 06:00]: **info** -- model 0.55 m vs gauge 0.74 m, err -0.19 m (threshold: n/a (context only))
