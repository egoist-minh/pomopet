import assert from 'node:assert/strict';
import test from 'node:test';

import { APIError, api, configureAPIClient } from '../lib/api.ts';
import { getOrCreateChatThreadId } from '../lib/chat-memory.ts';
import { hasUnresolvedChatAction, resolveChatActionRequest, updateChatActionStatus } from '../lib/chat-actions.ts';
import {
  nextTimerValue,
  remainingSecondsUntil,
  shouldHandleTimerEnd,
  shouldOfferSessionExtension,
} from '../lib/session-timer.ts';

test('timer reaches zero without becoming negative', () => {
  assert.equal(nextTimerValue(2), 1);
  assert.equal(nextTimerValue(1), 0);
  assert.equal(nextTimerValue(0), 0);
});

test('deadline timer catches up after a delayed renderer callback', () => {
  const deadline = 10_000;
  assert.equal(remainingSecondsUntil(deadline, 1_000), 9);
  assert.equal(remainingSecondsUntil(deadline, 6_400), 4);
  assert.equal(remainingSecondsUntil(deadline, 10_500), 0);
});

test('only active timers handle zero', () => {
  assert.equal(shouldHandleTimerEnd('running', 0), true);
  assert.equal(shouldHandleTimerEnd('break', 0), true);
  assert.equal(shouldHandleTimerEnd('paused', 0), false);
  assert.equal(shouldHandleTimerEnd('running', 1), false);
});

test('session extension is offered only in the final two running minutes', () => {
  assert.equal(shouldOfferSessionExtension('running', 121), false);
  assert.equal(shouldOfferSessionExtension('running', 120), true);
  assert.equal(shouldOfferSessionExtension('running', 1), true);
  assert.equal(shouldOfferSessionExtension('running', 0), false);
  assert.equal(shouldOfferSessionExtension('paused', 60), false);
  assert.equal(shouldOfferSessionExtension('break', 60), false);
});

test('API errors reject instead of resolving to null', async (context) => {
  context.mock.method(console, 'error', () => {});
  context.mock.method(globalThis, 'fetch', async () => ({
    ok: false,
    status: 422,
    statusText: 'Unprocessable Entity',
  }));

  await assert.rejects(api.getTasks(), (error) => {
    assert.equal(error instanceof APIError, true);
    assert.equal(error.status, 422);
    return true;
  });
});

test('a lost backend rejects task mutations', async (context) => {
  context.mock.method(console, 'error', () => {});
  context.mock.method(globalThis, 'fetch', async () => {
    throw new TypeError('Failed to fetch');
  });

  await assert.rejects(
    api.createTask({ name: 'Offline task', priority: 'medium' }),
    APIError,
  );
});

test('planning client preserves hierarchy and optimistic version fields', async (context) => {
  const requests = [];
  context.mock.method(globalThis, 'fetch', async (url, options = {}) => {
    requests.push({ url, options });
    return {
      ok: true,
      json: async () => ({ id: 'item-1', version: 2 }),
    };
  });

  await api.createPlanItem({
    title: 'Review mistakes',
    horizon: 'day',
    goal_id: 'goal-1',
    parent_id: 'week-1',
    planned_for: '2026-11-02',
    estimate_minutes: 30,
  });
  await api.reschedulePlanItem('item-1', '2026-11-03', 1);
  await api.getPlanItems({ status: 'open', inbox: true });
  await api.approvePlanDraft(
    'draft-1',
    { schema_version: 1, assumptions: [], items: [] },
    'approval-key-1',
    true,
  );
  await api.regeneratePlanDraftBranch(
    'draft-1',
    'week-1',
    { schema_version: 1, assumptions: [], items: [] },
  );
  await api.deleteGoal('goal-1', 3);

  assert.equal(requests[0].url.endsWith('/planning/plan-items'), true);
  assert.deepEqual(JSON.parse(requests[0].options.body), {
    title: 'Review mistakes',
    horizon: 'day',
    goal_id: 'goal-1',
    parent_id: 'week-1',
    planned_for: '2026-11-02',
    estimate_minutes: 30,
  });
  assert.equal(requests[1].url.endsWith('/planning/plan-items/item-1/reschedule'), true);
  assert.deepEqual(JSON.parse(requests[1].options.body), {
    planned_for: '2026-11-03',
    expected_version: 1,
  });
  assert.equal(requests[2].url.includes('status=open'), true);
  assert.equal(requests[2].url.includes('inbox=true'), true);
  assert.equal(requests[3].url.endsWith('/planning/drafts/draft-1/approve'), true);
  assert.deepEqual(JSON.parse(requests[3].options.body), {
    draft: { schema_version: 1, assumptions: [], items: [] },
    idempotency_key: 'approval-key-1',
    override_capacity: true,
  });
  assert.equal(requests[4].url.endsWith('/planning/drafts/draft-1/regenerate'), true);
  assert.deepEqual(JSON.parse(requests[4].options.body), {
    client_id: 'week-1',
    draft: { schema_version: 1, assumptions: [], items: [] },
  });
  assert.equal(requests[5].url.endsWith('/planning/goals/goal-1'), true);
  assert.equal(requests[5].options.method, 'DELETE');
  assert.deepEqual(JSON.parse(requests[5].options.body), {
    expected_version: 3,
    confirm_delete: true,
  });
});

