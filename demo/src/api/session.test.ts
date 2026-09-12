import { describe, expect, it } from 'bun:test';
import { Client } from './client';
import { Session } from './session';
import type { SessionEvent } from './types';

describe('Session', () => {
  it('throws when sending command before session started', async () => {
    const client = new Client({ baseURL: 'http://127.0.0.1:4356' });
    const session = new Session('alexa', client);

    await expect(session.sayText('Hello')).rejects.toThrow('Session not started');
    await expect(session.sayReaction('greeting')).rejects.toThrow('Session not started');
    await expect(session.close()).rejects.toThrow('Session not started');
  });

  it('subscribes to SSE stream and receives events', async () => {
    const client = new Client({ baseURL: 'http://127.0.0.1:4356' });
    const ssePayload = [
      'event: session_started\ndata: {}\n\n',
      'event: transcription_ready\ndata: {"text": "Hello assistant", "profile_id": "alexa"}\n\n',
      'event: speech_interrupted\ndata: {"profile_id": "alexa"}\n\n',
      'event: invalid_block\n\n',
      'event: corrupt_json\ndata: {invalid\n\n',
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
          [Session.HEADER_KEY]: 'test-session-123',
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
  });

  it('sends commands while session is active', async () => {
    const client = new Client({ baseURL: 'http://127.0.0.1:4356' });
    let capturedPath: string | undefined;
    let capturedOptions: unknown;

    client.send = (async (path: string, options?: unknown) => {
      capturedPath = path;
      capturedOptions = options;
      return { success: true };
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
          [Session.HEADER_KEY]: 'active-session-id',
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
      [Session.HEADER_KEY]: 'active-session-id',
    });
    expect((capturedOptions as { command: unknown }).command).toEqual({
      type: 'say_text',
      text: 'Test message',
      profileId: 'alexa',
    });

    const reactionRes = await session.sayReaction('interrupted');
    expect(reactionRes).toBe(true);
    expect((capturedOptions as { command: unknown }).command).toEqual({
      type: 'say_reaction',
      reaction: 'interrupted',
      profileId: 'alexa',
    });

    const closeRes = await session.close();
    expect(closeRes).toBe(true);
    expect((capturedOptions as { command: unknown }).command).toEqual({
      type: 'deactivate_profile',
    });

    // Clean up iterator
    streamController?.close();
    await iterator.next();
  });

  it('throws if trying to subscribe when session already started', async () => {
    const client = new Client({ baseURL: 'http://127.0.0.1:4356' });
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
          [Session.HEADER_KEY]: 'session-456',
        },
      });
    }) as unknown as typeof client.fetch;

    const session = client.createSession('alexa');
    const iter = session.subscribe()[Symbol.asyncIterator]();
    await iter.next();

    await expect(session.subscribe()[Symbol.asyncIterator]().next()).rejects.toThrow(
      'Session already started',
    );

    streamController?.close();
    await iter.next();
  });

  it('throws ClientError if session header is missing in response', async () => {
    const client = new Client({ baseURL: 'http://127.0.0.1:4356' });
    client.fetch = (async () => {
      return new Response('ok', {
        headers: {},
      });
    }) as unknown as typeof client.fetch;

    const session = client.createSession('alexa');
    await expect(session.subscribe()[Symbol.asyncIterator]().next()).rejects.toThrow(
      'Session ID not found in response headers',
    );
  });

  it('throws ClientError if response body is missing', async () => {
    const client = new Client({ baseURL: 'http://127.0.0.1:4356' });
    client.fetch = (async () => {
      const resp = new Response(null, {
        headers: {
          [Session.HEADER_KEY]: 'sess-789',
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
