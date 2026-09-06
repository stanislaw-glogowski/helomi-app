import { describe, expect, it } from 'bun:test';
import { camelToSnake, snakeToCamel, toCamelCase, toSnakeCase } from './helpers';

describe('camelToSnake', () => {
  it('converts camelCase string to snake_case', () => {
    expect(camelToSnake('profileId')).toBe('profile_id');
    expect(camelToSnake('sayText')).toBe('say_text');
    expect(camelToSnake('traceId')).toBe('trace_id');
    expect(camelToSnake('simple')).toBe('simple');
  });

  it('handles consecutive lowercase and uppercase letters', () => {
    expect(camelToSnake('isActiveProfile')).toBe('is_active_profile');
  });
});

describe('snakeToCamel', () => {
  it('converts snake_case string to camelCase', () => {
    expect(snakeToCamel('profile_id')).toBe('profileId');
    expect(snakeToCamel('say_text')).toBe('sayText');
    expect(snakeToCamel('is_active')).toBe('isActive');
    expect(snakeToCamel('simple')).toBe('simple');
  });
});

describe('toSnakeCase', () => {
  it('recursively converts object keys to snake_case', () => {
    const input = {
      profileId: 'default',
      isActive: true,
      commandPayload: {
        traceId: '123',
        voiceSpeed: 1.0,
      },
    };

    expect(toSnakeCase(input)).toEqual({
      profile_id: 'default',
      is_active: true,
      command_payload: {
        trace_id: '123',
        voice_speed: 1.0,
      },
    });
  });

  it('converts array of objects to snake_case', () => {
    const input = [{ profileId: 'p1' }, { profileId: 'p2' }];
    expect(toSnakeCase(input)).toEqual([{ profile_id: 'p1' }, { profile_id: 'p2' }]);
  });

  it('returns primitive values unchanged', () => {
    expect(toSnakeCase('string')).toBe('string');
    expect(toSnakeCase(123)).toBe(123);
    expect(toSnakeCase(null)).toBe(null);
  });
});

describe('toCamelCase', () => {
  it('recursively converts object keys to camelCase', () => {
    const input = {
      profile_id: 'default',
      is_active: true,
      nested_data: {
        user_prompt: 'Hello',
      },
    };

    expect(toCamelCase<Record<string, unknown>>(input)).toEqual({
      profileId: 'default',
      isActive: true,
      nestedData: {
        userPrompt: 'Hello',
      },
    });
  });

  it('converts array of objects to camelCase', () => {
    const input = [{ profile_id: 'p1' }, { profile_id: 'p2' }];
    expect(toCamelCase<Array<{ profileId: string }>>(input)).toEqual([
      { profileId: 'p1' },
      { profileId: 'p2' },
    ]);
  });

  it('returns primitive values unchanged', () => {
    expect(toCamelCase<string>('text')).toBe('text');
    expect(toCamelCase<number>(42)).toBe(42);
    expect(toCamelCase<null>(null)).toBe(null);
  });
});
