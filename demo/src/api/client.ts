import { ClientError } from './client.error';
import { camelToSnake, toCamelCase, toSnakeCase } from './helpers';
import { Session } from './session';
import type { CallOptions, Profile, RequestOptions } from './types';

/**
 * HTTP and SSE API Client for the Helomi speech server.
 */
export class Client {
  /** API version prefix. */
  static readonly VERSION = '1';

  private readonly baseURL: string;

  constructor(options: { baseURL: string }) {
    const { baseURL } = options;
    this.baseURL = baseURL;
  }

  /**
   * Creates a new Session controller for the specified voice profile.
   */
  createSession(profileId: string): Session {
    return new Session(profileId, this);
  }

  async getProfile(
    profileId: string,
    require_prompt: string,
    options?: CallOptions,
  ): Promise<Profile<string> | null>;
  async getProfile(
    profileId: string,
    options?: CallOptions,
  ): Promise<Profile<null> | null>;
  async getProfile(
    profileId: string,
    ...args: [string, CallOptions?] | [CallOptions?]
  ): Promise<unknown> {
    let require_prompt: string | undefined;
    let options: CallOptions = {};

    for (const arg of args) {
      switch (typeof arg) {
        case 'string':
          require_prompt = arg;
          break;
        case 'object':
          options = arg;
          break;
      }
    }

    try {
      return await this.send(`/profile/${profileId}`, {
        ...options,
        query: {
          require_prompt,
        },
      });
    } catch (err) {
      if (err instanceof ClientError && err.isNotFound) {
        return null;
      }
      throw err;
    }
  }

  async getProfiles(
    require_prompt: string,
    options?: CallOptions,
  ): Promise<Profile<string>[]>;
  async getProfiles(options?: CallOptions): Promise<Profile<null>[]>;
  async getProfiles(...args: [string, CallOptions?] | [CallOptions?]): Promise<unknown> {
    let require_prompt: string | undefined;
    let options: CallOptions = {};

    for (const arg of args) {
      switch (typeof arg) {
        case 'string':
          require_prompt = arg;
          break;
        case 'object':
          options = arg;
          break;
      }
    }

    return await this.send('/profile', {
      ...options,
      query: {
        require_prompt,
      },
    });
  }

  /**
   * Sends an HTTP request to the API with JSON payload conversion and error checking.
   */
  async fetch(path: string, options: RequestOptions = {}): Promise<Response> {
    const url = new URL(`/api/v${Client.VERSION}${path}`, this.baseURL);
    const { headers, command, abort, trace_id, query } = options;

    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (!value) {
          continue;
        }

        url.searchParams.append(camelToSnake(key), value);
      }
    }

    let method: 'POST' | undefined;

    if (command) {
      command.traceId = trace_id;

      switch (command.type) {
        default:
          method = 'POST';
      }
    }

    let response: Response;

    try {
      response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...headers,
        },
        body: command ? JSON.stringify(toSnakeCase(command)) : undefined,
        signal: abort,
      });
    } catch (cause) {
      throw new ClientError('Failed to send request', {
        cause,
      });
    }

    if (!response.ok) {
      let message: string | undefined;
      try {
        ({ detail: message } = (await response.json()) as { detail: string });
      } catch {
        // Fallback to HTTP statusText
      }

      message ??= response.statusText;

      throw new ClientError(message, {
        status: response.status,
      });
    }

    return response;
  }

  /**
   * Sends a request and deserializes the JSON response converted to camelCase.
   */
  async send<TResult>(path: string, options: RequestOptions = {}): Promise<TResult> {
    const response = await this.fetch(path, options);

    try {
      return toCamelCase(await response.json());
    } catch (cause) {
      throw new ClientError('Failed to parse response', {
        cause,
      });
    }
  }
}
