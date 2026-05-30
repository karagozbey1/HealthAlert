# Activity v2.1 Source Error Analysis

## 1. Source Test Metrics
- PAMAP2: accuracy=0.5459, macro_f1=0.5419, weighted_f1=0.5681, n=1502
- UCI-HAR: accuracy=0.8772, macro_f1=0.7991, weighted_f1=0.8686, n=1230

## 2. Source Per-Class Recall
### PAMAP2
- walking: 0.6757
- sitting: 0.6961
- standing: 0.3634
- lying: 0.4460

### UCI-HAR
- walking: 0.9984
- sitting: 0.8923
- standing: 0.3676
- lying: 1.0000

## 3. Source-Specific Confusion Matrices
Rows = actual, columns = predicted.

### PAMAP2
| Actual \ Pred | walking | sitting | standing | lying |
|---------------|---|---|---|---|
| walking | 325 | 6 | 8 | 142 |
| sitting | 1 | 197 | 72 | 13 |
| standing | 0 | 240 | 137 | 0 |
| lying | 0 | 199 | 1 | 161 |

### UCI-HAR
| Actual \ Pred | walking | sitting | standing | lying |
|---------------|---|---|---|---|
| walking | 616 | 0 | 1 | 0 |
| sitting | 0 | 174 | 21 | 0 |
| standing | 0 | 129 | 75 | 0 |
| lying | 0 | 0 | 0 | 214 |

## 4. Subject-Level Breakdown
| Source | Subject | n | Macro F1 | Walking R | Sitting R | Standing R | Lying R |
|--------|---------|---|----------|-----------|-----------|------------|---------|
| PAMAP2 | S102 | 512 | 0.2318 | 0.0994 | 0.8545 | 0.0000 | 0.3826 |
| PAMAP2 | S107 | 480 | 0.3192 | 0.9639 | 0.0500 | 0.2047 | 0.0157 |
| PAMAP2 | S108 | 510 | 0.9283 | 0.9675 | 0.8850 | 0.8952 | 0.9664 |
| UCI-HAR | s01 | 347 | 0.9295 | 1.0000 | 1.0000 | 0.7358 | 1.0000 |
| UCI-HAR | s07 | 308 | 0.7578 | 0.9935 | 0.9583 | 0.2264 | 1.0000 |
| UCI-HAR | s08 | 281 | 0.6677 | 1.0000 | 1.0000 | 0.0185 | 1.0000 |
| UCI-HAR | s10 | 294 | 0.7928 | 1.0000 | 0.6481 | 0.5227 | 1.0000 |

## 5. PAMAP2 Subject Error Distribution
| Subject | n | Macro F1 | Posture Confusions | Top Confusion Pairs |
|---------|---|----------|--------------------|---------------------|
| S107 | 480 | 0.3192 | 283 | lying->sitting:125, standing->sitting:101, sitting->standing:55, walking->standing:5, sitting->lying:2 |
| S102 | 512 | 0.2318 | 212 | walking->lying:142, standing->sitting:126, lying->sitting:71, sitting->lying:11, sitting->standing:4 |
| S108 | 510 | 0.9283 | 30 | sitting->standing:13, standing->sitting:13, lying->sitting:3, walking->standing:3, walking->sitting:2 |

## 6. Raw Channel Mean/Std Difference
| Source | Channel | Mean | Std |
|--------|---------|------|-----|
| UCI-HAR | acc_x | 0.806737 | 0.412435 |
| UCI-HAR | acc_y | 0.020894 | 0.397373 |
| UCI-HAR | acc_z | 0.084699 | 0.344685 |
| UCI-HAR | gyro_x | -0.002993 | 0.406942 |
| UCI-HAR | gyro_y | 0.000001 | 0.366841 |
| UCI-HAR | gyro_z | 0.001898 | 0.253681 |
| PAMAP2 | acc_x | 0.460798 | 1.213199 |
| PAMAP2 | acc_y | 7.668720 | 3.996798 |
| PAMAP2 | acc_z | 1.918240 | 4.600780 |
| PAMAP2 | gyro_x | 0.004593 | 0.199837 |
| PAMAP2 | gyro_y | 0.006106 | 0.273431 |
| PAMAP2 | gyro_z | -0.015215 | 0.179562 |

### Delta PAMAP2 - UCI-HAR
- acc_x: mean_delta=-0.345939, std_delta=0.800764
- acc_y: mean_delta=7.647826, std_delta=3.599425
- acc_z: mean_delta=1.833541, std_delta=4.256095
- gyro_x: mean_delta=0.007586, std_delta=-0.207105
- gyro_y: mean_delta=0.006105, std_delta=-0.093410
- gyro_z: mean_delta=-0.017113, std_delta=-0.074119

## 7. Mapping Check
- Current failed baseline uses PAMAP2 chest IMU 6g accelerometer + gyroscope.
- UCI-HAR uses smartphone waist total acceleration + body gyroscope.
- Sensor location mismatch remains even when both are 6-channel IMU streams.
