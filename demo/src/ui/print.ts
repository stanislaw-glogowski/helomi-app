import type { Color } from './colorize';
import { colorize } from './colorize';

export function print(...parts: Array<string | [string, ...Color[]]>): void {
  console.log(
    parts.map((part) => (typeof part === 'string' ? part : colorize(...part))).join(''),
  );
}
