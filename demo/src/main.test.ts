import { describe, expect, it } from 'bun:test';
import type { Profile, SessionEvent } from './api';
import { getProfilesWithRetry, subscribeToProfile } from './main';

const profile: Profile<string> = {
  id: 'alexa',
  name: 'Alexa',
  emoji: '🤖',
  prompt: 'Be helpful.',
  hasWakeword: true,
  isActive: false,
  isReadonly: false,
};

const noReplyLlm = {
  async *streamReply(): AsyncIterable<string | null> {},
};

describe('demo reconnects', () => {
  it('waits indefinitely for profiles during startup', async () => {
    let attempts = 0;
    const delays: number[] = [];
    const api = {
      createSession: () => {
        throw new Error('Not used');
      },
      getProfiles: async () => {
        attempts += 1;
        if (attempts < 3) {
          throw new Error('Connection refused');
        }
        return [profile];
      },
    };

    const profiles = await getProfilesWithRetry(api, async (delayMs) => {
      delays.push(delayMs);
    });

    expect(profiles).toEqual([profile]);
    expect(delays).toEqual([1_000, 2_000]);
  });

  it('creates a new session after EOF and resets the backoff after connecting', async () => {
    const stop = new Error('Stop test');
    const delays: number[] = [];
    let sessionCount = 0;
    const api = {
      createSession: () => {
        sessionCount += 1;
        return {
          async *subscribe(): AsyncIterable<SessionEvent> {
            yield { type: 'session_started' };
            yield { type: 'session_ended' };
          },
          sayText: async () => true,
          close: async () => true,
        };
      },
      getProfiles: async () => [profile],
    };

    await expect(
      subscribeToProfile(profile, api, noReplyLlm, async (delayMs) => {
        delays.push(delayMs);
        if (delays.length === 2) {
          throw stop;
        }
      }),
    ).rejects.toBe(stop);

    expect(sessionCount).toBe(2);
    expect(delays).toEqual([1_000, 1_000]);
  });

  it('aborts active LLM generation when the SSE connection ends', async () => {
    const stop = new Error('Stop test');
    let generationAborted = false;
    const api = {
      createSession: () => ({
        async *subscribe(): AsyncIterable<SessionEvent> {
          yield { type: 'session_started' };
          yield {
            type: 'transcription_ready',
            profileId: 'alexa',
            text: 'Hello',
          };
          await Promise.resolve();
        },
        sayText: async () => true,
        close: async () => true,
      }),
      getProfiles: async () => [profile],
    };
    const llm = {
      async *streamReply(
        _text: string,
        options: { abort?: AbortSignal } = {},
      ): AsyncIterable<string | null> {
        await new Promise<void>((resolve) => {
          options.abort?.addEventListener(
            'abort',
            () => {
              generationAborted = true;
              resolve();
            },
            { once: true },
          );
        });
      },
    };

    await expect(
      subscribeToProfile(profile, api, llm, async () => {
        throw stop;
      }),
    ).rejects.toBe(stop);

    expect(generationAborted).toBe(true);
  });
});
