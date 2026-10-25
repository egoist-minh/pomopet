import type {
  FocusSuggestion,
  HabitProfile,
  PersonalMemory,
  RelationalState,
  RelationshipEpisode,
  RelationshipMemoryAction,
  SharedRitual,
  UserProfile,
} from './relationship-types';
import type { ProactiveDecision, ProactiveEvaluateInput, ProactiveRun } from './proactive-agent';

const MAX_RETRIES = 3;
const RETRY_DELAY_BASE = 1000;

export interface RuntimeAPIConfig {
  apiBaseUrl: string;
  token: string;
}

interface ElectronRuntimeBridge {
  getRuntimeConfig?: () => Promise<RuntimeAPIConfig>;
}

let configuredRuntime: RuntimeAPIConfig | null = null;
let runtimePromise: Promise<RuntimeAPIConfig> | null = null;

export function configureAPIClient(config: RuntimeAPIConfig | null) {
  configuredRuntime = config ? validateRuntimeConfig(config) : null;
  runtimePromise = null;
}

function validateRuntimeConfig(config: RuntimeAPIConfig): RuntimeAPIConfig {
  const url = new URL(config.apiBaseUrl);
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(url.hostname)) {
    throw new Error('Backend URL must use a loopback HTTP address');
  }
  if (!url.pathname.endsWith('/api')) {
    throw new Error('Backend URL must end in /api');
  }
  return { apiBaseUrl: url.toString().replace(/\/$/, ''), token: config.token || '' };
}

async function getRuntimeConfig(): Promise<RuntimeAPIConfig> {
  if (configuredRuntime) return configuredRuntime;
  if (runtimePromise) return runtimePromise;

  runtimePromise = (async () => {
    if (typeof window !== 'undefined') {
      const bridge = (window as Window & { electron?: ElectronRuntimeBridge }).electron;
      if (bridge?.getRuntimeConfig) {
        return validateRuntimeConfig(await bridge.getRuntimeConfig());
      }
    }

    const configuredUrl = process.env.NEXT_PUBLIC_POMOPET_BACKEND_URL;
    const host = typeof window !== 'undefined' && ['localhost', '127.0.0.1'].includes(window.location.hostname)
      ? window.location.hostname
      : '127.0.0.1';
    const backendUrl = (configuredUrl || `http://${host}:8000`).replace(/\/$/, '');
    return validateRuntimeConfig({
      apiBaseUrl: `${backendUrl}/api`,
      token: process.env.NEXT_PUBLIC_POMOPET_RUNTIME_TOKEN || '',
    });
  })();

  return runtimePromise;
}

export class APIError extends Error {
  status?: number;
  endpoint?: string;
  retries: number;
  errorCode?: string;
  requestId?: string;

  constructor(
    message: string,
    status?: number,
    endpoint?: string,
    retries = 0,
    errorCode?: string,
    requestId?: string,
  ) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.endpoint = endpoint;
    this.retries = retries;
    this.errorCode = errorCode;
    this.requestId = requestId;
  }
}

export function formatAPIError(error: unknown, fallback: string): string {
  if (!(error instanceof Error)) return fallback;
  if (!(error instanceof APIError)) return error.message;
  const code = error.errorCode ? ` [${error.errorCode}]` : '';
  const reference = error.requestId ? ` (ref: ${error.requestId})` : '';
  return `${error.message}${code}${reference}`;
}

type ErrorCallback = (error: APIError) => void;
let globalErrorCallback: ErrorCallback | null = null;

export function setErrorCallback(callback: ErrorCallback | null) {
  globalErrorCallback = callback;
}

function notifyError(error: APIError, method: string) {
  const reference = error.requestId ? ` [request_id=${error.requestId}]` : '';
  const logEntry = `[${new Date().toISOString()}] ${error.message}${reference} (${error.endpoint})`;
  if (typeof window !== 'undefined') {
    const existingEntries = (localStorage.getItem('api_error_log') || '').split('\n').filter(Boolean);
    localStorage.setItem('api_error_log', [logEntry, ...existingEntries].slice(0, 50).join('\n'));
  }
  console.error(logEntry);

  // Send to backend
  void getRuntimeConfig().then(config => fetch(`${config.apiBaseUrl}/logs/frontend`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(config.token ? { 'X-PomoPet-Token': config.token } : {}),
      },
      body: JSON.stringify({
        message: error.message,
        endpoint: error.endpoint,
        method,
        status: error.status,
        error_code: error.errorCode,
        request_id: error.requestId,
        retries: error.retries,
      }),
    })).catch(() => {});

  if (globalErrorCallback) {
    globalErrorCallback(error);
  }
}

