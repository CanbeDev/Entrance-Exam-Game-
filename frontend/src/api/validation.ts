import { schemas } from './generated.ts';
import type { Components } from './generated.ts';

export interface Schema {
  readonly $ref?: string; readonly type?: string; readonly const?: unknown;
  readonly enum?: readonly unknown[]; readonly anyOf?: readonly Schema[]; readonly oneOf?: readonly Schema[];
  readonly properties?: Readonly<Record<string, Schema>>; readonly required?: readonly string[];
  readonly additionalProperties?: boolean | Schema; readonly items?: Schema;
  readonly prefixItems?: readonly Schema[]; readonly minItems?: number; readonly maxItems?: number;
  readonly minLength?: number; readonly maxLength?: number; readonly pattern?: string; readonly format?: string;
  readonly minimum?: number; readonly maximum?: number; readonly exclusiveMinimum?: number;
  readonly exclusiveMaximum?: number;
}
export type Parser<T> = (value: unknown) => T;

/** Deliberately bounded to the JSON-schema keywords present in the offline export. */
export function matches(value: unknown, schema: Schema): boolean {
  if (schema.$ref) {
    const name = schema.$ref.split('/').at(-1) as keyof typeof schemas;
    return !!schemas[name] && matches(value, schemas[name] as Schema);
  }
  if (schema.const !== undefined && value !== schema.const) return false;
  if (schema.enum && !schema.enum.includes(value)) return false;
  if (schema.anyOf && !schema.anyOf.some((s) => matches(value, s))) return false;
  if (schema.oneOf && schema.oneOf.filter((s) => matches(value, s)).length !== 1) return false;
  switch (schema.type) {
    case 'null': return value === null;
    case 'string':
      if (typeof value !== 'string') return false;
      if (schema.minLength !== undefined && [...value].length < schema.minLength) return false;
      if (schema.maxLength !== undefined && [...value].length > schema.maxLength) return false;
      if (schema.pattern && !new RegExp(schema.pattern).test(value)) return false;
      if (schema.format === 'date' && !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
      if (schema.format === 'date-time' && !Number.isFinite(Date.parse(value))) return false;
      return true;
    case 'integer':
    case 'number':
      if (typeof value !== 'number' || !Number.isFinite(value)) return false;
      if (schema.type === 'integer' && !Number.isSafeInteger(value)) return false;
      return !(schema.minimum !== undefined && value < schema.minimum
        || schema.maximum !== undefined && value > schema.maximum
        || schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum
        || schema.exclusiveMaximum !== undefined && value >= schema.exclusiveMaximum);
    case 'boolean': return typeof value === 'boolean';
    case 'array':
      if (!Array.isArray(value)) return false;
      if (schema.minItems !== undefined && value.length < schema.minItems) return false;
      if (schema.maxItems !== undefined && value.length > schema.maxItems) return false;
      if (schema.prefixItems && !schema.prefixItems.every((s, i) => matches(value[i], s))) return false;
      return !schema.items || value.every((v) => matches(v, schema.items!));
    case 'object':
      if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
      return (schema.required ?? []).every((key) => Object.hasOwn(value, key))
        && (!schema.properties?.type?.const || Object.hasOwn(value, 'type'))
        && Object.entries(value).every(([key, item]) => {
          const property = schema.properties?.[key];
          return property ? matches(item, property) : schema.additionalProperties !== false;
        });
    default: return true;
  }
}

export function parser<T>(schema: Schema): Parser<T> {
  return (value) => {
    if (!matches(value, schema)) throw new Error('Response did not match the API contract');
    return value as T;
  };
}
export function component<K extends keyof Components>(name: K): Parser<Components[K]> {
  return parser<Components[K]>(schemas[name] as Schema);
}
const string = { type: 'string', minLength: 1 } as const;
export const loginSchema: Schema = {
  type: 'object', required: ['user', 'expires_at'], properties: {
    user: { $ref: '#/components/schemas/UserPublic' }, expires_at: { type: 'string', format: 'date-time' },
  },
};
export const csrfSchema: Schema = {
  type: 'object', required: ['csrf_token'], properties: {
    csrf_token: { type: 'string', pattern: '^[a-zA-Z0-9_-]{43}$' },
  },
};
export const catalogSchema: Schema = {
  type: 'object', required: ['population_snapshot', 'countries'], properties: {
    population_snapshot: { $ref: '#/components/schemas/PublicPopulationSnapshot' },
    countries: { type: 'array', items: { type: 'object', required: ['id', 'name', 'population', 'base_soldier_value'],
      properties: { id: string, name: string, population: { type: 'integer', minimum: 1 },
        base_soldier_value: { type: 'integer', minimum: 1, maximum: 9 } } } },
  },
};
