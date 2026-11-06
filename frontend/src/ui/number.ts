/** Generic presentation controls only. Bounds are supplied by the caller. */
export function assertIntegerRange(value: number, min: number, max: number): void {
  if (![value, min, max].every(Number.isSafeInteger) || min > max || value < min || value > max) {
    throw new RangeError('A whole value within ordered, safe-integer bounds is required.');
  }
}

export function stepNumber(value: number, min: number, max: number, direction: -1 | 1): number {
  assertIntegerRange(value, min, max);
  return direction === 1 ? value >= max ? max : value + 1 : value <= min ? min : value - 1;
}

export function numberForKey(key: string, value: number, min: number, max: number): number | undefined {
  assertIntegerRange(value, min, max);
  switch (key) {
    case 'ArrowUp': return stepNumber(value, min, max, 1);
    case 'ArrowDown': return stepNumber(value, min, max, -1);
    case 'Home': return min;
    case 'End': return max;
    default: return undefined;
  }
}

export function numberFromInput(raw: string, min: number, max: number): number | undefined {
  assertIntegerRange(min, min, max);
  if (!/^-?\d+$/.test(raw)) return undefined;
  const value = Number(raw);
  return Number.isSafeInteger(value) && value >= min && value <= max ? value : undefined;
}
