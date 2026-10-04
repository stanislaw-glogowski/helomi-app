import type { HelomiClient } from './client';
import { ClientError } from './client.error';
import { toCamelCase } from './helpers';
import type {
  Command,
  CommandOptions,
  CommandResult,
  ReactionKind,
  SessionEvent,
} from './types';

/**
 * Manages an active speech session for a specific voice profile.
 * Handles SSE event subscription and API response command dispatching.
 */
export class HelomiSession {
  /** HTTP header name used for session authentication. */
  static readonly HEADER_KEY = 'x-session-id';

  private sessionId?: string;

  constructor(
    private readonly profileId: string,
    private readonly client: HelomiClient,
  ) {}

  /**
   * Sends synthesized speech text to the application for playback.
   */
  async sayText(text: string, options?: CommandOptions): Promise<boolean> {
    return this.sendCommand(
      {
        type: 'say_text',
        text,
        mode: 'api',
      },
      options,
    );
  }

  /**
   * Sends a configured spoken reaction to the application.
   */
  async sayReaction(reaction: ReactionKind, options?: CommandOptions): Promise<boolean> {
    return this.sendCommand(
      {
        type: 'say_reaction',
        reaction,
        mode: 'api',
      },
      options,
    );
  }

  async close(options?: CommandOptions): Promise<boolean> {
    return this.sendCommand(
      {
        type: 'end_conversation',
        playFarewell: true,
      },
      options,
    );
  }

  /**
   * Subscribes to the server-sent events stream for this profile.
   * Yields events such as `session_started`, `transcription_ready`, and `speech_interrupted`.
   */
  async *subscribe(): AsyncIterable<SessionEvent> {
    if (this.sessionId) {
      throw new ClientError('HelomiSession already started');
    }

    const response = await this.client.fetch(`/profile/${this.profileId}/stream`, {
      timeout: false,
    });

    const sessionId = response.headers.get(HelomiSession.HEADER_KEY);

    if (!sessionId) {
      throw new ClientError('HelomiSession ID not found in response headers');
    }

    if (!response.body) {
      throw new ClientError('No response body');
    }

    this.sessionId = sessionId;

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    try {
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() ?? '';

        for (const block of events) {
          const type = block.match(/^event:\s*(.+)$/m)?.[1]?.trim();
          const data = block.match(/^data:\s*(.+)$/m)?.[1]?.trim();

          if (!type || !data) {
            continue;
          }

          try {
            yield {
              type,
              ...toCamelCase<object>(JSON.parse(data)),
            } as SessionEvent;
          } catch (cause) {
            throw new ClientError(`Invalid SSE payload for event ${type}`, { cause });
          }
        }
      }
    } finally {
      this.sessionId = undefined;
      try {
        await reader.cancel();
      } catch {
        // The connection may already be closed by the server or network stack.
      }
      reader.releaseLock();
    }

    yield {
      type: 'session_ended',
    };
  }

  private get headers(): Record<string, string> {
    if (!this.sessionId) {
      throw new ClientError('HelomiSession not started');
    }
    return {
      [HelomiSession.HEADER_KEY]: this.sessionId,
    };
  }

  private async sendCommand(
    command: Command,
    options: CommandOptions = {},
  ): Promise<boolean> {
    return this.client
      .send<CommandResult>('/command', {
        headers: this.headers,
        command,
        ...options,
      })
      .then(({ accepted }) => accepted);
  }
}
