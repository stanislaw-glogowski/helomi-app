import { describe, expect, it } from 'bun:test';
import { Colorize, colorize } from './colorize';

describe('colorize', () => {
  it('returns original text if no colors provided', () => {
    expect(colorize('hello')).toBe('hello');
  });

  it('wraps text with single color and reset code', () => {
    expect(colorize('hello', 'cyan')).toBe(`${Colorize.cyan}hello\x1b[0m`);
  });

  it('wraps text with multiple colors and reset code', () => {
    expect(colorize('hello', 'bold', 'cyan')).toBe(
      `${Colorize.bold}${Colorize.cyan}hello\x1b[0m`,
    );
  });
});
