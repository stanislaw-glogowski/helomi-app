import type { OpenAIProviderSettings } from '@ai-sdk/openai';
import { createOpenAI } from '@ai-sdk/openai';
import type { LanguageModel, ModelMessage, SystemModelMessage } from 'ai';
import { streamText } from 'ai';
import { cleanLine, ollamaFetch } from './helpers';

/**
 * LLM Provider interfacing with OpenAI-compatible APIs (including Ollama, vLLM, etc.).
 * Streams generated text sentence-by-sentence formatted for real-time TTS synthesis.
 */
export class LlmProvider {
  private readonly model: LanguageModel;

  constructor(options: {
    modelId: string;
    baseURL?: string;
    apiKey?: string;
  }) {
    const { modelId, baseURL, apiKey } = options;

    const openai = createOpenAI({
      baseURL,
      apiKey,
      fetch: baseURL
        ? (ollamaFetch as unknown as OpenAIProviderSettings['fetch'])
        : undefined,
    });

    this.model = openai(modelId);
  }

  /**
   * Generates a streaming assistant reply to user input, splitting and cleaning line-by-line.
   * Yields clean sentence lines suitable for immediate TTS utterance dispatch.
   */
  async *streamReply(
    text: string,
    options: {
      system?: SystemModelMessage;
      messages?: ModelMessage[];
      abort?: AbortSignal;
    } = {},
  ): AsyncIterable<string> {
    const { system, messages = [], abort } = options;

    const { stream } = streamText({
      model: this.model,
      system,
      messages: [
        ...messages,
        {
          role: 'user',
          content: text,
        },
      ],
      abortSignal: abort,
    });

    let buffer = '';

    for await (const part of stream) {
      switch (part.type) {
        case 'text-delta': {
          buffer += part.text;
          let newlineIndex: number;

          while (true) {
            newlineIndex = buffer.indexOf('\n');
            if (newlineIndex === -1) {
              break;
            }

            let line = buffer.slice(0, newlineIndex);
            if (line.endsWith('\r')) {
              line = line.slice(0, -1);
            }
            buffer = buffer.slice(newlineIndex + 1);
            line = cleanLine(line);
            if (line) {
              yield line;
            }
          }

          break;
        }
      }
    }
    if (buffer.length > 0) {
      const line = cleanLine(buffer.endsWith('\r') ? buffer.slice(0, -1) : buffer);

      if (line) {
        yield line;
      }
    }
  }
}
