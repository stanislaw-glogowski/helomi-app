import * as process from 'node:process';
import type { SystemModelMessage } from 'ai';
import type { Profile } from './api';
import { Client, ClientError } from './api';
import { MessageManager, PromptLoader } from './conversation';
import { LlmProvider } from './llm';
import { ANSI_STYLES, printBanner } from './ui';

// Configuration read from environment variables or defaults
const {
  API_BASE_URL = 'http://127.0.0.1:4356',
  LLM_BASE_URL = undefined,
  LLM_API_KEY = undefined,
  LLM_MODEL_ID = 'gpt-5.6-luna',
} = process.env;

/**
 * Wraps an async function to execute detached without unhandled promise rejection crashes.
 */
function wrapAsync(fn: () => Promise<void>): void {
  fn().catch((err) => {
    if (err instanceof Error && err.name === 'AbortError') {
      return;
    }
    console.error(
      `${ANSI_STYLES.red}[ERROR]${ANSI_STYLES.reset} ${err instanceof Error ? err.message : String(err)}`,
    );
  });
}

/**
 * Subscribes to SSE stream for a voice profile, handles speech recognition events,
 * triggers streaming LLM replies, and supports barge-in interruption.
 */
async function subscribeToProfile(
  profile: Profile,
  system: SystemModelMessage,
  api: Client,
  llm: LlmProvider,
): Promise<void> {
  const session = api.createSession(profile.id);
  const messages = new MessageManager({ system });

  // Controller used to abort ongoing LLM generation when the user interrupts
  let abortController = new AbortController();

  const log = (message: string) => {
    const badge = `${ANSI_STYLES.cyan}[${profile.id}]${ANSI_STYLES.reset}`;
    console.log(`${badge} ${message}`);
  };

  for await (const event of session.subscribe()) {
    switch (event.type) {
      case 'session_started':
        log(
          `${ANSI_STYLES.green}● Session connected${ANSI_STYLES.reset} (listening for speech)`,
        );
        break;

      case 'session_ended':
        log(`${ANSI_STYLES.gray}○ Session ended${ANSI_STYLES.reset}`);
        break;

      case 'profile_activated':
        log(`${ANSI_STYLES.magenta}⚡ Profile activated${ANSI_STYLES.reset}`);
        break;

      case 'speech_interrupted':
        // User spoke while TTS was playing: cancel LLM generation
        abortController.abort();
        abortController = new AbortController();
        log(
          `${ANSI_STYLES.yellow}⏹ Interrupted${ANSI_STYLES.reset} (user spoke, cancelled ongoing speech)`,
        );
        break;

      case 'transcription_ready': {
        const { text } = event;
        log(
          `${ANSI_STYLES.bold}${ANSI_STYLES.blue}🎙 User:${ANSI_STYLES.reset} "${text}"`,
        );

        // Record user message in conversation history
        messages.append({
          role: 'user',
          content: text,
        });

        // Generate and stream assistant reply sentence-by-sentence to TTS
        wrapAsync(async () => {
          const lines: string[] = [];

          try {
            const reply = llm.streamReply(text, {
              system: messages.system,
              messages: messages.history,
              abort: abortController.signal,
            });

            for await (const line of reply) {
              log(
                `${ANSI_STYLES.bold}${ANSI_STYLES.green}🔊 Assistant [#${lines.length + 1}]:${ANSI_STYLES.reset} "${line}"`,
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
  const prompts = new PromptLoader();

  // Fetch available profiles from Helomi server
  const profiles = await api.getProfiles();
  printBanner({
    apiUrl: API_BASE_URL,
    llmModel: LLM_MODEL_ID,
    llmBaseUrl: LLM_BASE_URL,
    profiles,
  });

  const promises: Promise<void>[] = [];

  for (const profile of profiles) {
    const system = await prompts.loadSystemMessage(profile.id);
    if (!system) {
      console.log(
        `${ANSI_STYLES.yellow}ℹ [INFO]${ANSI_STYLES.reset} Skipping profile '${profile.id}': no prompt found in prompts/profiles/${profile.id}.md`,
      );
      continue;
    }

    promises.push(subscribeToProfile(profile, system, api, llm));
  }

  if (promises.length === 0) {
    console.warn(
      `\n${ANSI_STYLES.yellow}[WARN]${ANSI_STYLES.reset} No active profiles found with matching prompt files.`,
    );
    console.warn(
      `${ANSI_STYLES.dim}Create a prompt file under prompts/profiles/<profile_id>.md (e.g. prompts/profiles/default.md).${ANSI_STYLES.reset}\n`,
    );
    return;
  }

  await Promise.all(promises);
}

try {
  await main();
} catch (err) {
  if (err instanceof ClientError || (err instanceof Error && 'cause' in err)) {
    console.error(
      `\n${ANSI_STYLES.red}${ANSI_STYLES.bold}[ERROR]${ANSI_STYLES.reset} Could not connect to Helomi server at ${API_BASE_URL}.`,
    );
    console.error(
      `${ANSI_STYLES.dim}Ensure the Helomi server is running via:${ANSI_STYLES.reset} ${ANSI_STYLES.yellow}uv run helomi-cli serve${ANSI_STYLES.reset}\n`,
    );
  } else {
    console.error(
      `\n${ANSI_STYLES.red}${ANSI_STYLES.bold}[ERROR]${ANSI_STYLES.reset} ${err instanceof Error ? err.message : String(err)}\n`,
    );
  }
}
