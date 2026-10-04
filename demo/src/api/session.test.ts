import { describe, expect, it } from 'bun:test';
import { HelomiClient } from './client';
import { HelomiSession } from './session';
import type { SessionEvent } from './types';

describe('HelomiSession', () => {
  it('throws when sending command before session started', async () => {
    const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
    const session = new HelomiSession('alexa', client);

    await expect(session.sayText('Hello')).rejects.toThrow('HelomiSession not started');
    await expect(session.sayReaction('greeting')).rejects.toThrow(
      'HelomiSession not started',
    );
    await expect(session.close()).rejects.toThrow('HelomiSession not started');
  });

  it('subscribes to SSE stream and receives events', async () => {
    const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
    const ssePayload = [
      'event: session_started\ndata: {}\n\n',
      ': keep-alive\n\n',
      'event: transcription_ready\ndata: {"text": "Hello assistant", "profile_id": "alexa"}\n\n',
      'event: speech_interrupted\ndata: {"profile_id": "alexa"}\n\n',
      'event: invalid_block\n\n',
    ].join('');

    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(ssePayload));
        controller.close();
      },
    });

    client.fetch = (async () => {
      return new Response(stream, {
        headers: {
          [HelomiSession.HEADER_KEY]: 'test-session-123',
        },
      });
    }) as unknown as typeof client.fetch;

    const session = client.createSession('alexa');
    const events: SessionEvent[] = [];

    for await (const event of session.subscribe()) {
      events.push(event);
    }

    expect(events).toEqual([
      { type: 'session_started' },
      {
        type: 'transcription_ready',
        text: 'Hello assistant',
        profileId: 'alexa',
      } as SessionEvent,
      {
        type: 'speech_interrupted',
        profileId: 'alexa',
      } as SessionEvent,
      { type: 'session_ended' },
    ]);
    await expect(session.sayText('After disconnect')).rejects.toThrow(
      'HelomiSession not started',
    );
  });

  it('rejects malformed SSE payloads', async () => {
    const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode('event: corrupt_json\ndata: {invalid\n\n'),
        );
        controller.close();
      },
    });
    client.fetch = (async () =>
      new Response(stream, {
        headers: { [HelomiSession.HEADER_KEY]: 'test-session-123' },
      })) as unknown as typeof client.fetch;

    const session = client.createSession('alexa');
    const iterator = session.subscribe()[Symbol.asyncIterator]();
    await expect(iterator.next()).rejects.toThrow(
      'Invalid SSE payload for event corrupt_json',
    );
    await expect(session.sayText('After error')).rejects.toThrow(
      'HelomiSession not started',
    );
  });

  it('sends commands while session is active', async () => {
    const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
    let capturedPath: string | undefined;
    let capturedOptions: unknown;

    client.send = (async (path: string, options?: unknown) => {
      capturedPath = path;
      capturedOptions = options;
      return { accepted: true, rejectionCode: null, detail: null };
    }) as unknown as typeof client.send;

    const encoder = new TextEncoder();
    let streamController: ReadableStreamDefaultController | undefined;
    const stream = new ReadableStream({
      start(c) {
        streamController = c;
        c.enqueue(encoder.encode('event: session_started\ndata: {}\n\n'));
      },
    });

    client.fetch = (async () => {
      return new Response(stream, {
        headers: {
          [HelomiSession.HEADER_KEY]: 'active-session-id',
        },
      });
    }) as unknown as typeof client.fetch;

    const session = client.createSession('alexa');
    const iterator = session.subscribe()[Symbol.asyncIterator]();
    const firstEvent = await iterator.next();
    expect(firstEvent.value).toEqual({ type: 'session_started' });

    const sayRes = await session.sayText('Test message');
    expect(sayRes).toBe(true);
    expect(capturedPath).toBe('/command');
    expect((capturedOptions as { headers: Record<string, string> }).headers).toEqual({
      [HelomiSession.HEADER_KEY]: 'active-session-id',
    });
    expect((capturedOptions as { command: unknown }).command).toEqual({
      type: 'say_text',
      text: 'Test message',
      mode: 'api',
    });

    const reactionRes = await session.sayReaction('interrupted');
    expect(reactionRes).toBe(true);
    expect((capturedOptions as { command: unknown }).command).toEqual({
      type: 'say_reaction',
      reaction: 'interrupted',
      mode: 'api',
    });

    const closeRes = await session.close();
    expect(closeRes).toBe(true);
    expect((capturedOptions as { command: unknown }).command).toEqual({
      type: 'end_conversation',
      playFarewell: true,
    });

    // Clean up iterator
    streamController?.close();
    await iterator.next();
  });

  it('disables the Bun idle timeout for the SSE request', async () => {
    const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
    let timeout: number | boolean | undefined;

    client.fetch = (async (_path: string, options = {}) => {
      timeout = options.timeout;
      return new Response('event: session_started\ndata: {}\n\n', {
        headers: {
          [HelomiSession.HEADER_KEY]: 'session-without-timeout',
        },
      });
    }) as typeof client.fetch;

    const events: SessionEvent[] = [];
    for await (const event of client.createSession('alexa').subscribe()) {
      events.push(event);
    }

    expect(timeout).toBe(false);
    expect(events).toEqual([{ type: 'session_started' }, { type: 'session_ended' }]);
  });

  it('clears the session when reading the SSE stream fails', async () => {
    const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode('event: session_started\ndata: {}\n\n'),
        );
        controller.error(new Error('Connection reset'));
      },
    });

    client.fetch = (async () =>
      new Response(stream, {
        headers: { [HelomiSession.HEADER_KEY]: 'failed-session' },
      })) as unknown as typeof client.fetch;

    const session = client.createSession('alexa');
    const iterator = session.subscribe()[Symbol.asyncIterator]();
    await expect(iterator.next()).rejects.toThrow('Connection reset');
    await expect(session.sayText('After reset')).rejects.toThrow(
      'HelomiSession not started',
    );
  });

  it('throws if trying to subscribe when session already started', async () => {
    const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
    const encoder = new TextEncoder();
    let streamController: ReadableStreamDefaultController | undefined;
    const stream = new ReadableStream({
      start(c) {
        streamController = c;
        c.enqueue(encoder.encode('event: session_started\ndata: {}\n\n'));
      },
    });

    client.fetch = (async () => {
      return new Response(stream, {
        headers: {
          [HelomiSession.HEADER_KEY]: 'session-456',
        },
      });
    }) as unknown as typeof client.fetch;

    const session = client.createSession('alexa');
    const iter = session.subscribe()[Symbol.asyncIterator]();
    await iter.next();

    await expect(session.subscribe()[Symbol.asyncIterator]().next()).rejects.toThrow(
      'HelomiSession already started',
    );

    streamController?.close();
    await iter.next();
  });

  it('throws ClientError if session header is missing in response', async () => {
    const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
    client.fetch = (async () => {
      return new Response('ok', {
        headers: {},
      });
    }) as unknown as typeof client.fetch;

    const session = client.createSession('alexa');
    await expect(session.subscribe()[Symbol.asyncIterator]().next()).rejects.toThrow(
      'HelomiSession ID not found in response headers',
    );
  });

  it('throws ClientError if response body is missing', async () => {
    const client = new HelomiClient({ baseUrl: 'http://127.0.0.1:4356' });
    client.fetch = (async () => {
      const resp = new Response(null, {
        headers: {
          [HelomiSession.HEADER_KEY]: 'sess-789',
        },
      });
      Object.defineProperty(resp, 'body', { value: null });
      return resp;
    }) as unknown as typeof client.fetch;

    const session = client.createSession('alexa');
    await expect(session.subscribe()[Symbol.asyncIterator]().next()).rejects.toThrow(
      'No response body',
    );
  });
});
