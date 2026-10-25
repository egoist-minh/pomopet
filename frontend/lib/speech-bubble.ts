export const SPEECH_BUBBLE_UNITS_PER_LINE = 10;
export const MIN_SPEECH_BUBBLE_DURATION_MS = 6_000;
export const MAX_SPEECH_BUBBLE_DURATION_MS = 60_000;

const SPEECH_BUBBLE_READING_LEAD_IN_MS = 2_000;
const SPEECH_BUBBLE_MS_PER_UNIT = 300;

/**
 * Keep chat replies visible long enough to read. The unit-based estimate works
 * for both Vietnamese and English, while the bounds keep short notices snappy
 * and prevent a forgotten bubble from staying on screen indefinitely.
 */
export function getSpeechBubbleDisplayDuration(text: string): number {
  const units = text.trim().split(/\s+/).filter(Boolean).length;
  const estimatedDuration = SPEECH_BUBBLE_READING_LEAD_IN_MS
    + units * SPEECH_BUBBLE_MS_PER_UNIT;

  return Math.min(
    MAX_SPEECH_BUBBLE_DURATION_MS,
    Math.max(MIN_SPEECH_BUBBLE_DURATION_MS, estimatedDuration),
  );
}

/**
 * Wrap speech for the compact pet window without removing any content.
 * Whitespace-delimited units are used as a lightweight token approximation so
 * Vietnamese and English remain readable without shipping a model tokenizer.
 */
export function wrapSpeechBubbleText(
  text: string,
  unitsPerLine = SPEECH_BUBBLE_UNITS_PER_LINE,
): string {
  if (!Number.isInteger(unitsPerLine) || unitsPerLine < 1) {
    throw new RangeError('unitsPerLine must be a positive integer');
  }

  return text
    .split(/\r?\n/)
    .map(paragraph => {
      const units = paragraph.trim().split(/\s+/).filter(Boolean);
      const lines: string[] = [];
      for (let index = 0; index < units.length; index += unitsPerLine) {
        lines.push(units.slice(index, index + unitsPerLine).join(' '));
      }
      return lines.join('\n');
    })
    .join('\n');
}
