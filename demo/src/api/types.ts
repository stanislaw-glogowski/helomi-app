/**
 * Representation of a loaded Helomi voice profile.
 */
export type Profile<TPrompt = string | null> = {
  id: string;
  name: string;
  emoji: string;
  prompt: TPrompt;
  hasWakeword: boolean;
  isActive: boolean;
  isReadonly: boolean;
};

export type ReactionKind = 'greeting' | 'farewell' | 'interrupted';
export type ResponseMode = 'api' | 'parrot' | 'operator';

/**
 * Options for generic API calls.
 */
export type CallOptions = {
  abort?: AbortSignal;
};

/**
 * Options for commands sent to the Helomi application.
 */
export type CommandOptions = CallOptions & {
  traceId?: string;
};

/**
 * Options for raw HTTP requests sent by HelomiClient.
 */
export type RequestOptions = CommandOptions & {
  headers?: Record<string, string>;
  command?: Command;
  query?: Record<string, string | undefined>;
  timeout?: number | boolean;
};

/**
 * Generic message envelope matching the Helomi message schema.
 */
export type Envelope<
  TType extends string,
  TData extends Record<string, unknown> = Record<never, never>,
> = {
  type: TType;
  traceId?: string | undefined;
} & TData;

/**
 * Command payloads accepted by POST /api/v1/command.
 */
export type Command =
  | Envelope<
      'say_text',
      {
        text: string;
        mode: ResponseMode;
      }
    >
  | Envelope<
      'say_reaction',
      {
        reaction: ReactionKind;
        mode: ResponseMode;
      }
    >
  | Envelope<
      'end_conversation',
      {
        playFarewell: boolean;
      }
    >;

export type CommandResult = {
  accepted: boolean;
  rejectionCode: string | null;
  detail: string | null;
};

/**
 * Base profile event payload envelope.
 */
export type ProfileEvent<
  TType extends string,
  TData extends Record<string, unknown> = Record<never, never>,
> = Envelope<
  TType,
  {
    profileId: string;
  } & TData
>;

/**
 * Event types emitted during an active SSE speech session.
 */
export type SessionEvent =
  | Envelope<'session_started' | 'session_ended'>
  | ProfileEvent<'profile_activated' | 'profile_deactivated' | 'speech_interrupted'>
  | ProfileEvent<
      'transcription_ready',
      {
        text: string;
      }
    >;
