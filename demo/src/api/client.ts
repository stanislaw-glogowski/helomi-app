import { ClientError } from './client.error';
import { toCamelCase, toSnakeCase } from './helpers';
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

  /**
   * Fetches metadata for a single profile by ID.
   * Returns null if the profile does not exist.
   */
  async getProfile(profileId: string, options?: CallOptions): Promise<Profile | null> {
    try {
      return await this.send(`/profile/${profileId}`, options);
    } catch (err) {
      if (err instanceof ClientError && err.isNotFound) {
        return null;
      }
      throw err;
    }
  }

  /**
   * Lists all available profiles loaded in the Helomi server.
   */
  async getProfiles(options?: CallOptions): Promise<Profile[]> {
    return await this.send('/profile', options);
  }

  /**
   * Sends an HTTP request to the API with JSON payload conversion and error checking.
   */
  async fetch(path: string, options: RequestOptions = {}): Promise<Response> {
    const url = new URL(`/api/v${Client.VERSION}${path}`, this.baseURL);
    const { headers, command, abort, trace_id } = options;

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
