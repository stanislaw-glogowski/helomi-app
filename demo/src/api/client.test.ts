import { describe, expect, it } from 'bun:test';
import { HelomiClient } from './client';
import { ClientError } from './client.error';
import { HelomiSession } from './session';

describe('HelomiClient', () => {
  it('initializes with baseUrl and creates session', () => {
    const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
    const session = client.createSession('alexa');

    expect(session).toBeInstanceOf(HelomiSession);
  });

  it('sends getProfile request and returns profile', async () => {
    const originalFetch = globalThis.fetch;
    let requestedUrl: string | undefined;

    globalThis.fetch = (async (input: RequestInfo | URL) => {
      requestedUrl = String(input);
      return new Response(
        JSON.stringify({
          id: 'alexa',
          name: 'Alexa',
          is_active: true,
          has_wakeword: true,
          is_readonly: false,
          prompt: 'system prompt',
          emoji: '🤖',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }) as unknown as typeof fetch;

    try {
      const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
      const profile = await client.getProfile('alexa', 'demo');

      expect(profile).toEqual({
        id: 'alexa',
        name: 'Alexa',
        isActive: true,
        hasWakeword: true,
        isReadonly: false,
        prompt: 'system prompt',
        emoji: '🤖',
      });
      expect(requestedUrl).toBe(
        'http://127.0.0.1:4356/api/v1/profile/alexa?require_prompt=demo',
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('returns null on getProfile 404 response', async () => {
    const originalFetch = globalThis.fetch;

    globalThis.fetch = (async () => {
      return new Response(JSON.stringify({ detail: 'Profile not found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as unknown as typeof fetch;

    try {
      const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
      const profile = await client.getProfile('unknown');
      expect(profile).toBeNull();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('rethrows non-404 errors in getProfile', async () => {
    const originalFetch = globalThis.fetch;

    globalThis.fetch = (async () => {
      return new Response(JSON.stringify({ detail: 'Internal Server Error' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as unknown as typeof fetch;

    try {
      const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
      await expect(client.getProfile('alexa')).rejects.toThrow(ClientError);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('fetches profiles list via getProfiles', async () => {
    const originalFetch = globalThis.fetch;
    let requestedUrl: string | undefined;

    globalThis.fetch = (async (input: RequestInfo | URL) => {
      requestedUrl = String(input);
      return new Response(
        JSON.stringify([
          {
            id: 'alexa',
            name: 'Alexa',
            is_active: true,
            has_wakeword: true,
            is_readonly: false,
            prompt: null,
            emoji: '🤖',
          },
        ]),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }) as unknown as typeof fetch;

    try {
      const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
      const profiles = await client.getProfiles();

      expect(profiles).toHaveLength(1);
      expect(requestedUrl).toBe('http://127.0.0.1:4356/api/v1/profile');

      await client.getProfiles('demo', { abort: new AbortController().signal });
      expect(requestedUrl).toBe(
        'http://127.0.0.1:4356/api/v1/profile?require_prompt=demo',
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('handles query parameters and command options in fetch', async () => {
    const originalFetch = globalThis.fetch;
    let interceptedUrl: string | undefined;
    let interceptedInit: RequestInit | undefined;

    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      interceptedUrl = String(input);
      interceptedInit = init;
      return new Response(JSON.stringify({ accepted: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as unknown as typeof fetch;

    try {
      const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
      const res = await client.fetch('/command', {
        headers: { 'X-Custom': 'val' },
        traceId: 'trace-123',
        timeout: 1_500,
        query: {
          testParam: 'hello',
          emptyParam: undefined,
        },
        command: {
          type: 'say_text',
          text: 'Hello world',
          mode: 'api',
        },
      });

      expect(res.ok).toBe(true);
      expect(interceptedUrl).toBe(
        'http://127.0.0.1:4356/api/v1/command?test_param=hello',
      );
      expect(interceptedInit?.method).toBe('POST');
      expect(
        (interceptedInit as RequestInit & { timeout?: number | boolean }).timeout,
      ).toBe(1_500);
      const headers = (interceptedInit?.headers ?? {}) as Record<string, string>;
      expect(headers['X-Custom']).toBe('val');
      expect(headers['Content-Type']).toBe('application/json');

      const body = JSON.parse(interceptedInit?.body as string);
      expect(body.trace_id).toBe('trace-123');
      expect(body.type).toBe('say_text');
      expect(body.text).toBe('Hello world');
      expect(body.mode).toBe('api');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('throws ClientError on network failure', async () => {
    const originalFetch = globalThis.fetch;

    globalThis.fetch = (async () => {
      throw new Error('Connection refused');
    }) as unknown as typeof fetch;

    try {
      const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
      await expect(client.fetch('/health')).rejects.toThrow('Failed to send request');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('throws ClientError with statusText when non-ok response has no json detail', async () => {
    const originalFetch = globalThis.fetch;

    globalThis.fetch = (async () => {
      return new Response('Not HTML/JSON', {
        status: 502,
        statusText: 'Bad Gateway',
      });
    }) as unknown as typeof fetch;

    try {
      const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
      const error = await client.fetch('/bad').catch((e) => e);
      expect(error).toBeInstanceOf(ClientError);
      expect(error.message).toBe('Bad Gateway');
      expect(error.status).toBe(502);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('throws ClientError when parsing invalid json in send', async () => {
    const originalFetch = globalThis.fetch;

    globalThis.fetch = (async () => {
      return new Response('not valid json {', {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as unknown as typeof fetch;

    try {
      const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
      await expect(client.send('/invalid')).rejects.toThrow('Failed to parse response');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
