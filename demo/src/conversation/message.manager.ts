import type { ModelMessage, SystemModelMessage } from 'ai';

/**
 * Manages rolling conversation history for an LLM session.
 * Preserves system prompt and retains up to MAX_MESSAGES past interactions.
 */
export class MessageManager {
  /** Maximum number of history messages retained in memory. */
  static readonly MAX_MESSAGES = 10;

  /** System prompt defining persona and voice delivery formatting rules. */
  readonly system: SystemModelMessage;
  private models: ModelMessage[] = [];

  constructor(options: {
    system: SystemModelMessage;
  }) {
    const { system } = options;
    this.system = system;
  }

  /**
   * Returns a copy of the recent conversation history messages.
   */
  get history(): ModelMessage[] {
    return [...this.models];
  }

  /**
   * Appends a message to conversation history, truncating older messages if exceeding capacity.
   */
  append(message: ModelMessage): void {
    this.models.push(message);

    if (this.models.length > MessageManager.MAX_MESSAGES) {
      this.models = this.models.slice(-MessageManager.MAX_MESSAGES);
    }
  }
}
