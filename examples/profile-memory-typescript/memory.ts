import type { CoreMessage } from "ai";

/**
 * Manages an isolated sliding window conversation memory for each profile.
 * Retains up to `maxMessages` (default: 10) per profile.
 */
export class ProfileMemoryManager {
  private readonly memory: Map<string, CoreMessage[]> = new Map();
  private readonly maxMessages: number;

  constructor(maxMessages: number = 10) {
    this.maxMessages = Math.max(1, maxMessages);
  }

  /**
   * Retrieves current conversation messages for a given profile.
   */
  getMessages(profileId: string): CoreMessage[] {
    return [...(this.memory.get(profileId) ?? [])];
  }

  /**
   * Appends a message to the profile's memory and truncates oldest entries
   * if exceeding `maxMessages`.
   */
  addMessage(profileId: string, message: CoreMessage): void {
    const history = this.memory.get(profileId) ?? [];
    history.push(message);

    // Keep only the most recent N messages
    if (history.length > this.maxMessages) {
      this.memory.set(profileId, history.slice(-this.maxMessages));
    } else {
      this.memory.set(profileId, history);
    }
  }

  /**
   * Appends a user turn to the profile's memory.
   */
  addUserMessage(profileId: string, content: string): void {
    this.addMessage(profileId, { role: "user", content });
  }

  /**
   * Appends an assistant turn to the profile's memory.
   */
  addAssistantMessage(profileId: string, content: string): void {
    this.addMessage(profileId, { role: "assistant", content });
  }

  /**
   * Returns current message count for the profile.
   */
  getCount(profileId: string): number {
    return this.memory.get(profileId)?.length ?? 0;
  }

  /**
   * Clears memory for a specific profile or for all profiles.
   */
  clear(profileId?: string): void {
    if (profileId) {
      this.memory.delete(profileId);
    } else {
      this.memory.clear();
    }
  }

  /**
   * Returns a debug summary of current memory storage.
   */
  getSummary(profileId: string): string {
    const count = this.getCount(profileId);
    return `[Memory: ${profileId}] ${count}/${this.maxMessages} messages in context`;
  }
}
