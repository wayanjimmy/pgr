# entireio_cli_offline_ir_public60_pre_read

Public offline retrieval benchmark using weak labels from baseline `read_code` decisions.

## Setup

- Query cases: 132
- Runs: 42
- Tasks: 42
- Conditions: `baseline`, `fff`, `pgr`
- Relevance signal: unique files the baseline agent opened with `read_code` in that run

## Overall

| Metric | Baseline | `fff` | `pgr` |
|---|---:|---:|---:|
| MRR | 0.2271 | 0.1764 | 0.2640 |
| Hit@1 | 17.4% | 10.6% | 22.0% |
| Hit@3 | 24.2% | 23.5% | 28.8% |
| Avg output chars | 2225.7 | 978.7 | 1449.4 |

## Paired by task

- **MRR fff vs baseline:** -0.048, 95% CI [-0.115, +0.019]
- **MRR pgr vs baseline:** +0.067, 95% CI [-0.007, +0.141]
- **Hit@1 fff vs baseline:** -11.6 points, 95% CI [-21.5, -1.7]
- **Hit@1 pgr vs baseline:** +5.1 points, 95% CI [-4.1, +14.4]
- **Hit@3 fff vs baseline:** +6.6 points, 95% CI [-2.9, +16.1]
- **Hit@3 pgr vs baseline:** +10.4 points, 95% CI [+0.8, +20.0]
- **output chars fff vs baseline:** -1056, 95% CI [-1408, -705]
- **output chars pgr vs baseline:** -751, 95% CI [-1022, -480]
