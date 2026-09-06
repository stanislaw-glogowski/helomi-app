/**
 * Custom error class for Helomi API client errors.
 * Encapsulates HTTP status codes and error causes.
 */
export class ClientError extends Error {
  /** HTTP response status code, if applicable. */
  readonly status: number | null;

  constructor(
    message: string,
    options: {
      status?: number;
      cause?: unknown;
    } = {},
  ) {
    const { status = null, cause } = options;

    super(message, {
      cause,
    });
    this.name = 'ClientError';
    this.status = status;
  }

  /**
   * Indicates whether the error was caused by a 404 Not Found response.
   */
  get isNotFound(): boolean {
    return this.status === 404;
  }
}