async function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchAPIWithRetry(
  endpoint: string,
  options: RequestInit = {},
  retries = MAX_RETRIES,
  attempt = 0
): Promise<any> {
  const runtime = await getRuntimeConfig();
  const url = `${runtime.apiBaseUrl}${endpoint}`;
  const method = options.method || 'GET';

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
        ...(runtime.token ? { 'X-PomoPet-Token': runtime.token } : {}),
      },
    });

    if (!response.ok) {
      const body = typeof response.json === 'function'
        ? await response.json().catch(() => null)
        : null;
      const error = new APIError(
        body?.message || body?.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        endpoint,
        attempt,
        body?.error_code,
        body?.request_id,
      );

      if (response.status >= 500 && retries > 0) {
        await sleep(RETRY_DELAY_BASE * (2 ** attempt));
        return fetchAPIWithRetry(endpoint, options, retries - 1, attempt + 1);
      }

      notifyError(error, method);
      throw error;
    }

    return await response.json();
  } catch (error) {
    if (error instanceof APIError) {
      throw error;
    }

    const apiError = new APIError(
      error instanceof Error ? error.message : 'Unknown error',
      undefined,
      endpoint,
      attempt
    );

    if (retries > 0) {
      await sleep(RETRY_DELAY_BASE * (2 ** attempt));
      return fetchAPIWithRetry(endpoint, options, retries - 1, attempt + 1);
    }

    console.error(`API call failed after ${attempt} retries: ${endpoint}`, apiError);
    notifyError(apiError, method);
    throw apiError;
  }
}

async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  const retries = !options.method || options.method === 'GET' ? MAX_RETRIES : 0;
  return fetchAPIWithRetry(endpoint, options, retries);
}

export interface Task {
  id: string;
  name: string;
  priority: 'high' | 'medium' | 'low';
  deadline?: string;
  completed: boolean;
  estimatedDuration?: number;
  subtasks: { id: string; name: string; completed: boolean }[];
}

export type Importance = 'high' | 'medium' | 'low';
export type GoalStatus = 'active' | 'completed' | 'archived';
export type PlanHorizon = 'month' | 'week' | 'day';
export type PlanItemStatus = 'open' | 'completed' | 'dropped';

