import { describe, expect, it } from 'bun:test';
import { ClientError } from './client.error';

describe('ClientError', () => {
  it('creates error with message and default properties', () => {
    const error = new ClientError('Something failed');
    expect(error.message).toBe('Something failed');
    expect(error.name).toBe('ClientError');
    expect(error.status).toBeNull();
    expect(error.isNotFound).toBe(false);
  });

  it('sets status and detects isNotFound for 404 status', () => {
    const error404 = new ClientError('Profile not found', { status: 404 });
    expect(error404.status).toBe(404);
    expect(error404.isNotFound).toBe(true);

    const error500 = new ClientError('Internal error', { status: 500 });
    expect(error500.status).toBe(500);
    expect(error500.isNotFound).toBe(false);
  });

  it('preserves error cause', () => {
    const cause = new Error('Network timeout');
    const error = new ClientError('Request failed', { cause });
    expect(error.cause).toBe(cause);
  });
});
