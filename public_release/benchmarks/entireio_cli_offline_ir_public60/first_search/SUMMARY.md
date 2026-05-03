# entireio_cli_offline_ir_public60_first_search

Public offline retrieval benchmark using weak labels from baseline `read_code` decisions.

## Setup

- Query cases: 50
- Runs: 50
- Tasks: 50
- Conditions: `baseline`, `fff`, `pgr`
- Relevance signal: unique files the baseline agent opened with `read_code` in that run

## Overall

| Metric | Baseline | `fff` | `pgr` |
|---|---:|---:|---:|
| MRR | 0.3177 | 0.3059 | 0.4053 |
| Hit@1 | 26.0% | 18.0% | 34.0% |
| Hit@3 | 34.0% | 42.0% | 42.0% |
| Avg output chars | 6565.9 | 1427.0 | 1587.1 |

## Paired by task

- **MRR fff vs baseline:** -0.012, 95% CI [-0.089, +0.066]
- **MRR pgr vs baseline:** +0.088, 95% CI [-0.007, +0.182]
- **Hit@1 fff vs baseline:** -8.0 points, 95% CI [-17.7, +1.7]
- **Hit@1 pgr vs baseline:** +8.0 points, 95% CI [-4.7, +20.7]
- **Hit@3 fff vs baseline:** +8.0 points, 95% CI [-3.3, +19.3]
- **Hit@3 pgr vs baseline:** +8.0 points, 95% CI [-1.7, +17.7]
- **output chars fff vs baseline:** -5139, 95% CI [-13648, +3371]
- **output chars pgr vs baseline:** -4979, 95% CI [-13485, +3527]
