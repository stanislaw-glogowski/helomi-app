import * as process from 'node:process';
import type { Profile } from './api';
import { Client, ClientError } from './api';
import { LlmProvider, MessageManager } from './conversation';
import type { Color } from './ui';
import { print, printBanner } from './ui';

// Configuration read from environment variables or defaults
const {
  API_BASE_URL = 'http://127.0.0.1:4356',
  LLM_BASE_URL = undefined,
  LLM_API_KEY = undefined,
  LLM_MODEL_ID = 'gpt-5.6-luna',
} = process.env;

/**
 * Subscribes to SSE stream for a voice profile, handles speech recognition events,
 * triggers streaming LLM replies, and supports barge-in interruption.
 */
async function subscribeToProfile(
  profile: Profile<string>,
  api: Client,
  llm: LlmProvider,
): Promise<void> {
  const session = api.createSession(profile.id);
  const messages = new MessageManager({
    system: {
      role: 'system',
      content: profile.prompt,
    },
  });

  // Controller used to abort ongoing LLM generation when the user interrupts
  let abortController = new AbortController();

  const log = (...parts: Array<string | [string, ...Color[]]>) => {
    print([`[${profile.id}]`, 'cyan'], ' ', ...parts);
  };

  for await (const event of session.subscribe()) {
    switch (event.type) {
      case 'session_started':
        log(['● Session connected', 'green'], ' (listening for speech)');
        break;

      case 'session_ended':
        log(['○ Session ended', 'gray']);
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
        (async () => {
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
          } catch (err) {
            // Silently ignore aborted requests on interruption
            if (err instanceof Error && err.name === 'AbortError') {
              return;
            }
          }

          // Record assistant response in conversation history
          if (lines.length > 0) {
            messages.append({
              role: 'assistant',
              content: lines.join('\n'),
            });
          }
        })().catch((err) => {
          if (err instanceof Error && err.name === 'AbortError') {
            return;
          }
          print(
            ['[ERROR]', 'red'],
            ` ${err instanceof Error ? err.message : String(err)}`,
          );
        });
        break;
      }
    }
  }
}

/**
 * Main application entrypoint.
 * Connects to Helomi API, discovers profiles, loads prompts, and subscribes to SSE streams.
 */
async function main(): Promise<void> {
  const api = new Client({
    baseURL: API_BASE_URL,
  });
  const llm = new LlmProvider({
    baseURL: LLM_BASE_URL,
    apiKey: LLM_API_KEY,
    modelId: LLM_MODEL_ID,
  });

  // Fetch available profiles from Helomi server
  const profiles = await api.getProfiles('demo');
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
    print([
      'Create a prompt file under prompts/profiles/<profile_id>.md (e.g. prompts/profiles/alexa.md).\n',
      'dim',
    ]);
    return;
  }

  await Promise.all(promises);
}

try {
  await main();
} catch (err) {
  if (err instanceof ClientError || (err instanceof Error && 'cause' in err)) {
    print();
    print(
      ['[ERROR]', 'bold', 'red'],
      ` Could not connect to Helomi server at ${API_BASE_URL}.`,
    );
    print(['Ensure the Helomi server is running\n', 'dim']);
  } else {
    print();
    print(
      ['[ERROR]', 'bold', 'red'],
      ` ${err instanceof Error ? err.message : String(err)}\n`,
    );
  }
}
