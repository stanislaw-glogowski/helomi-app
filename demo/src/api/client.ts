import { ClientError } from './client.error';
import { camelToSnake, toCamelCase, toSnakeCase } from './helpers';
import { HelomiSession } from './session';
import type { CallOptions, Profile, RequestOptions } from './types';

/**
 * HTTP and SSE API HelomiClient for the Helomi speech server.
 */
export class HelomiClient {
  /** API version prefix. */
  static readonly VERSION = '1';

  private readonly baseUrl: string;

  constructor(options: { baseUrl: string }) {
    const { baseUrl } = options;
    this.baseUrl = baseUrl;
  }

  /**
   * Creates a new HelomiSession controller for the specified voice profile.
   */
  createSession(profileId: string): HelomiSession {
    return new HelomiSession(profileId, this);
  }

  async getProfile(
    profileId: string,
    requirePrompt: string,
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
    let requirePrompt: string | undefined;
    let options: CallOptions = {};

    for (const arg of args) {
      switch (typeof arg) {
        case 'string':
          requirePrompt = arg;
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
          requirePrompt,
        },
      });
    } catch (error) {
      if (error instanceof ClientError && error.isNotFound) {
        return null;
      }
      throw error;
    }
  }

  async getProfiles(
    requirePrompt: string,
    options?: CallOptions,
  ): Promise<Profile<string>[]>;
  async getProfiles(options?: CallOptions): Promise<Profile<null>[]>;
  async getProfiles(...args: [string, CallOptions?] | [CallOptions?]): Promise<unknown> {
    let requirePrompt: string | undefined;
    let options: CallOptions = {};

    for (const arg of args) {
      switch (typeof arg) {
        case 'string':
          requirePrompt = arg;
          break;
        case 'object':
          options = arg;
          break;
      }
    }

    return await this.send('/profile', {
      ...options,
      query: {
        requirePrompt,
      },
    });
  }

  /**
   * Sends an HTTP request to the API with JSON payload conversion and error checking.
   */
  async fetch(path: string, options: RequestOptions = {}): Promise<Response> {
    const url = new URL(`/api/v${HelomiClient.VERSION}${path}`, this.baseUrl);
    const { headers, command, abort, traceId, query } = options;

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
      command.traceId = traceId;

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
