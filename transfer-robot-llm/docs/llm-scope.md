# Transfer Robot LLM Scope

## Use LLM For

- STT transcript correction
- short answer generation
- TTS-friendly wording
- light intent normalization for downstream modules

## Do Not Use LLM First For

- lidar interpretation
- obstacle detection
- lift state judgment
- actuator control
- navigation control
- safety-critical decision making

## Recommended Runtime Flow

1. STT produces a raw transcript.
2. Local LLM corrects the transcript and creates a short reply.
3. Hardware and control modules determine real robot actions.
4. TTS plays the final approved message.

## Design Direction

For the transfer robot, it is more useful to let algorithms detect robot state and events, then ask the LLM to polish or produce spoken guidance when needed.
