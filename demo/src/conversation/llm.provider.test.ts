import { describe, expect, it } from 'bun:test';
import { MockLanguageModelV4 } from 'ai/test';
import {
  END_CONVERSATION_TOOL_NAME,
  endConversationTool,
  LlmProvider,
} from './llm.provider';

describe('LlmProvider', () => {
  it('initializes with custom model or default options', () => {
    const mockModel = new MockLanguageModelV4({
      modelId: 'test-model',
    });

    const providerWithMock = new LlmProvider({
      model: mockModel,
    });
    expect(providerWithMock).toBeDefined();

    const providerWithOpenAI = new LlmProvider({
      modelId: 'custom-model',
      baseURL: 'http://localhost:11434/v1',
      apiKey: 'test-key',
    });
    expect(providerWithOpenAI).toBeDefined();

    const providerDefault = new LlmProvider({});
    expect(providerDefault).toBeDefined();
  });

  const makeFinish = (unified: 'stop' | 'tool-calls' = 'stop') => ({
    type: 'finish' as const,
    finishReason: { unified, raw: unified },
    usage: {
      inputTokens: {
        total: 10,
        noCache: undefined,
        cacheRead: undefined,
        cacheWrite: undefined,
      },
      outputTokens: {
        total: 5,
        text: undefined,
        reasoning: undefined,
      },
    },
  });

  it('endConversationTool executes and returns null', async () => {
    expect(endConversationTool.description).toContain('end the conversation');
    if (endConversationTool.execute) {
      const result = await endConversationTool.execute(
        { reason: 'goodbye' },
        { messages: [], toolCallId: 'test-call', context: {} },
      );
      expect(result).toBeNull();
    }
  });

  it('streams text sentence by sentence across chunks', async () => {
    const mockModel = new MockLanguageModelV4({
      doStream: async () => ({
        stream: new ReadableStream({
          start(controller) {
            controller.enqueue({
              type: 'response-metadata',
              id: '1',
              modelId: 'test',
              timestamp: new Date(),
            });
            controller.enqueue({ type: 'text-start', id: '0' });
            controller.enqueue({
              type: 'text-delta',
              id: '0',
              delta: 'Hello there!\nHow can I ',
            });
            controller.enqueue({
              type: 'text-delta',
              id: '0',
              delta: 'help you today?\r\nHave a great day.',
            });
            controller.enqueue({ type: 'text-end', id: '0' });
            controller.enqueue(makeFinish('stop'));
            controller.close();
          },
        }),
      }),
    });

    const provider = new LlmProvider({ model: mockModel });
    const lines: (string | null)[] = [];

    for await (const line of provider.streamReply('Hello!')) {
      lines.push(line);
    }

    expect(lines).toEqual([
      'Hello there!',
      'How can I help you today?',
      'Have a great day.',
    ]);
  });

  it('cleans lines during streaming', async () => {
    const mockModel = new MockLanguageModelV4({
      doStream: async () => ({
        stream: new ReadableStream({
          start(controller) {
            controller.enqueue({
              type: 'response-metadata',
              id: '1',
              modelId: 'test',
              timestamp: new Date(),
            });
            controller.enqueue({ type: 'text-start', id: '0' });
            controller.enqueue({
              type: 'text-delta',
              id: '0',
              delta: '<think>Greeting</think>**Hello** *friend*!\n',
            });
            controller.enqueue({ type: 'text-end', id: '0' });
            controller.enqueue(makeFinish('stop'));
            controller.close();
          },
        }),
      }),
    });

    const provider = new LlmProvider({ model: mockModel });
    const lines: (string | null)[] = [];

    for await (const line of provider.streamReply('Hi')) {
      lines.push(line);
    }

    expect(lines).toEqual(['Hello friend!']);
  });

  it('yields null when endConversation tool is called directly', async () => {
    const mockModel = new MockLanguageModelV4({
      doStream: async () => ({
        stream: new ReadableStream({
          start(controller) {
            controller.enqueue({
              type: 'response-metadata',
              id: '1',
              modelId: 'test',
              timestamp: new Date(),
            });
            controller.enqueue({
              type: 'tool-call',
              toolCallId: 'call-end-1',
              toolName: END_CONVERSATION_TOOL_NAME,
              input: JSON.stringify({ reason: 'user goodbye' }),
            });
            controller.enqueue(makeFinish('tool-calls'));
            controller.close();
          },
        }),
      }),
    });

    const provider = new LlmProvider({ model: mockModel });
    const lines: (string | null)[] = [];

    for await (const line of provider.streamReply('Goodbye')) {
      lines.push(line);
    }

    expect(lines).toEqual([null]);
  });

  it('yields pending buffer before yielding null when endConversation is called after text', async () => {
    const mockModel = new MockLanguageModelV4({
      doStream: async () => ({
        stream: new ReadableStream({
          start(controller) {
            controller.enqueue({
              type: 'response-metadata',
              id: '1',
              modelId: 'test',
              timestamp: new Date(),
            });
            controller.enqueue({ type: 'text-start', id: '0' });
            controller.enqueue({
              type: 'text-delta',
              id: '0',
              delta: 'Goodbye, take care!',
            });
            controller.enqueue({ type: 'text-end', id: '0' });
            controller.enqueue({
              type: 'tool-call',
              toolCallId: 'call-end-2',
              toolName: END_CONVERSATION_TOOL_NAME,
              input: '{}',
            });
            controller.enqueue(makeFinish('tool-calls'));
            controller.close();
          },
        }),
      }),
    });

    const provider = new LlmProvider({ model: mockModel });
    const lines: (string | null)[] = [];

    for await (const line of provider.streamReply('Bye bye')) {
      lines.push(line);
    }

    expect(lines).toEqual(['Goodbye, take care!', null]);
  });

  it('ignores other unknown tool calls and finishes streaming', async () => {
    const mockModel = new MockLanguageModelV4({
      doStream: async () => ({
        stream: new ReadableStream({
          start(controller) {
            controller.enqueue({
              type: 'response-metadata',
              id: '1',
              modelId: 'test',
              timestamp: new Date(),
            });
            controller.enqueue({
              type: 'tool-call',
              toolCallId: 'call-other',
              toolName: 'unknownTool',
              input: '{}',
            });
            controller.enqueue({ type: 'text-start', id: '0' });
            controller.enqueue({
              type: 'text-delta',
              id: '0',
              delta: 'Still talking.\n',
            });
            controller.enqueue({ type: 'text-end', id: '0' });
            controller.enqueue(makeFinish('stop'));
            controller.close();
          },
        }),
      }),
    });

    const provider = new LlmProvider({ model: mockModel });
    const lines: (string | null)[] = [];

    for await (const line of provider.streamReply('Hello')) {
      lines.push(line);
    }

    expect(lines).toEqual(['Still talking.']);
  });
});
