/**
 * Checks if a value is a plain JavaScript object.
 */
function isPlainObject(val: unknown): val is Record<string, unknown> {
  return Object.prototype.toString.call(val) === '[object Object]';
}

/**
 * Converts a camelCase string to snake_case.
 */
export function camelToSnake(str: string): string {
  return str.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();
}

/**
 * Converts a snake_case string to camelCase.
 */
export function snakeToCamel(str: string): string {
  return str.replace(/_([a-z0-9])/g, (_, char: string) => char.toUpperCase());
}

/**
 * Recursively converts object keys from camelCase to snake_case for API requests.
 */
export function toSnakeCase<TData>(data: TData): unknown {
  if (Array.isArray(data)) {
    return data.map(toSnakeCase);
  }

  if (isPlainObject(data)) {
    return Object.fromEntries(
      Object.entries(data).map(([key, value]) => [camelToSnake(key), toSnakeCase(value)]),
    );
  }

  return data;
}

/**
 * Recursively converts object keys from snake_case to camelCase for API responses.
 */
export function toCamelCase<TResult = unknown>(data: unknown): TResult {
  if (Array.isArray(data)) {
    return data.map(toCamelCase) as unknown as TResult;
  }

  if (isPlainObject(data)) {
    return Object.fromEntries(
      Object.entries(data).map(([key, value]) => [snakeToCamel(key), toCamelCase(value)]),
    ) as TResult;
  }

  return data as TResult;
}
