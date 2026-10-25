import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getSpeechBubbleDisplayDuration,
  MAX_SPEECH_BUBBLE_DURATION_MS,
  MIN_SPEECH_BUBBLE_DURATION_MS,
  wrapSpeechBubbleText,
} from '../lib/speech-bubble.ts';

test('speech wrapping keeps all text and wraps at the configured unit count', () => {
  const source = 'one two three four five six seven eight nine ten eleven twelve';
  const wrapped = wrapSpeechBubbleText(source, 5);

  assert.equal(wrapped, 'one two three four five\nsix seven eight nine ten\neleven twelve');
  assert.equal(wrapped.replace(/\n/g, ' '), source);
});

test('speech wrapping preserves explicit paragraph breaks', () => {
  assert.equal(
    wrapSpeechBubbleText('việc một việc hai\nnghỉ ngắn rồi tiếp tục', 3),
    'việc một việc\nhai\nnghỉ ngắn rồi\ntiếp tục',
  );
});

test('short speech stays visible for the minimum reading time', () => {
  assert.equal(getSpeechBubbleDisplayDuration('Okay!'), MIN_SPEECH_BUBBLE_DURATION_MS);
});

test('longer speech receives proportionally more reading time', () => {
  const twentyWords = Array(20).fill('word').join(' ');

  assert.equal(getSpeechBubbleDisplayDuration(twentyWords), 8_000);
  assert.ok(
    getSpeechBubbleDisplayDuration(Array(50).fill('word').join(' '))
      > getSpeechBubbleDisplayDuration(twentyWords),
  );
});

test('speech display time is capped at one minute', () => {
  assert.equal(
    getSpeechBubbleDisplayDuration(Array(500).fill('word').join(' ')),
    MAX_SPEECH_BUBBLE_DURATION_MS,
  );
});
