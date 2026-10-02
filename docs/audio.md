# Audio Routing and Assets

Helomi mounts every configured audio driver behind one `AudioRouter` and keeps exactly one conversation route active.
The local `avfaudio` driver uses the native Swift `AVAudioEngine` helper. The optional `twilio` driver handles inbound
bidirectional Media Streams.

## Local audio

```yaml
audio:
  initial_driver: avfaudio
  monitor_driver: avfaudio
  drivers:
  - avfaudio
  avfaudio:
    voice_processing: true
```

Apple voice processing enables echo cancellation and automatic gain control. Blocking native driver work stays off
the asyncio event loop.

## Routing behavior

- An inbound Twilio call atomically takes over the active route and selects its profile from the called number.
- Local microphone capture is ignored while the remote route is active.
- Optional monitoring sends only inbound caller audio to `avfaudio`; synthesis and room voice are not duplicated.
- The previous route is restored after hangup.
- A second call is rejected as busy.
- Switching away from a live remote call requires explicit confirmation and disconnects before changing route.

Set `monitor_driver: null` or omit it to disable monitoring. The tray's Call window can mute configured monitoring
without changing the response mode.

## Twilio playback

Speech and driver-specific room voice are mixed in float32 20 ms frames. The mixer applies ambient volume and speech
ducking, clips the result, resamples it, and emits headerless μ-law audio at 8 kHz. Output is paced in real time with a
bounded queue.

Each logical playback ends with a Twilio `mark`; the returned mark acknowledges completion. Barge-in sends `clear`,
cancels stale synthesis/playback by turn ID, and continues capturing the caller's utterance.

See [Settings Configuration](settings.md) for webhook and driver setup.

## Synthesis streaming

Each synthesis request keeps its complete input text. Model audio is coalesced into 100 ms portions and played while
generation continues, with at most one second of unacknowledged speech buffered across the application and driver.
The producer waits for playback capacity instead of dropping audio. Text requests retain FIFO order without a fixed
item limit; barge-in, profile changes, and route changes discard obsolete work.

The playback acknowledgement timeout includes the remaining buffered duration plus `app.conversation.playback_ack_timeout`
seconds of transport grace. Failed requests emit `processing_failed` and do not terminate the processing loops.
Completed synthesis still exposes the full clean audio for WAV export. VoxCPM2 reference features are reused per profile
when normalization and denoising are disabled.

## Reference and room audio

Use clean mono WAV files. Paths in a profile are relative to that profile when written with `path://`:

```yaml
audio:
  avfaudio:
    room_voice:
      path: path://assets/ambient.wav
      volume: 0.25
      ducking: 0.35

synthesis:
  voxcpm2:
    ref_audio: path://assets/ref_audio.wav
```

A voice-cloning reference should normally contain 10–20 seconds of clear speech. Room voice is looped only inside the
active driver; synthesis events and WAV exports remain clean.
