# Recorded prompts

The `livekit.yaml` and `pipecat.yaml` examples expect three short recordings in
this folder: `hello.wav`, `question.wav`, and `interrupt.wav`. Record them
yourself as mono WAV files, ideally 16 kHz, with a little silence trimmed from
each end. voicebench downmixes and resamples other formats.

Real agents run speech-to-text and a neural VAD on your audio, so synthetic
test signals from `voicebench synth` do not work for them.
