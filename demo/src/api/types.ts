/**
 * Representation of a loaded Helomi voice profile.
 */
export type Profile = {
  id: string;
  name: string;
  isActive: boolean;
};

/**
 * Options for generic API calls.
 */
export type CallOptions = {
  abort?: AbortSignal;
};

/**
 * Options for commands sent to the speech pipeline.
 */
export type CommandOptions = CallOptions & {
  trace_id?: string;
};

/**
 * Options for raw HTTP requests sent by Client.
 */
export type RequestOptions = CommandOptions & {
  headers?: Record<string, string>;
  command?: Command;
};

/**
 * Generic message envelope matching Helomi pipeline schema.
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
        profileId: string;
        text: string;
      }
    >
  | Envelope<
      'activate_profile',
      {
        profileId: string;
      }
    >
  | Envelope<'deactivate_profile'>;

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
