import { describe, expect, it } from 'bun:test';
import { RETRY_INITIAL_DELAY_MS, RETRY_MAX_DELAY_MS, RetryBackoff } from './retry';

describe('RetryBackoff', () => {
  it('grows exponentially and caps at thirty seconds', () => {
    const backoff = new RetryBackoff();

    expect(Array.from({ length: 7 }, () => backoff.next())).toEqual([
      1_000, 2_000, 4_000, 8_000, 16_000, 30_000, 30_000,
    ]);
    expect(RETRY_MAX_DELAY_MS).toBe(30_000);
  });

  it('resets to the initial delay', () => {
    const backoff = new RetryBackoff();
    backoff.next();
    backoff.next();
    backoff.reset();

    expect(backoff.next()).toBe(RETRY_INITIAL_DELAY_MS);
  });
});
