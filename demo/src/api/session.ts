import type { Client } from './client';
import { ClientError } from './client.error';
import { toCamelCase } from './helpers';
import type { Command, CommandOptions, Reaction, SessionEvent } from './types';

/**
 * Manages an active speech session for a specific voice profile.
 * Handles SSE event subscription and command dispatching (`say_text`, `activate_profile`, etc.).
 */
export class Session {
  /** HTTP header name used for session authentication. */
  static readonly HEADER_KEY = 'x-session-id';

  private sessionId?: string;

  constructor(
    private readonly profileId: string,
    private readonly client: Client,
  ) {
    //
  }

  /**
   * Sends synthesized speech text to the audio pipeline for playback.
   */
  async sayText(text: string, options?: CommandOptions): Promise<boolean> {
    return this.sendCommand(
      {
        type: 'say_text',
        text,
        profileId: this.profileId,
      },
      options,
    );
  }

  /**
   * Sends synthesized speech text to the audio pipeline for playback.
   */
  async sayReaction(reaction: Reaction, options?: CommandOptions): Promise<boolean> {
    return this.sendCommand(
      {
        type: 'say_reaction',
        reaction,
        profileId: this.profileId,
      },
      options,
    );
  }

  async close(options?: CommandOptions): Promise<boolean> {
    return this.sendCommand(
      {
        type: 'deactivate_profile',
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
      throw new ClientError('Session already started');
    }

    const response = await this.client.fetch(`/profile/${this.profileId}/stream`);

    const sessionId = response.headers.get(Session.HEADER_KEY);

    if (!sessionId) {
      throw new ClientError('Session ID not found in response headers');
    }

    this.sessionId = sessionId;

    if (!response.body) {
      throw new ClientError('No response body');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

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
        } catch {
          //
        }
      }
    }

    if (this.sessionId) {
      this.sessionId = undefined;

      yield {
        type: 'session_ended',
      };
    }
  }

  private get headers(): Record<string, string> {
    if (!this.sessionId) {
      throw new ClientError('Session not started');
    }
    return {
      [Session.HEADER_KEY]: this.sessionId,
    };
  }

  private async sendCommand(
    command: Command,
    options: CommandOptions = {},
  ): Promise<boolean> {
    return this.client
      .send<{
        success: boolean;
      }>('/command', {
        headers: this.headers,
        command,
        ...options,
      })
      .then(({ success }) => success);
  }
}
