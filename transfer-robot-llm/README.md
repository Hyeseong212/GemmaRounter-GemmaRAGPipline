# Gemma Transfer Robot LLM Project

This project is the local-LLM workspace for the transfer robot.

Its current job is intentionally narrow:

- correct STT transcripts
- generate a short answer or guidance line
- hand off clean text for TTS playback

## Current LLM Scope

Use the local LLM mainly for:

- STT correction after speech recognition
- response generation from corrected speech
- TTS-friendly output text

Example flow:

1. User speech is converted to text by STT.
2. The local LLM corrects the STT transcript.
3. The local LLM generates a concise reply or guidance sentence.
4. TTS plays the final sentence.

## Hardware-First Areas

These areas should stay in the hardware or control stack for now:

- lidar-based situation understanding
- lift and actuator control
- deterministic safety logic
- motion or procedure control

That means the robot should detect events and decide physical actions with algorithms first, then use TTS to speak the right message.

## Notes

- `first-router` is for the haptic medical-device project.
- `transfer-robot-llm` is for the transfer-robot local-LLM project.
- Procedure-control references for hardware algorithms can be added later when the hardware side is clearer.

## Files

- prompt: [`prompts/transfer_robot_system_prompt.txt`](/home/rb/AI/transfer-robot-llm/prompts/transfer_robot_system_prompt.txt)
- request example: [`examples/stt_correction_request.json`](/home/rb/AI/transfer-robot-llm/examples/stt_correction_request.json)
- response example: [`examples/stt_correction_response.json`](/home/rb/AI/transfer-robot-llm/examples/stt_correction_response.json)
- architecture note: [`docs/llm-scope.md`](/home/rb/AI/transfer-robot-llm/docs/llm-scope.md)
- run: [`scripts/run_local_gemma.sh`](/home/rb/AI/transfer-robot-llm/scripts/run_local_gemma.sh)
- manage: [`scripts/manage_local_gemma.sh`](/home/rb/AI/transfer-robot-llm/scripts/manage_local_gemma.sh)

## Runtime Defaults

The transfer-robot wrapper now starts with a conservative GPU-safe profile:

- model variant: `e2b`
- context: `2048`
- batch size: `128`
- ubatch size: `32`
- GPU enabled
- GPU layers: `8`
- KV offload disabled
- op offload disabled

This is intentional so the service can use Jetson GPU memory with a smaller 2B model, avoid the earlier OOM case, and reduce throttling pressure on the current Orin setup.
