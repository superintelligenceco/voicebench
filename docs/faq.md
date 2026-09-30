# FAQ

## Does voicebench need a real voice agent to try it?

No. The bundled `mock` adapter is a deterministic agent with delays that you configure in the scenario. Run `voicebench example mock-conversation -O demo.yaml` and then `voicebench run demo.yaml`.

## Do the demo numbers describe a real product?

No. The numbers in the demo come from the mock agent. They show what the report looks like, not how any vendor performs.

## Why are my latency numbers higher than my vendor dashboard?

voicebench measures at the audio, from the end of your speech to the start of the agent's speech, including the network, jitter buffers, and codec delay. Vendor dashboards usually report individual pipeline stages. Run voicebench close to the agent if you want to isolate the agent itself.

## How does voicebench decide that the agent stopped for a barge-in?

It runs the VAD over the agent track and measures from the start of your interrupting turn to the end of the agent's speech segment. If the agent sends a `clear` event, voicebench drops the audio it had buffered but not played, the way a client playback buffer would.

## Can I use voicebench in CI?

Yes. Put limits in the scenario's `assert` block. `voicebench run` exits with status 1 when a limit fails, so the job fails with it. Use `--no-write` to skip the report files.

## Which transports are supported?

The `mock` and `websocket` adapters are covered by the test suite. The `livekit` and `pipecat` adapters are experimental: install them with `pip install 'voicebench[livekit]'` or `pip install 'voicebench[pipecat]'`. To support another transport, subclass `voicebench.adapters.Adapter`, as shown in [Adapters](adapters.md).

## Why do the executable and the container image lack the LiveKit and Pipecat adapters?

Their SDKs are large and platform-specific. The executable and the image carry the core adapters only. Install the Python package with the matching extra to use them.

## How do I verify a download?

Each release attaches a `SHA256SUMS` file and build provenance attestations. Check a file with `sha256sum --check --ignore-missing SHA256SUMS`, or with `gh attestation verify voicebench-linux-x64 --repo superintelligenceco/voicebench`. The container image is signed with cosign keyless signing:

```sh
cosign verify ghcr.io/superintelligenceco/voicebench:latest \
  --certificate-identity-regexp '^https://github.com/superintelligenceco/voicebench/' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```