test('chat sends the selected Gemini provider', async (context) => {
  let request;
  context.mock.method(globalThis, 'fetch', async (_url, options) => {
    request = options;
    return {
      ok: true,
      json: async () => ({ status: 'completed', message: 'Gemini response', request_id: 'req-1' }),
    };
  });

  const response = await api.sendChat(
    'Help me focus',
    'gemini',
    'thread-123',
    420,
  );

  assert.equal(response.message, 'Gemini response');
  assert.deepEqual(JSON.parse(request.body), {
    message: 'Help me focus',
    provider: 'gemini',
    thread_id: 'thread-123',
    timezone_offset: 420,
  });
});

test('chat action confirm and cancel send only the thread identifier', async (context) => {
  const requests = [];
  context.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true,
      json: async () => ({ status: 'completed', message: 'Done', request_id: 'req-2' }),
    };
  });

  await api.confirmChatAction('action-1', 'thread-123');
  await api.cancelChatAction('action-2', 'thread-123');

  assert.equal(requests[0].url.endsWith('/chat/actions/action-1/confirm'), true);
  assert.equal(requests[1].url.endsWith('/chat/actions/action-2/cancel'), true);
  assert.deepEqual(JSON.parse(requests[0].options.body), { thread_id: 'thread-123' });
  assert.deepEqual(JSON.parse(requests[1].options.body), { thread_id: 'thread-123' });
});

test('action-card state locks pending actions and records completion', () => {
  const messages = [{
    role: 'pet',
    text: 'Create task',
    action: {
      id: 'action-1',
      type: 'create_task',
      preview: 'Create task',
      expires_at: '2026-10-18T16:00:00Z',
    },
    actionStatus: 'pending',
  }];

  assert.equal(hasUnresolvedChatAction(messages), true);
  const completed = updateChatActionStatus(messages, 'action-1', 'completed');
  assert.equal(completed[0].actionStatus, 'completed');
  assert.equal(hasUnresolvedChatAction(completed), false);
});

test('confirm refreshes application data while cancel does not', async () => {
  const calls = [];
  const client = {
    confirmChatAction: async () => {
      calls.push('confirm');
      return { status: 'completed', message: 'Done', request_id: 'req-3' };
    },
    cancelChatAction: async () => {
      calls.push('cancel');
      return { status: 'cancelled', message: 'Cancelled', request_id: 'req-4' };
    },
  };
  const refresh = async () => { calls.push('refresh'); };

  await resolveChatActionRequest('action-1', 'confirm', 'thread-123', refresh, client);
  await resolveChatActionRequest('action-2', 'cancel', 'thread-123', refresh, client);

  assert.deepEqual(calls, ['confirm', 'refresh', 'cancel']);
});

test('chat thread ID is generated once and restored from local storage', () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };

  assert.equal(
    getOrCreateChatThreadId(storage, () => 'generated-thread-id'),
    'generated-thread-id',
  );
  assert.equal(
    getOrCreateChatThreadId(storage, () => 'different-thread-id'),
    'generated-thread-id',
  );
});

test('API key configuration sends the key only to the backend', async (context) => {
  let request;
  context.mock.method(globalThis, 'fetch', async (_url, options) => {
    request = options;
    return {
      ok: true,
      json: async () => ({ provider: 'gemini', configured: true }),
    };
  });

  await api.configureAIProvider('gemini', 'secret-api-key');

  assert.equal(request.method, 'PUT');
  assert.deepEqual(JSON.parse(request.body), { api_key: 'secret-api-key' });
});

