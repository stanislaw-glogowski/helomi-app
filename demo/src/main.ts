import * as process from 'node:process';
import type { CommandOptions, Profile, SessionEvent } from './api';
import { HelomiClient } from './api';
import { LlmProvider, MessageManager } from './conversation';
import type { Sleep } from './retry';
import { RetryBackoff, sleep } from './retry';
import type { Color } from './ui';
import { print, printBanner } from './ui';

// Configuration read from environment variables or defaults
const {
  API_BASE_URL = 'http://127.0.0.1:4356',
  LLM_BASE_URL = undefined,
  LLM_API_KEY = undefined,
  LLM_MODEL_ID = 'gpt-5.6-luna',
} = process.env;

type DemoSession = {
  subscribe(): AsyncIterable<SessionEvent>;
  sayText(text: string, options?: CommandOptions): Promise<boolean>;
  close(options?: CommandOptions): Promise<boolean>;
};

type DemoApi = {
  createSession(profileId: string): DemoSession;
  getProfiles(requirePrompt: string): Promise<Profile<string>[]>;
};

type DemoLlm = Pick<LlmProvider, 'streamReply'>;

type ProfileLogger = (...parts: Array<string | [string, ...Color[]]>) => void;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function retryDelaySeconds(delayMs: number): number {
  return delayMs / 1_000;
}

/**
 * Subscribes to SSE stream for a voice profile, handles speech recognition events,
 * triggers streaming LLM replies, and supports barge-in interruption.
 */
async function runProfileSession(
  profile: Profile<string>,
  api: DemoApi,
  llm: DemoLlm,
  messages: MessageManager,
  log: ProfileLogger,
  onConnected: () => void,
): Promise<void> {
  const session = api.createSession(profile.id);

  // Controller used to abort ongoing LLM generation when the user interrupts
  let abortController = new AbortController();

  try {
    for await (const event of session.subscribe()) {
      switch (event.type) {
        case 'session_started':
          onConnected();
          log(['● HelomiSession connected', 'green'], ' (listening for speech)');
          break;

        case 'session_ended':
          log(['○ HelomiSession ended', 'gray']);
          break;

        case 'profile_activated':
          log(['⚡ Profile activated', 'magenta']);
          break;

        case 'speech_interrupted':
          // User spoke while TTS was playing: cancel LLM generation
          abortController.abort();
          abortController = new AbortController();
          log(['⏹ Interrupted', 'yellow'], ' (user spoke, cancelled ongoing speech)');
          break;

        case 'transcription_ready': {
          const { text } = event;
          log(['🗣 User:', 'bold', 'blue'], ` "${text}"`);

          // Record user message in conversation history
          messages.append({
            role: 'user',
            content: text,
          });

          // Generate and stream assistant reply sentence-by-sentence to TTS
          void (async () => {
            const lines: string[] = [];

            try {
              const reply = llm.streamReply(text, {
                system: messages.system,
                messages: messages.history,
                abort: abortController.signal,
              });

              for await (const line of reply) {
                if (!line) {
                  await session.close();
                  return;
                }

                log(
                  [`🔊 Assistant [#${lines.length + 1}]:`, 'bold', 'green'],
                  ` "${line}"`,
                );

                lines.push(line);
                await session.sayText(line);
              }
            } catch (error) {
              if (error instanceof Error && error.name === 'AbortError') {
                return;
              }

              log(['[ERROR]', 'red'], ` ${errorMessage(error)}`);
              return;
            }

            // Record assistant response in conversation history
            if (lines.length > 0) {
              messages.append({
                role: 'assistant',
                content: lines.join('\n'),
              });
            }
          })();
          break;
        }
      }
    }
  } finally {
    abortController.abort();
  }
}

/** Keeps one profile subscribed across transport failures and server restarts. */
export async function subscribeToProfile(
  profile: Profile<string>,
  api: DemoApi,
  llm: DemoLlm,
  wait: Sleep = sleep,
): Promise<never> {
  const messages = new MessageManager({
    system: {
      role: 'system',
      content: profile.prompt,
    },
  });
  const backoff = new RetryBackoff();
  const log: ProfileLogger = (...parts) => {
    print([`[${profile.id}]`, 'cyan'], ' ', ...parts);
  };

  while (true) {
    let disconnectReason = 'SSE stream ended';
    try {
      await runProfileSession(profile, api, llm, messages, log, () => {
        backoff.reset();
      });
    } catch (error) {
      disconnectReason = errorMessage(error);
    }

    const delayMs = backoff.next();
    log(
      ['○ HelomiSession disconnected', 'yellow'],
      ` (${disconnectReason}); reconnecting in ${retryDelaySeconds(delayMs)}s`,
    );
    await wait(delayMs);
  }
}

/** Waits indefinitely for the API to become available during demo startup. */
export async function getProfilesWithRetry(
  api: DemoApi,
  wait: Sleep = sleep,
): Promise<Profile<string>[]> {
  const backoff = new RetryBackoff();

  while (true) {
    try {
      return await api.getProfiles('demo');
    } catch (error) {
      const delayMs = backoff.next();
      print(
        ['[WARN]', 'yellow'],
        ` Helomi API unavailable (${errorMessage(error)}); retrying in ${retryDelaySeconds(delayMs)}s`,
      );
      await wait(delayMs);
    }
  }
}

/**
 * Main application entrypoint.
 * Connects to Helomi API, discovers profiles, loads prompts, and subscribes to SSE streams.
 */
export async function main(): Promise<void> {
  const api = new HelomiClient({
    baseUrl: API_BASE_URL,
  });
  const llm = new LlmProvider({
    baseUrl: LLM_BASE_URL,
    apiKey: LLM_API_KEY,
    modelId: LLM_MODEL_ID,
  });

  // Fetch available profiles from Helomi server
  const profiles = await getProfilesWithRetry(api);
  printBanner({
    apiUrl: API_BASE_URL,
    llmModel: LLM_MODEL_ID,
    llmBaseUrl: LLM_BASE_URL,
    profiles,
  });

  const promises: Promise<void>[] = [];

  for (const profile of profiles) {
    promises.push(subscribeToProfile(profile, api, llm));
  }

  if (promises.length === 0) {
    print();
    print(['[WARN]', 'yellow'], ' No active profiles found with matching prompt files.');
    print(['Create resources/profiles/alexa/prompts/demo.md.\n', 'dim']);
    return;
  }

  await Promise.all(promises);
}

if (import.meta.main) {
  try {
    await main();
  } catch (error) {
    print();
    print(['[ERROR]', 'bold', 'red'], ` ${errorMessage(error)}\n`);
  }
}
