# ADR-0006: Natural voice conversation policy

- Status: Accepted
- Date: 2026-08-03
- Supersedes: None
- Superseded by: None
- Implementation: None

## Context

Conversation quality in a local voice assistant is not determined by language-model
output alone. A natural exchange also depends on when Helomi decides that the user
has finished speaking, whether listener backchannels interrupt an answer, how an
interruption changes subsequent context, how much detail the assistant selects,
and when generated text becomes audible.

The current response router primarily selects a fast or detailed model from the
length and punctuation of the latest transcription. Other turn intents exist in
the domain model but do not drive distinct graph behavior. Conversation summaries
also run synchronously after every reply, keeping the live graph run occupied after
the visible response has been generated.

Helomi must improve this behavior without weakening its local privacy boundary,
moving voice-session policy into the conversation graph, or allowing background
maintenance to compete indefinitely with a new user turn.

## Decision or proposal

Treat natural conversation as an end-to-end policy spanning speech turn-taking,
conversation planning, context maintenance, and spoken delivery while preserving
the existing package ownership boundaries.

`helomi.speech` owns:

- turn endpointing and continuation windows;
- detection of high-confidence listener backchannels;
- playback ducking and interruption decisions;
- cancellation and draining of obsolete synthesis and playback work.

`helomi.conversation` owns:

- contextual turn planning using the current turn, recent history, and explicit
  interrupted-delivery context;
- whether a turn requires no response, cancellation, one clarification question,
  or a response with brief, standard, or detailed depth;
- finite graph execution, streamed reply segmentation, history, and summaries;
- deterministic fallback behavior when classification fails.

Use hybrid turn planning. Deterministic rules handle only outcomes that must be
safe and unambiguous, such as empty input and exact cancellation phrases. Obvious
standalone questions and explicit detailed requests avoid classifier latency.
Ambiguous acknowledgements, follow-ups, corrections, and underspecified requests
use the configured local classifier. Invalid classifier output falls back to a
standard response, never to silence or cancellation.

Finish the live graph run when the visible reply finishes. Run summarisation as
conversation-owned idle maintenance after completion. A new activation or user
turn preempts maintenance, and language-model operations remain serialized through
their existing service owner. Cancellation retains the last valid summary and the
certainly delivered prefix of an interrupted answer.

Treat human listening comparison as the quality acceptance gate. Automated tests
protect endpointing, routing, cancellation, context, and queue-accounting contracts,
but do not establish that timing or spoken delivery sounds natural. Compare the
baseline and candidate on the same target Mac, model, voice, profile, and scripted
Polish turns. The candidate must improve naturalness and appropriateness without a
regression in turn-taking, interruption, continuity, or brevity.

Alexa is the supported profile contract for this decision. Executable commands,
tool dispatch, and ignored local profiles are outside its scope.

## Consequences

Helomi can respond with better continuity and less mechanical timing because turn
completion, interruption, response depth, and delivery are coordinated explicitly.
Visible replies no longer wait for summarisation, and a new turn takes priority over
maintenance.

The design adds coordination between speech and conversation workers and requires
new deterministic contracts for endpoint assessment, backchannels, planning, and
maintenance preemption. Ambiguous turns incur classifier latency, while obvious
turns retain a direct path. Conservative fallbacks may occasionally produce a
short response where silence or clarification would have been preferable, but they
avoid the more harmful outcomes of suppressing a valid turn or cancelling it by
mistake.

Automated validation remains independent of microphones, speakers, Metal, models,
and downloads. Real endpoint timing, acoustic echo cancellation, interruption,
model latency, synthesis, and playback still require a separate hardware listening
review.

## Alternatives considered

- Keep the length-based response router: rejected because utterance length does not
  identify acknowledgements, corrections, clarification needs, cancellation, or
  conversational continuation.
- Classify every turn with a model: rejected because it adds avoidable latency and
  makes safety-sensitive silence and cancellation depend on generated output.
- Tune prompts only: rejected because prompts cannot repair premature endpointing,
  destructive backchannel handling, blocked live turns, or stale delivery state.
- Summarize synchronously after every reply: rejected because maintenance extends
  the critical path and delays a subsequent user turn.
- Treat every detected utterance during playback as an interruption: rejected
  because brief listener backchannels would unnecessarily destroy an active reply.

## References

- [ADR-0001: Package ownership and composition](0001-package-ownership-and-composition.md)
- [ADR-0002: Event-driven worker lifecycle](0002-event-driven-worker-lifecycle.md)
- [ADR-0003: Local settings and profile contract](0003-local-settings-and-profile-contract.md)
- [ADR-0005: Lazy local model adapters](0005-lazy-local-model-adapters.md)
- [Conversation architecture](../architecture/conversation.md)
- [Voice pipeline](../architecture/voice-pipeline.md)
- [Conversation benchmarks](../../benchmarks/conversation/README.md)
- [Voice benchmarks](../../benchmarks/voice/README.md)