test('relationship memory client supports list, edit, delete, and toggles', async (context) => {
  const requests = [];
  context.mock.method(globalThis, 'fetch', async (url, options = {}) => {
    requests.push({ url, options });
    return {
      ok: true,
      json: async () => url.endsWith('/profile')
        ? { id: 'profile-1', personalization_on: false, memory_prompts_on: true }
        : [],
    };
  });

  await api.getRelationshipMemories();
  await api.updateRelationshipMemory('memory-1', 'An');
  await api.deleteRelationshipMemory('memory-1', 'never_mention');
  await api.updateRelationshipProfile({ personalization_on: false });
  await api.deleteRelationshipData();

  assert.equal(requests[0].url.endsWith('/relationship/memories'), true);
  assert.equal(requests[1].options.method, 'PATCH');
  assert.deepEqual(JSON.parse(requests[1].options.body), { value: 'An' });
  assert.equal(requests[2].options.method, 'DELETE');
  assert.deepEqual(JSON.parse(requests[2].options.body), { action: 'never_mention' });
  assert.deepEqual(JSON.parse(requests[3].options.body), { personalization_on: false });
  assert.equal(requests[4].url.endsWith('/relationship/data'), true);
});

test('behavioral personalization client keeps suggestions editable and sends rank context', async (context) => {
  const requests = [];
  context.mock.method(globalThis, 'fetch', async (url, options = {}) => {
    requests.push({ url, options });
    return {
      ok: true,
      json: async () => url.includes('focus-suggestion')
        ? { duration: { minutes: 50, mode: 'prefill' }, task_rank: { rank: 0 } }
        : { id: 'session-1', duration: 3000, time_left: 3000, state: 'running' },
    };
  });

  await api.getRelationshipHabits();
  await api.getFocusSuggestion('today');
  await api.startSession('task-1', 3000, {
    view: 'today',
    rank: 0,
    visible_task_count: 3,
    sort_mode: 'importance',
    duration_source: 'habit_prefill',
    suggested_duration_minutes: 50,
    suggested_rank: 0,
  });
  await api.dismissRelationshipHabit('habit-1');

  assert.equal(requests[0].url.endsWith('/relationship/habits'), true);
  assert.equal(requests[1].url.includes('/relationship/focus-suggestion?view=today'), true);
  const start = JSON.parse(requests[2].options.body);
  assert.equal(start.duration, 3000);
  assert.equal(start.source, 'ui');
  assert.equal(typeof start.idempotency_key, 'string');
  assert.deepEqual(start.action_context, {
    view: 'today',
    rank: 0,
    visible_task_count: 3,
    sort_mode: 'importance',
    duration_source: 'habit_prefill',
    suggested_duration_minutes: 50,
    suggested_rank: 0,
  });
  assert.equal(requests[3].options.method, 'DELETE');
});

test('episodic relationship client keeps context opt-in and supports suppression', async (context) => {
  const requests = [];
  context.mock.method(globalThis, 'fetch', async (url, options = {}) => {
    requests.push({ url, options });
    return {
      ok: true,
      json: async () => url.endsWith('/relational-state')
        ? { rule_version: 'relationship-v1', evidence_count: 1 }
        : [],
    };
  });

  await api.getRelationshipEpisodes();
  await api.getRelationshipRituals();
  await api.getRelationalState();
  await api.updateRelationshipProfile({ relationship_context_on: true });
  await api.updateRelationshipEpisode('episode-1', 'never_mention');
  await api.updateRelationshipRitual('ritual-1', 'archived');

  assert.equal(requests[0].url.endsWith('/relationship/episodes'), true);
  assert.equal(requests[1].url.endsWith('/relationship/rituals'), true);
  assert.equal(requests[2].url.endsWith('/relationship/relational-state'), true);
  assert.deepEqual(JSON.parse(requests[3].options.body), { relationship_context_on: true });
  assert.deepEqual(JSON.parse(requests[4].options.body), { action: 'never_mention' });
  assert.deepEqual(JSON.parse(requests[5].options.body), { action: 'archived' });
});

test('runtime API configuration controls the port and authorization header', async (context) => {
  let request;
  configureAPIClient({
    apiBaseUrl: 'http://127.0.0.1:45678/api',
    token: 'runtime-secret',
  });
  context.mock.method(globalThis, 'fetch', async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => [] };
  });

  await api.getTasks();

  assert.equal(request.url, 'http://127.0.0.1:45678/api/tasks/');
  assert.equal(request.options.headers['X-PomoPet-Token'], 'runtime-secret');
  configureAPIClient(null);
});
