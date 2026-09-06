import { describe, expect, it } from 'bun:test';
import type { SystemModelMessage } from 'ai';
import { MessageManager } from './message.manager';

describe('MessageManager', () => {
  const system: SystemModelMessage = {
    role: 'system',
    content: 'You are a helpful voice assistant.',
  };

  it('initializes with system prompt and empty history', () => {
    const manager = new MessageManager({ system });
    expect(manager.system).toEqual(system);
    expect(manager.history).toEqual([]);
  });

  it('appends messages to history', () => {
    const manager = new MessageManager({ system });
    manager.append({ role: 'user', content: 'Hello' });
    manager.append({ role: 'assistant', content: 'Hi there!' });

    expect(manager.history).toEqual([
      { role: 'user', content: 'Hello' },
      { role: 'assistant', content: 'Hi there!' },
    ]);
  });

  it('limits history to MAX_MESSAGES (10)', () => {
    const manager = new MessageManager({ system });

    for (let i = 1; i <= 15; i++) {
      manager.append({ role: 'user', content: `Message ${i}` });
    }

    expect(manager.history.length).toBe(10);
    expect(manager.history[0]?.content).toBe('Message 6');
    expect(manager.history[9]?.content).toBe('Message 15');
  });

  it('returns a copy of history array', () => {
    const manager = new MessageManager({ system });
    manager.append({ role: 'user', content: 'Test' });

    const history1 = manager.history;
    const history2 = manager.history;
    expect(history1).not.toBe(history2);
    expect(history1).toEqual(history2);
  });
});
