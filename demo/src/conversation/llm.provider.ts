import type { OpenAIProviderSettings } from '@ai-sdk/openai';
import { createOpenAI } from '@ai-sdk/openai';
import type { LanguageModel, ModelMessage, SystemModelMessage } from 'ai';
import { jsonSchema, streamText, tool } from 'ai';
import { cleanLine, ollamaFetch } from './helpers';

export const END_CONVERSATION_TOOL_NAME = 'endConversation';

export const endConversationTool = tool({
  description:
    'Call this tool when the user wants to end the conversation, stop talking, finish the interaction, or says goodbye.',
  inputSchema: jsonSchema({
    type: 'object',
    properties: {
      reason: {
        type: 'string',
        description: 'Optional reason why the conversation is ending.',
      },
    },
  }),
  execute: async () => null,
});

/**
 * LLM Provider interfacing with OpenAI-compatible APIs (including Ollama, vLLM, etc.).
 * Streams generated text sentence-by-sentence formatted for real-time TTS synthesis.
 */
export class LlmProvider {
  private readonly model: LanguageModel;

  constructor(options: {
    modelId?: string;
    baseURL?: string;
    apiKey?: string;
    model?: LanguageModel;
  }) {
    const { modelId = 'gpt-5.6-luna', baseURL, apiKey, model } = options;

    if (model) {
      this.model = model;
      return;
    }

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
   * When the user wants to end the conversation, the endConversation tool is triggered and null is yielded.
   */
  async *streamReply(
    text: string,
    options: {
      system?: SystemModelMessage;
      messages?: ModelMessage[];
      abort?: AbortSignal;
    } = {},
  ): AsyncIterable<string | null> {
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
      tools: {
        [END_CONVERSATION_TOOL_NAME]: endConversationTool,
      },
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

        case 'tool-call': {
          if (part.toolName === END_CONVERSATION_TOOL_NAME) {
            if (buffer.length > 0) {
              const line = cleanLine(
                buffer.endsWith('\r') ? buffer.slice(0, -1) : buffer,
              );
              buffer = '';
              if (line) {
                yield line;
              }
            }
            yield null;
            return;
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