export interface Goal {
  id: string;
  title: string;
  definition_of_done: string;
  deadline: string;
  importance: Importance;
  status: GoalStatus;
  weekly_capacity_minutes: number;
  version: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface PlanItem {
  id: string;
  goal_id: string | null;
  parent_id: string | null;
  horizon: PlanHorizon;
  title: string;
  importance: Importance;
  deadline: string | null;
  planned_for: string | null;
  period_start: string | null;
  estimate_minutes: number | null;
  status: PlanItemStatus;
  version: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface PlanningProgress {
  goal_id: string | null;
  item_id: string | null;
  planned_minutes: number;
  actual_focus_minutes: number;
  focus_session_count: number;
  completed_daily_task_count: number;
  daily_task_count: number;
}

export interface PlannerInput {
  provider: AIProvider;
  current_state: string;
  weaknesses: string[];
  topics: string[];
  available_weekdays: number[];
  minutes_per_day: number;
  default_session_duration: number;
}

export interface DraftItem {
  client_id: string;
  parent_client_id: string | null;
  horizon: PlanHorizon;
  title: string;
  period_start: string | null;
  planned_for: string | null;
  estimate_minutes: number | null;
}

export interface PlanDraft {
  id: string;
  goal_id: string;
  goal_version: number;
  status: 'draft' | 'approved' | 'cancelled';
  input: PlannerInput;
  draft: { schema_version: 1; assumptions: string[]; items: DraftItem[] };
  capacity: {
    available_minutes: number;
    planning_limit_minutes: number;
    planned_minutes: number;
    over_capacity: boolean;
  };
  approval_result: { created_items: { client_id: string; id: string; horizon: PlanHorizon }[] } | null;
}

export interface Session {
  id: string;
  task_id: string;
  duration: number;
  initial_duration?: number;
  initial_duration_source?: 'selected' | 'legacy_total' | 'legacy_unknown';
  time_left: number;
  state: 'running' | 'paused' | 'completed' | 'cancelled';
  distraction_count: number;
  penalty_seconds: number;
  started_at: string | null;
}

export interface BehaviorActionContext {
  view?: 'inbox' | 'today' | 'week';
  rank?: number;
  visible_task_count?: number;
  sort_mode?: 'created_desc' | 'importance' | 'date_importance';
  timezone_offset?: number;
  duration_source?: 'selected' | 'explicit_preference' | 'habit_prefill' | 'task_estimate' | 'chat';
  suggested_duration_minutes?: number;
  suggested_rank?: number;
  suggested_task_id?: string;
}

export interface Statistics {
  focusHoursToday: number;
  focusHoursWeek: number;
  sessionsCompleted: number;
  distractionChain: number;
  distractionData: { time: string; distractions: number }[];
  totalDistractionsWeek: number;
}

export type AIProvider = 'openai' | 'gemini';
export type AIProviderStatus = Record<AIProvider, boolean>;

export interface PendingAction {
  id: string;
  type:
    | 'create_task'
    | 'create_tasks'
    | 'update_task'
    | 'delete_task'
    | 'start_focus_session'
    | 'pause_focus_session'
    | 'resume_focus_session'
    | 'extend_focus_session'
    | 'complete_task'
    | 'edit_plan'
    | 'update_goal'
    | 'delete_goal'
    | 'update_plan_item'
    | 'reschedule_plan_task'
    | 'create_daily_plan_task'
    | 'regenerate_week_plan';
  preview: string;
  expires_at: string;
}

export interface ChatResponse {
  status: 'completed' | 'confirmation_required' | 'cancelled';
  message: string;
  request_id: string;
  plan_changed?: boolean;
  pending_action_id?: string;
  action?: PendingAction;
}

export type ChatActionStatus = 'pending' | 'processing' | 'completed' | 'cancelled' | 'error';

export interface ChatMessageItem {
  role: 'user' | 'pet';
  text: string;
  action?: PendingAction;
  actionStatus?: ChatActionStatus;
  proactiveSuggestion?: {
    decisionId: string;
    target: 'plan';
  };
}

export const api = {
  // Task API
  async getTasks(): Promise<Task[]> {
    return fetchAPI('/tasks/');
  },

  async createTask(task: { name: string; priority: string; deadline?: string; estimated_duration?: number }): Promise<{ id: string }> {
    return fetchAPI('/tasks/', {
      method: 'POST',
      body: JSON.stringify(task),
    });
  },

  async updateTask(taskId: string, task: { name?: string; priority?: string; deadline?: string; estimated_duration?: number }): Promise<any> {
    return fetchAPI(`/tasks/${taskId}`, {
      method: 'PUT',
      body: JSON.stringify(task),
    });
  },

  async deleteTask(taskId: string): Promise<any> {
    return fetchAPI(`/tasks/${taskId}`, {
      method: 'DELETE',
    });
  },

  async completeTask(taskId: string): Promise<any> {
    return fetchAPI(`/tasks/${taskId}/complete`, {
      method: 'POST',
    });
  },

  async addSubtask(taskId: string, name: string): Promise<any> {
    return fetchAPI('/tasks/subtasks', {
      method: 'POST',
      body: JSON.stringify({ task_id: taskId, name }),
    });
  },

  async deleteSubtask(subtaskId: string): Promise<any> {
    return fetchAPI(`/tasks/subtasks/${subtaskId}`, {
      method: 'DELETE',
    });
  },

  // Planning API
  async getGoals(includeArchived = false): Promise<Goal[]> {
    return fetchAPI(`/planning/goals?include_archived=${includeArchived}`);
  },

  async createGoal(goal: {
    title: string;
    definition_of_done: string;
    deadline: string;
    importance: Importance;
    weekly_capacity_minutes: number;
  }): Promise<Goal> {
    return fetchAPI('/planning/goals', {
      method: 'POST',
      body: JSON.stringify(goal),
    });
  },

  async updateGoal(goalId: string, update: Partial<Pick<Goal,
    'title' | 'definition_of_done' | 'deadline' | 'importance' | 'weekly_capacity_minutes'
  >> & { expected_version?: number }): Promise<Goal> {
    return fetchAPI(`/planning/goals/${goalId}`, {
      method: 'PATCH',
      body: JSON.stringify(update),
    });
  },

  async archiveGoal(goalId: string, expectedVersion?: number): Promise<Goal> {
    return fetchAPI(`/planning/goals/${goalId}/archive`, {
      method: 'POST',
      body: JSON.stringify({ expected_version: expectedVersion }),
    });
  },

  async deleteGoal(goalId: string, expectedVersion?: number): Promise<{
    deleted_goal_id: string;
    deleted_structure_items: number;
    moved_to_inbox: number;
    retained_history_items: number;
  }> {
    return fetchAPI(`/planning/goals/${goalId}`, {
      method: 'DELETE',
      body: JSON.stringify({
        expected_version: expectedVersion,
        confirm_delete: true,
      }),
    });
  },

  async getPlanItems(filters: {
    goal_id?: string;
    horizon?: PlanHorizon;
    status?: PlanItemStatus;
    inbox?: boolean;
  } = {}): Promise<PlanItem[]> {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined) query.set(key, String(value));
    });
    const suffix = query.size ? `?${query.toString()}` : '';
    return fetchAPI(`/planning/plan-items${suffix}`);
  },

  async createPlanItem(item: {
    title: string;
    horizon: PlanHorizon;
    goal_id?: string | null;
    parent_id?: string | null;
    importance?: Importance;
    deadline?: string | null;
    planned_for?: string | null;
    period_start?: string | null;
    estimate_minutes?: number | null;
  }): Promise<PlanItem> {
    return fetchAPI('/planning/plan-items', {
      method: 'POST',
      body: JSON.stringify(item),
    });
  },

  async updatePlanItem(itemId: string, update: Partial<Pick<PlanItem,
    'title' | 'horizon' | 'goal_id' | 'parent_id' | 'importance' | 'deadline' |
    'planned_for' | 'period_start' | 'estimate_minutes'
  >> & { expected_version?: number }): Promise<PlanItem> {
    return fetchAPI(`/planning/plan-items/${itemId}`, {
      method: 'PATCH',
      body: JSON.stringify(update),
    });
  },

  async completePlanItem(itemId: string, expectedVersion?: number, actionContext?: BehaviorActionContext): Promise<PlanItem> {
    return fetchAPI(`/planning/plan-items/${itemId}/complete`, {
      method: 'POST',
      body: JSON.stringify({
        expected_version: expectedVersion,
        source: 'ui',
        idempotency_key: globalThis.crypto?.randomUUID?.() || `complete-${itemId}-${Date.now()}`,
        action_context: actionContext,
      }),
    });
  },

  async dropPlanItem(itemId: string, expectedVersion?: number): Promise<PlanItem> {
    return fetchAPI(`/planning/plan-items/${itemId}/drop`, {
      method: 'POST',
      body: JSON.stringify({ expected_version: expectedVersion }),
    });
  },

  async movePlanItemToInbox(itemId: string, expectedVersion?: number): Promise<PlanItem> {
    return fetchAPI(`/planning/plan-items/${itemId}/inbox`, {
      method: 'POST',
      body: JSON.stringify({ expected_version: expectedVersion }),
    });
  },

  async reschedulePlanItem(
    itemId: string,
    plannedFor: string,
    expectedVersion?: number,
  ): Promise<PlanItem> {
    return fetchAPI(`/planning/plan-items/${itemId}/reschedule`, {
      method: 'POST',
      body: JSON.stringify({ planned_for: plannedFor, expected_version: expectedVersion }),
    });
  },

  async getGoalProgress(goalId: string): Promise<PlanningProgress> {
    return fetchAPI(`/planning/goals/${goalId}/progress`);
  },

  async getPlanItemProgress(itemId: string): Promise<PlanningProgress> {
    return fetchAPI(`/planning/plan-items/${itemId}/progress`);
  },

  async generatePlanDraft(goalId: string, input: PlannerInput): Promise<PlanDraft> {
    return fetchAPI(`/planning/goals/${goalId}/drafts`, {
      method: 'POST',
      body: JSON.stringify(input),
    });
  },

  async updatePlanDraft(draftId: string, draft: PlanDraft['draft']): Promise<PlanDraft> {
    return fetchAPI(`/planning/drafts/${draftId}`, {
      method: 'PATCH',
      body: JSON.stringify({ draft }),
    });
  },

  async cancelPlanDraft(draftId: string): Promise<PlanDraft> {
    return fetchAPI(`/planning/drafts/${draftId}/cancel`, { method: 'POST' });
  },

  async regeneratePlanDraftBranch(
    draftId: string,
    clientId: string,
    draft: PlanDraft['draft'],
  ): Promise<PlanDraft> {
    return fetchAPI(`/planning/drafts/${draftId}/regenerate`, {
      method: 'POST',
      body: JSON.stringify({ client_id: clientId, draft }),
    });
  },

  async approvePlanDraft(
    draftId: string,
    draft: PlanDraft['draft'],
    idempotencyKey: string,
    overrideCapacity = false,
  ): Promise<PlanDraft> {
    return fetchAPI(`/planning/drafts/${draftId}/approve`, {
      method: 'POST',
      body: JSON.stringify({
        draft,
        idempotency_key: idempotencyKey,
        override_capacity: overrideCapacity,
      }),
    });
  },

  // Session API
  async startSession(taskId: string, duration: number, actionContext?: BehaviorActionContext): Promise<Session> {
    return fetchAPI('/sessions/start', {
      method: 'POST',
      body: JSON.stringify({
        task_id: taskId,
        duration,
        source: 'ui',
        idempotency_key: globalThis.crypto?.randomUUID?.() || `start-${taskId}-${Date.now()}`,
        action_context: actionContext,
      }),
    });
  },

  async pauseSession(): Promise<any> {
    return fetchAPI('/sessions/pause', {
      method: 'POST',
    });
  },

  async resumeSession(): Promise<any> {
    return fetchAPI('/sessions/resume', {
      method: 'POST',
    });
  },

  async cancelSession(): Promise<any> {
    return fetchAPI('/sessions/cancel', {
      method: 'POST',
    });
  },

  async completeSession(): Promise<any> {
    return fetchAPI('/sessions/complete', {
      method: 'POST',
    });
  },

