import { describe, expect, it } from 'bun:test';
import { cleanLine, ollamaFetch } from './helpers';

describe('cleanLine', () => {
  it('removes reasoning think blocks', () => {
    const input = '<think>I should greet the user warmly.</think>Hello there!';
    expect(cleanLine(input)).toBe('Hello there!');
  });

  it('removes multiline think blocks', () => {
    const input = '<think>\nStep 1: Check time.\nStep 2: Answer.\n</think>Good morning!';
    expect(cleanLine(input)).toBe('Good morning!');
  });

  it('removes markdown code blocks', () => {
    const input = 'Here is the answer: ```const x = 1;``` Done.';
    expect(cleanLine(input)).toBe('Here is the answer: Done.');
  });

  it('strips markdown formatting characters', () => {
    const input = '*bold* _italic_ # header `code` ~strikethrough~ > quote';
    expect(cleanLine(input)).toBe('bold italic header code strikethrough quote');
  });

  it('converts markdown links to plain text', () => {
    const input =
      'Visit [Helomi App](https://github.com/stanislaw-glogowski/helomi-app) today!';
    expect(cleanLine(input)).toBe('Visit Helomi App today!');
  });

  it('collapses multiple whitespace and trims', () => {
    const input = '   Too    many    spaces.   ';
    expect(cleanLine(input)).toBe('Too many spaces.');
  });

  it('preserves allowed vocal delivery tags in square brackets', () => {
    const input = 'Hello, friend! [laughter] How have you been? [breath]';
    expect(cleanLine(input)).toBe(
      'Hello, friend! [laughter] How have you been? [breath]',
    );
  });
});

describe('ollamaFetch', () => {
  it('sets think: false on JSON string bodies', async () => {
    const originalFetch = globalThis.fetch;
    let interceptedInit: RequestInit | undefined;
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      interceptedInit = init;
      return new Response('ok');
    }) as unknown as typeof fetch;

    try {
      const res = await ollamaFetch('http://localhost:11434/api/chat', {
        method: 'POST',
        body: JSON.stringify({ model: 'llama', stream: true }),
      });

      expect(res.status).toBe(200);
      expect(interceptedInit?.body).toBeDefined();
      const parsed = JSON.parse(interceptedInit?.body as string);
      expect(parsed.think).toBe(false);
      expect(parsed.model).toBe('llama');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('falls back to original fetch on non-JSON body', async () => {
    const originalFetch = globalThis.fetch;
    let interceptedInit: RequestInit | undefined;
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      interceptedInit = init;
      return new Response('ok');
    }) as unknown as typeof fetch;

    try {
      await ollamaFetch('http://localhost:11434/api/chat', {
        method: 'POST',
        body: 'invalid-json',
      });

      expect(interceptedInit?.body).toBe('invalid-json');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('calls fetch as-is when init or body is not provided', async () => {
    const originalFetch = globalThis.fetch;
    let calledUrl: string | undefined;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      calledUrl = String(input);
      return new Response('ok');
    }) as unknown as typeof fetch;

    try {
      await ollamaFetch('http://localhost:11434/api/tags');
      expect(calledUrl).toBe('http://localhost:11434/api/tags');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
