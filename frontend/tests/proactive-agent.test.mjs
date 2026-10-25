import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createExecutionAcknowledger,
  createProactiveScheduler,
  PROACTIVE_POLL_INTERVAL_MS,
  shouldPresentProactiveDecision,
  transitionTrigger,
} from '../lib/proactive-agent.ts';
import { appendProactivePlanSuggestion } from '../lib/chat-actions.ts';
import { api, configureAPIClient } from '../lib/api.ts';

const decision = (overrides = {}) => ({
  decision_id: 'decision-1',
  action: 'TELL_JOKE',
  message: 'A short joke',
  target: null,
  reason_codes: ['IDLE_OR_BREAK'],
  status: 'SELECTED',
  created_at: null,
  executed_at: null,
  ...overrides,
});

test('scheduler starts immediately, uses the five-minute interval, and cleans up', async () => {
  let scheduled;
  let interval;
  let cleared;
  const inputs = [];
  const scheduler = createProactiveScheduler({
    evaluate: async input => {
      inputs.push(input);
      return decision();
    },
    getSessionState: () => 'idle',
    getProvider: () => 'gemini',
    getThreadId: () => 'thread-1234',
    onDecision: () => {},
    createRequestId: () => 'request-1',
    setIntervalFn: (callback, milliseconds) => {
      scheduled = callback;
      interval = milliseconds;
      return 42;
    },
    clearIntervalFn: id => { cleared = id; },
  });

  scheduler.start('welcome');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(inputs.length, 1);
  assert.equal(inputs[0].provider, 'gemini');
  assert.equal(inputs[0].trigger, 'welcome');
  assert.equal(inputs[0].thread_id, 'thread-1234');
  assert.equal(interval, PROACTIVE_POLL_INTERVAL_MS);
  scheduled();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(inputs.length, 2);
  scheduler.stop();
  assert.equal(cleared, 42);
});

test('scheduler does not overlap requests', async () => {
  let release;
  const waiting = new Promise(resolve => { release = resolve; });
  let calls = 0;
  const scheduler = createProactiveScheduler({
    evaluate: async () => {
      calls += 1;
      await waiting;
      return decision();
    },
    getSessionState: () => 'idle',
    getProvider: () => 'openai',
    onDecision: () => {},
    createRequestId: () => `request-${calls}`,
  });

  const first = scheduler.trigger('periodic');
  assert.equal(await scheduler.trigger('periodic'), false);
  assert.equal(calls, 1);
  release();
  assert.equal(await first, true);
});

test('silent decisions are not presented or acknowledged', async () => {
  const silent = decision({ action: 'STAY_SILENT', message: null, status: 'SILENT' });
  const calls = [];
  const acknowledge = createExecutionAcknowledger(async id => calls.push(id));
  assert.equal(shouldPresentProactiveDecision(silent), false);
  assert.equal(await acknowledge(silent), false);
  assert.deepEqual(calls, []);
});

test('jokes and planning suggestions render and execute exactly once', async () => {
  const calls = [];
  const acknowledge = createExecutionAcknowledger(async id => calls.push(id));
  const joke = decision();
  const plan = decision({
    decision_id: 'decision-2',
    action: 'SUGGEST_PLAN',
    message: 'Open Plan?',
    target: 'plan',
  });
  assert.equal(shouldPresentProactiveDecision(joke), true);
  assert.equal(shouldPresentProactiveDecision(plan), true);
  assert.equal(shouldPresentProactiveDecision(decision({
    action: 'GIVE_HYDRATION_TIP',
    message: 'Water break?',
  })), true);
  assert.equal(await acknowledge(joke), true);
  assert.equal(await acknowledge(joke), false);
  assert.equal(await acknowledge(plan), true);
  assert.deepEqual(calls, ['decision-1', 'decision-2']);
});

test('session completion transitions emit proactive triggers', () => {
  assert.equal(transitionTrigger('running', 'break'), 'focus_ended');
  assert.equal(transitionTrigger('break', 'idle'), 'break_ended');
  assert.equal(transitionTrigger('idle', 'running'), null);
});

test('planning suggestions appear once in chat with an explicit plan target', () => {
  const plan = decision({
    decision_id: 'plan-decision',
    action: 'SUGGEST_PLAN',
    message: 'Mình mở Plan nhé?',
    target: 'plan',
  });
  const first = appendProactivePlanSuggestion([], plan);
  const duplicate = appendProactivePlanSuggestion(first, plan);

  assert.deepEqual(first, [{
    role: 'pet',
    text: 'Mình mở Plan nhé?',
    proactiveSuggestion: { decisionId: 'plan-decision', target: 'plan' },
  }]);
  assert.equal(duplicate, first);
  assert.deepEqual(appendProactivePlanSuggestion([], decision()), []);
});

test('proactive trace client lists runs and opens one run', async context => {
  const requests = [];
  configureAPIClient({ apiBaseUrl: 'http://127.0.0.1:8000/api', token: '' });
  context.mock.method(globalThis, 'fetch', async url => {
    requests.push(url);
    return {
      ok: true,
      json: async () => requests.length === 1 ? [] : {
        ...decision(),
        state_snapshot: {},
        candidate_actions: ['STAY_SILENT', 'TELL_JOKE'],
        trace: [],
      },
    };
  });

  assert.deepEqual(await api.getProactiveRuns(20), []);
  assert.equal((await api.getProactiveRun('decision/with slash')).decision_id, 'decision-1');
  assert.equal(requests[0].endsWith('/proactive/runs?limit=20'), true);
  assert.equal(requests[1].endsWith('/proactive/runs/decision%2Fwith%20slash'), true);
  configureAPIClient(null);
});