async extendSession(minutes: number): Promise<any> {
     return fetchAPI(`/sessions/extend`, {
       method: 'POST',
       body: JSON.stringify({
         minutes,
         source: 'ui',
         idempotency_key: globalThis.crypto?.randomUUID?.() || `extend-${Date.now()}`,
       }),
     });
   },

  async addDistraction(): Promise<any> {
    return fetchAPI('/sessions/distraction', {
      method: 'POST',
    });
  },

  async updateTimeLeft(timeLeft: number): Promise<any> {
    return fetchAPI('/sessions/update-time', {
      method: 'POST',
      body: JSON.stringify({ time_left: timeLeft }),
    });
  },

  async getCurrentSession(): Promise<Session | null> {
    return fetchAPI('/sessions/current');
  },

  // Statistics API
  async getStatistics(): Promise<Statistics> {
    const timezoneOffset = -new Date().getTimezoneOffset();
    return fetchAPI(`/statistics/?timezone_offset=${timezoneOffset}`);
  },

  async getDailyStatistics(): Promise<any> {
    const timezoneOffset = -new Date().getTimezoneOffset();
    return fetchAPI(`/statistics/daily?timezone_offset=${timezoneOffset}`);
  },

  async getWeeklyStatistics(): Promise<any> {
    const timezoneOffset = -new Date().getTimezoneOffset();
    return fetchAPI(`/statistics/weekly?timezone_offset=${timezoneOffset}`);
  },

  async getDistractionStatistics(): Promise<any> {
    const timezoneOffset = -new Date().getTimezoneOffset();
    return fetchAPI(`/statistics/distractions?timezone_offset=${timezoneOffset}`);
  },

  async sendChat(
    message: string,
    provider: AIProvider,
    threadId: string,
    timezoneOffset: number,
  ): Promise<ChatResponse> {
    return fetchAPI('/chat/', {
      method: 'POST',
      body: JSON.stringify({
        message,
        provider,
        thread_id: threadId,
        timezone_offset: timezoneOffset,
      }),
    });
  },

  async confirmChatAction(actionId: string, threadId: string): Promise<ChatResponse> {
    return fetchAPI(`/chat/actions/${actionId}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ thread_id: threadId }),
    });
  },

  async cancelChatAction(actionId: string, threadId: string): Promise<ChatResponse> {
    return fetchAPI(`/chat/actions/${actionId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ thread_id: threadId }),
    });
  },

  async getAIProviders(): Promise<AIProviderStatus> {
    return fetchAPI('/chat/providers');
  },

  async configureAIProvider(provider: AIProvider, apiKey: string): Promise<void> {
    await fetchAPI(`/chat/providers/${provider}/key`, {
      method: 'PUT',
      body: JSON.stringify({ api_key: apiKey }),
    });
  },

  async getRelationshipProfile(): Promise<UserProfile> {
    return fetchAPI('/relationship/profile');
  },

  async updateRelationshipProfile(
    update: Partial<Pick<UserProfile,
      | 'personalization_on'
      | 'memory_prompts_on'
      | 'relationship_context_on'
      | 'proactive_enabled'
      | 'proactive_jokes_on'
      | 'proactive_planning_on'
    >>,
  ): Promise<UserProfile> {
    return fetchAPI('/relationship/profile', {
      method: 'PATCH',
      body: JSON.stringify(update),
    });
  },

  async evaluateProactive(input: ProactiveEvaluateInput): Promise<ProactiveDecision> {
    return fetchAPI('/proactive/evaluate', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  },

  async markProactiveExecuted(decisionId: string): Promise<ProactiveDecision> {
    return fetchAPI(`/proactive/decisions/${decisionId}/executed`, { method: 'POST' });
  },

  async getProactiveRuns(limit = 20): Promise<ProactiveDecision[]> {
    return fetchAPI(`/proactive/runs?limit=${limit}`);
  },

  async getProactiveRun(decisionId: string): Promise<ProactiveRun> {
    return fetchAPI(`/proactive/runs/${encodeURIComponent(decisionId)}`);
  },

  async getRelationshipMemories(): Promise<PersonalMemory[]> {
    return fetchAPI('/relationship/memories');
  },

  async getRelationshipHabits(): Promise<HabitProfile[]> {
    return fetchAPI('/relationship/habits');
  },

  async dismissRelationshipHabit(habitId: string): Promise<void> {
    await fetchAPI(`/relationship/habits/${habitId}`, { method: 'DELETE' });
  },

  async getRelationshipEpisodes(): Promise<RelationshipEpisode[]> {
    return fetchAPI('/relationship/episodes');
  },

  async updateRelationshipEpisode(
    episodeId: string,
    action: RelationshipMemoryAction,
  ): Promise<void> {
    await fetchAPI(`/relationship/episodes/${episodeId}`, {
      method: 'DELETE',
      body: JSON.stringify({ action }),
    });
  },

  async getRelationshipRituals(): Promise<SharedRitual[]> {
    return fetchAPI('/relationship/rituals');
  },

  async updateRelationshipRitual(
    ritualId: string,
    action: RelationshipMemoryAction,
  ): Promise<void> {
    await fetchAPI(`/relationship/rituals/${ritualId}`, {
      method: 'DELETE',
      body: JSON.stringify({ action }),
    });
  },

  async getRelationalState(): Promise<RelationalState> {
    return fetchAPI('/relationship/relational-state');
  },

  async getFocusSuggestion(
    view: 'inbox' | 'today' | 'week',
    context: { taskId?: string; goalId?: string } = {},
  ): Promise<FocusSuggestion> {
    const timezoneOffset = -new Date().getTimezoneOffset();
    const query = new URLSearchParams({ view, timezone_offset: String(timezoneOffset) });
    if (context.taskId) query.set('task_id', context.taskId);
    if (context.goalId) query.set('goal_id', context.goalId);
    return fetchAPI(`/relationship/focus-suggestion?${query.toString()}`);
  },

  async updateRelationshipMemory(memoryId: string, value: string | number): Promise<PersonalMemory> {
    return fetchAPI(`/relationship/memories/${memoryId}`, {
      method: 'PATCH',
      body: JSON.stringify({ value }),
    });
  },

  async deleteRelationshipMemory(
    memoryId: string,
    action: 'deleted' | 'never_mention' | 'deactivated' = 'deleted',
  ): Promise<void> {
    await fetchAPI(`/relationship/memories/${memoryId}`, {
      method: 'DELETE',
      body: JSON.stringify({ action }),
    });
  },

  async deleteRelationshipData(): Promise<void> {
    await fetchAPI('/relationship/data', { method: 'DELETE' });
  },
};
