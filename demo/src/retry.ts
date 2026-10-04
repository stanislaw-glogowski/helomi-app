export const RETRY_INITIAL_DELAY_MS = 1_000;
export const RETRY_MAX_DELAY_MS = 30_000;

export type Sleep = (delayMs: number) => Promise<void>;

export class RetryBackoff {
  private nextDelayMs = RETRY_INITIAL_DELAY_MS;

  next(): number {
    const delayMs = this.nextDelayMs;
    this.nextDelayMs = Math.min(this.nextDelayMs * 2, RETRY_MAX_DELAY_MS);
    return delayMs;
  }

  reset(): void {
    this.nextDelayMs = RETRY_INITIAL_DELAY_MS;
  }
}

export const sleep: Sleep = async (delayMs) => {
  await Bun.sleep(delayMs);
};
