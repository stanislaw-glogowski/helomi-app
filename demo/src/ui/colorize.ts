// ANSI styling codes for readable, aesthetic terminal output
export const Colorize = {
  bold: '\x1b[1m',
  dim: '\x1b[2m',
  cyan: '\x1b[36m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  magenta: '\x1b[35m',
  red: '\x1b[31m',
  gray: '\x1b[90m',
} as const;

export type Color = keyof typeof Colorize;

export function colorize(text: string, ...colors: Color[]): string {
  if (!colors.length) {
    return text;
  }

  return `${colors.map((color) => Colorize[color]).join('')}${text}\x1b[0m`;
}
