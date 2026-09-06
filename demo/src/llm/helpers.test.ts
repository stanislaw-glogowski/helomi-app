import { describe, expect, it } from 'bun:test';
import { cleanLine } from './helpers';

describe('cleanLine', () => {
  it('removes reasoning think blocks', () => {
    const input = '<think>I should greet the user warmly.</think>Hello there!';
    expect(cleanLine(input)).toBe('Hello there!');
  });

  it('removes multiline think blocks', () => {
    const input = '<think>\nStep 1: Check time.\nStep 2: Answer.\n</think>Good morning!';
    expect(cleanLine(input)).toBe('Good morning!');
  });

  it('removes markdown code blocks', () => {
    const input = 'Here is the answer: ```const x = 1;``` Done.';
    expect(cleanLine(input)).toBe('Here is the answer: Done.');
  });

  it('strips markdown formatting characters', () => {
    const input = '*bold* _italic_ # header `code` ~strikethrough~ > quote';
    expect(cleanLine(input)).toBe('bold italic header code strikethrough quote');
  });

  it('converts markdown links to plain text', () => {
    const input =
      'Visit [Helomi App](https://github.com/stanislaw-glogowski/helomi-app) today!';
    expect(cleanLine(input)).toBe('Visit Helomi App today!');
  });

  it('collapses multiple whitespace and trims', () => {
    const input = '   Too    many    spaces.   ';
    expect(cleanLine(input)).toBe('Too many spaces.');
  });

  it('preserves allowed vocal delivery tags in square brackets', () => {
    const input = 'Hello, friend! [laughter] How have you been? [breath]';
    expect(cleanLine(input)).toBe(
      'Hello, friend! [laughter] How have you been? [breath]',
    );
  });
});
