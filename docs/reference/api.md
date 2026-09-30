# Python API reference

The docs build generates this page from the docstrings in the source. Most users need only `run_benchmark` and `load_scenario`:

```python
import asyncio

from voicebench.bench import run_benchmark
from voicebench.scenario import load_scenario

result = asyncio.run(run_benchmark(load_scenario("examples/mock-conversation.yaml")))
print(result.summary["response_latency_ms"]["p50"], result.passed)
```

## Running a benchmark

::: voicebench.bench

## Scenarios

::: voicebench.scenario

## Adapters

::: voicebench.adapters.base

## Voice activity detection

::: voicebench.vad

## Metrics

::: voicebench.metrics

## Word error rate

::: voicebench.wer
