'use client';

import {
  Archive,
  CalendarDays,
  Check,
  ChevronRight,
  Clock3,
  Inbox,
  ListTodo,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';

import {
  api,
  AIProvider,
  BehaviorActionContext,
  DraftItem,
  formatAPIError,
  Goal,
  Importance,
  PlanDraft,
  PlanItem,
  PlanningProgress,
  Task,
} from '@/lib/api';
import type { FocusSuggestion } from '@/lib/relationship-types';
import type { SessionState } from './FloatingPet';


type PlanView = 'inbox' | 'today' | 'week' | 'month';

interface PlanPanelProps {
  petName: string;
  sessionState: SessionState;
  onStartSession: (task: Task, durationMinutes: number, context?: BehaviorActionContext) => void;
  onTasksChanged?: () => Promise<void> | void;
  provider: AIProvider;
  refreshToken?: number;
}

const importanceRank: Record<Importance, number> = { high: 0, medium: 1, low: 2 };

function localDate(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function mondayOf(date: Date): Date {
  const result = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const day = result.getDay() || 7;
  result.setDate(result.getDate() - day + 1);
  return result;
}

function addDays(date: Date, days: number): Date {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

function asLegacyTask(item: PlanItem): Task {
  return {
    id: item.id,
    name: item.title,
    priority: item.importance,
    deadline: item.deadline || item.planned_for || undefined,
    completed: item.status === 'completed',
    estimatedDuration: item.estimate_minutes || undefined,
    subtasks: [],
  };
}

function importanceColor(importance: Importance): string {
  if (importance === 'high') return 'bg-red-300';
  if (importance === 'low') return 'bg-green-300';
  return 'bg-amber-300';
}

export default function PlanPanel({
  petName,
  sessionState,
  onStartSession,
  onTasksChanged,
  provider,
  refreshToken = 0,
}: PlanPanelProps) {
  const [view, setView] = useState<PlanView>('inbox');
  const [goals, setGoals] = useState<Goal[]>([]);
  const [items, setItems] = useState<PlanItem[]>([]);
  const [progress, setProgress] = useState<Record<string, PlanningProgress>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [focusSuggestion, setFocusSuggestion] = useState<FocusSuggestion>({ duration: null, task_rank: null });
  const [focusDraft, setFocusDraft] = useState<{
    item: PlanItem;
    minutes: number;
    rank: number;
    visibleCount: number;
    view: 'today' | 'week';
    sortMode: 'importance' | 'date_importance';
    suggestion: FocusSuggestion;
  } | null>(null);

  const [inboxTitle, setInboxTitle] = useState('');
  const [inboxImportance, setInboxImportance] = useState<Importance>('medium');
  const [inboxEstimate, setInboxEstimate] = useState(25);
  const [inboxGoalId, setInboxGoalId] = useState('');
  const [assigningId, setAssigningId] = useState<string | null>(null);
  const [assignGoalId, setAssignGoalId] = useState('');
  const [assignWeekId, setAssignWeekId] = useState('');
  const [assignDate, setAssignDate] = useState(localDate());
  const [rescheduleDates, setRescheduleDates] = useState<Record<string, string>>({});

  const [showGoalForm, setShowGoalForm] = useState(false);
  const [goalTitle, setGoalTitle] = useState('');
  const [goalDone, setGoalDone] = useState('');
  const [goalDeadline, setGoalDeadline] = useState('');
  const [goalImportance, setGoalImportance] = useState<Importance>('medium');
  const [goalCapacity, setGoalCapacity] = useState(300);
  const [editingGoalId, setEditingGoalId] = useState<string | null>(null);
  const [editGoalTitle, setEditGoalTitle] = useState('');
  const [editGoalDone, setEditGoalDone] = useState('');
  const [editGoalDeadline, setEditGoalDeadline] = useState('');
  const [editGoalImportance, setEditGoalImportance] = useState<Importance>('medium');
  const [editGoalCapacity, setEditGoalCapacity] = useState(0);

  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [editItemTitle, setEditItemTitle] = useState('');
  const [editItemPeriod, setEditItemPeriod] = useState('');
  const [editItemImportance, setEditItemImportance] = useState<Importance>('medium');
  const [aiGoalId, setAiGoalId] = useState<string | null>(null);
  const [aiDraft, setAiDraft] = useState<PlanDraft | null>(null);
  const [aiCurrentState, setAiCurrentState] = useState('');
  const [aiWeaknesses, setAiWeaknesses] = useState('');
  const [aiTopics, setAiTopics] = useState('');
  const [aiWeekdays, setAiWeekdays] = useState([0, 1, 2, 3, 4]);
  const [aiMinutesPerDay, setAiMinutesPerDay] = useState(60);
  const [aiSessionDuration, setAiSessionDuration] = useState(25);
  const [capacityOverride, setCapacityOverride] = useState(false);
  const [approvalKey, setApprovalKey] = useState('');
  const [draftDayTitle, setDraftDayTitle] = useState('');
  const [draftDayParent, setDraftDayParent] = useState('');
  const [draftDayDate, setDraftDayDate] = useState(localDate());

  const [milestoneTitle, setMilestoneTitle] = useState('');
  const [milestoneGoalId, setMilestoneGoalId] = useState('');
  const [milestoneMonth, setMilestoneMonth] = useState(localDate().slice(0, 7));

  const [outcomeTitle, setOutcomeTitle] = useState('');
  const [outcomeMonthId, setOutcomeMonthId] = useState('');
  const [outcomeStart, setOutcomeStart] = useState(localDate(mondayOf(new Date())));

  const [dailyTitle, setDailyTitle] = useState('');
  const [dailyWeekId, setDailyWeekId] = useState('');
  const [dailyDate, setDailyDate] = useState(localDate());
  const [dailyEstimate, setDailyEstimate] = useState(25);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [loadedGoals, loadedItems] = await Promise.all([
        api.getGoals(),
        api.getPlanItems({ status: 'open' }),
      ]);
      const activeGoalIds = new Set(loadedGoals.map(goal => goal.id));
      const visibleItems = loadedItems.filter(
        item => !item.goal_id || activeGoalIds.has(item.goal_id),
      );
      const progressEntries = await Promise.all(
        loadedGoals.map(async goal => [goal.id, await api.getGoalProgress(goal.id)] as const),
      );
      setGoals(loadedGoals);
      setItems(visibleItems);
      setProgress(Object.fromEntries(progressEntries));
      setError(null);
    } catch (cause) {
      setError(formatAPIError(cause, 'Could not load the plan'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshToken]);

  useEffect(() => {
    if (view !== 'today' && view !== 'week') return;
    let active = true;
    api.getFocusSuggestion(view).then(suggestion => {
      if (active) setFocusSuggestion(suggestion);
    }).catch(() => {
      if (active) setFocusSuggestion({ duration: null, task_rank: null });
    });
    return () => { active = false; };
  }, [view, items.length, sessionState]);

  const run = async (id: string, action: () => Promise<unknown>): Promise<boolean> => {
    setBusyId(id);
    setError(null);
    try {
      await action();
      await refresh();
      return true;
    } catch (cause) {
      setError(formatAPIError(cause, 'Planning action failed'));
      return false;
    } finally {
      setBusyId(null);
    }
  };

  const monthItems = useMemo(
    () => items.filter(item => item.horizon === 'month'),
    [items],
  );
  const weekItems = useMemo(
    () => items.filter(item => item.horizon === 'week'),
    [items],
  );
  const inboxItems = useMemo(
    () => items.filter(item => item.horizon === 'day' && !item.planned_for),
    [items],
  );
  const today = localDate();
  const todayItems = useMemo(
    () => items
      .filter(item => item.horizon === 'day' && item.planned_for === today)
      .sort((a, b) => importanceRank[a.importance] - importanceRank[b.importance]),
    [items, today],
  );
  const weekStartDate = mondayOf(new Date());
  const weekDates = Array.from({ length: 7 }, (_, index) => localDate(addDays(weekStartDate, index)));
  const weekEnd = weekDates[6];
  const currentWeekOutcomes = weekItems.filter(
    item => item.period_start && item.period_start >= weekDates[0] && item.period_start <= weekEnd,
  );
  const draftPlannedMinutes = aiDraft?.draft.items.reduce(
    (total, item) => total + (item.horizon === 'day' ? item.estimate_minutes || 0 : 0),
    0,
  ) || 0;
  const draftOverCapacity = Boolean(
    aiDraft && draftPlannedMinutes > aiDraft.capacity.planning_limit_minutes,
  );
  const draftDayCount = aiDraft?.draft.items.filter(item => item.horizon === 'day').length || 0;

  const goalName = (goalId: string | null) =>
    goals.find(goal => goal.id === goalId)?.title || 'No goal';

  const parentName = (parentId: string | null) =>
    items.find(item => item.id === parentId)?.title || '';

  const createInboxItem = async (event: FormEvent) => {
    event.preventDefault();
    if (!inboxTitle.trim()) return;
    await run('new-inbox', () => api.createPlanItem({
      title: inboxTitle.trim(),
      horizon: 'day',
      goal_id: inboxGoalId || undefined,
      importance: inboxImportance,
      estimate_minutes: inboxEstimate,
    }));
    setInboxTitle('');
  };

  const createGoal = async (event: FormEvent) => {
    event.preventDefault();
    if (!goalTitle.trim() || !goalDone.trim() || !goalDeadline) return;
    await run('new-goal', () => api.createGoal({
      title: goalTitle.trim(),
      definition_of_done: goalDone.trim(),
      deadline: goalDeadline,
      importance: goalImportance,
      weekly_capacity_minutes: goalCapacity,
    }));
    setGoalTitle('');
    setGoalDone('');
    setGoalDeadline('');
    setShowGoalForm(false);
  };

  const beginGoalEdit = (goal: Goal) => {
    setEditingGoalId(goal.id);
    setEditGoalTitle(goal.title);
    setEditGoalDone(goal.definition_of_done);
    setEditGoalDeadline(goal.deadline);
    setEditGoalImportance(goal.importance);
    setEditGoalCapacity(goal.weekly_capacity_minutes);
  };

  const saveGoalEdit = async (event: FormEvent, goal: Goal) => {
    event.preventDefault();
    if (!editGoalTitle.trim() || !editGoalDone.trim() || !editGoalDeadline) return;
    const saved = await run(`edit-goal-${goal.id}`, () => api.updateGoal(goal.id, {
      title: editGoalTitle.trim(),
      definition_of_done: editGoalDone.trim(),
      deadline: editGoalDeadline,
      importance: editGoalImportance,
      weekly_capacity_minutes: editGoalCapacity,
      expected_version: goal.version,
    }));
    if (saved) setEditingGoalId(null);
  };

  const beginPlanItemEdit = (item: PlanItem) => {
    setEditingItemId(item.id);
    setEditItemTitle(item.title);
    setEditItemPeriod(
      item.horizon === 'month'
        ? item.period_start?.slice(0, 7) || ''
        : item.period_start || '',
    );
    setEditItemImportance(item.importance);
  };

  const savePlanItemEdit = async (event: FormEvent, item: PlanItem) => {
    event.preventDefault();
    if (!editItemTitle.trim() || !editItemPeriod) return;
    const periodStart = item.horizon === 'month'
      ? `${editItemPeriod}-01`
      : editItemPeriod;
    const saved = await run(`edit-item-${item.id}`, () => api.updatePlanItem(item.id, {
      title: editItemTitle.trim(),
      period_start: periodStart,
      importance: editItemImportance,
      expected_version: item.version,
    }));
    if (saved) setEditingItemId(null);
  };

  const renderPlanItemEditor = (item: PlanItem) => (
    <form
      onSubmit={event => void savePlanItemEdit(event, item)}
      className="mt-1 space-y-1 border-2 border-black bg-white p-1"
    >
      <input
        value={editItemTitle}
        onChange={event => setEditItemTitle(event.target.value)}
        className="w-full border-2 border-black px-1 py-1 text-[9px] font-bold"
      />
      <div className="grid grid-cols-2 gap-1">
        <input
          type={item.horizon === 'month' ? 'month' : 'date'}
          value={editItemPeriod}
          onChange={event => setEditItemPeriod(event.target.value)}
          className="border-2 border-black px-1 text-[8px] font-bold"
        />
        <select
          value={editItemImportance}
          onChange={event => setEditItemImportance(event.target.value as Importance)}
          className="border-2 border-black px-1 text-[8px] font-bold uppercase"
        >
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>
      <div className="grid grid-cols-2 gap-1">
        <button
          type="button"
          onClick={() => setEditingItemId(null)}
          className="border-2 border-black bg-gray-100 py-1 text-[8px] font-black"
        >
          CANCEL
        </button>
        <button
          disabled={!editItemTitle.trim() || !editItemPeriod || busyId === `edit-item-${item.id}`}
          className="border-2 border-black bg-green-300 py-1 text-[8px] font-black disabled:opacity-40"
        >
          SAVE
        </button>
      </div>
    </form>
  );

  const generateDraft = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!aiGoalId || aiWeekdays.length === 0) return;
    setBusyId('ai-draft');
    setError(null);
    try {
      if (aiDraft?.status === 'draft') {
        await api.cancelPlanDraft(aiDraft.id);
      }
      const draft = await api.generatePlanDraft(aiGoalId, {
        provider,
        current_state: aiCurrentState,
        weaknesses: aiWeaknesses.split(',').map(value => value.trim()).filter(Boolean),
        topics: aiTopics.split(',').map(value => value.trim()).filter(Boolean),
        available_weekdays: aiWeekdays,
        minutes_per_day: aiMinutesPerDay,
        default_session_duration: aiSessionDuration,
      });
      setAiDraft(draft);
      setApprovalKey(globalThis.crypto?.randomUUID?.() || `approval-${Date.now()}`);
      setCapacityOverride(false);
    } catch (cause) {
      setError(formatAPIError(cause, 'AI planning failed'));
    } finally {
      setBusyId(null);
    }
  };

  const updateDraftItem = (clientId: string, update: Partial<DraftItem>) => {
    setAiDraft(current => current ? {
      ...current,
      draft: {
        ...current.draft,
        items: current.draft.items.map(item => item.client_id === clientId ? { ...item, ...update } : item),
      },
    } : current);
  };

  const removeDraftBranch = (clientId: string) => {
    setAiDraft(current => {
      if (!current) return current;
      const removed = new Set([clientId]);
      let changed = true;
      while (changed) {
        changed = false;
        current.draft.items.forEach(item => {
          if (item.parent_client_id && removed.has(item.parent_client_id) && !removed.has(item.client_id)) {
            removed.add(item.client_id);
            changed = true;
          }
        });
      }
      return {
        ...current,
        draft: { ...current.draft, items: current.draft.items.filter(item => !removed.has(item.client_id)) },
      };
    });
  };

  const addDraftDay = () => {
    if (!aiDraft || !draftDayTitle.trim() || !draftDayParent || !draftDayDate) return;
    const item: DraftItem = {
      client_id: `day-${Date.now()}`,
      parent_client_id: draftDayParent,
      horizon: 'day',
      title: draftDayTitle.trim(),
      period_start: null,
      planned_for: draftDayDate,
      estimate_minutes: aiSessionDuration,
    };
    setAiDraft({ ...aiDraft, draft: { ...aiDraft.draft, items: [...aiDraft.draft.items, item] } });
    setDraftDayTitle('');
  };

  const cancelDraft = async () => {
    if (aiDraft) await run('ai-cancel', () => api.cancelPlanDraft(aiDraft.id));
    setAiDraft(null);
    setAiGoalId(null);
  };

  const regenerateDraftBranch = async (clientId: string) => {
    if (!aiDraft) return;
    const operationId = `ai-regen-${clientId}`;
    setBusyId(operationId);
    setError(null);
    try {
      const regenerated = await api.regeneratePlanDraftBranch(
        aiDraft.id,
        clientId,
        aiDraft.draft,
      );
      setAiDraft(regenerated);
      setCapacityOverride(false);
    } catch (cause) {
      setError(formatAPIError(cause, 'Branch regeneration failed'));
    } finally {
      setBusyId(null);
    }
  };

  const approveDraft = async () => {
    if (!aiDraft || !approvalKey) return;
    setBusyId('ai-approve');
    setError(null);
    try {
      await api.updatePlanDraft(aiDraft.id, aiDraft.draft);
      await api.approvePlanDraft(aiDraft.id, aiDraft.draft, approvalKey, capacityOverride);
      setAiDraft(null);
      setAiGoalId(null);
      await refresh();
      await onTasksChanged?.();
      setView('week');
      setNotice(`${draftDayCount} daily task${draftDayCount === 1 ? '' : 's'} added to your plan.`);
    } catch (cause) {
      setError(formatAPIError(cause, 'Draft approval failed'));
    } finally {
      setBusyId(null);
    }
  };

  const createMilestone = async (event: FormEvent) => {
    event.preventDefault();
    if (!milestoneTitle.trim() || !milestoneGoalId || !milestoneMonth) return;
    await run('new-milestone', () => api.createPlanItem({
      title: milestoneTitle.trim(),
      horizon: 'month',
      goal_id: milestoneGoalId,
      period_start: `${milestoneMonth}-01`,
    }));
    setMilestoneTitle('');
  };

  const createOutcome = async (event: FormEvent) => {
    event.preventDefault();
    const parent = monthItems.find(item => item.id === outcomeMonthId);
    if (!outcomeTitle.trim() || !parent || !outcomeStart) return;
    await run('new-outcome', () => api.createPlanItem({
      title: outcomeTitle.trim(),
      horizon: 'week',
      goal_id: parent.goal_id,
      parent_id: parent.id,
      period_start: outcomeStart,
    }));
    setOutcomeTitle('');
  };

  const createDailyTask = async (event: FormEvent) => {
    event.preventDefault();
    const parent = weekItems.find(item => item.id === dailyWeekId);
    if (!dailyTitle.trim() || !parent || !dailyDate) return;
    await run('new-daily', () => api.createPlanItem({
      title: dailyTitle.trim(),
      horizon: 'day',
      goal_id: parent.goal_id,
      parent_id: parent.id,
      planned_for: dailyDate,
      estimate_minutes: dailyEstimate,
    }));
    setDailyTitle('');
  };

  const assignInboxItem = async (item: PlanItem) => {
    if (!assignDate) return;
    const week = weekItems.find(candidate => candidate.id === assignWeekId);
    if (assignGoalId && week?.goal_id === assignGoalId) {
      await run(item.id, () => api.updatePlanItem(item.id, {
        goal_id: assignGoalId,
        parent_id: week.id,
        planned_for: assignDate,
        expected_version: item.version,
      }));
    } else if (assignGoalId) {
      setError('Choose a weekly outcome before scheduling a goal-linked task.');
      return;
    } else if (item.goal_id) {
      await run(item.id, () => api.updatePlanItem(item.id, {
        goal_id: null,
        parent_id: null,
        planned_for: assignDate,
        expected_version: item.version,
      }));
    } else {
      await run(item.id, () => api.reschedulePlanItem(item.id, assignDate, item.version));
    }
    setAssigningId(null);
    setAssignGoalId('');
    setAssignWeekId('');
  };

  const openFocusDraft = async (
    item: PlanItem,
    rank: number,
    visibleCount: number,
    selectedView: 'today' | 'week',
    sortMode: 'importance' | 'date_importance',
  ) => {
    let suggestion = focusSuggestion;
    try {
      suggestion = await api.getFocusSuggestion(selectedView, {
        taskId: item.id,
        goalId: item.goal_id || undefined,
      });
      setFocusSuggestion(suggestion);
    } catch {
      // Starting focus remains available without personalization.
    }
    const duration = suggestion.duration;
    const minutes = duration?.mode === 'prefill'
      ? duration.minutes
      : item.estimate_minutes || 25;
    setFocusDraft({ item, minutes, rank, visibleCount, view: selectedView, sortMode, suggestion });
  };

  const confirmFocusDraft = () => {
    if (!focusDraft || focusDraft.minutes < 1 || focusDraft.minutes > 240) return;
    const suggestedDuration = focusDraft.suggestion.duration;
    const suggestedRank = focusDraft.suggestion.task_rank;
    let durationSource: BehaviorActionContext['duration_source'] = 'selected';
    if (suggestedDuration && focusDraft.minutes === suggestedDuration.minutes) {
      durationSource = suggestedDuration.source === 'explicit_preference'
        ? 'explicit_preference'
        : 'habit_prefill';
    } else if (!suggestedDuration && focusDraft.minutes === (focusDraft.item.estimate_minutes || 25)) {
      durationSource = 'task_estimate';
    }
    onStartSession(asLegacyTask(focusDraft.item), focusDraft.minutes, {
      view: focusDraft.view,
      rank: focusDraft.rank,
      visible_task_count: focusDraft.visibleCount,
      sort_mode: focusDraft.sortMode,
      timezone_offset: -new Date().getTimezoneOffset(),
      duration_source: durationSource,
      suggested_duration_minutes: suggestedDuration?.minutes,
      suggested_rank: suggestedRank?.rank,
      suggested_task_id: suggestedRank?.rank === focusDraft.rank ? focusDraft.item.id : undefined,
    });
    setFocusDraft(null);
  };

  const renderDailyTask = (
    item: PlanItem,
    rank: number,
    visibleCount: number,
    selectedView: 'today' | 'week',
    sortMode: 'importance' | 'date_importance',
  ) => {
    const suggested = focusSuggestion.task_rank?.rank === rank;
    const main = selectedView === 'today' && rank === 0;
    const selectedDate = rescheduleDates[item.id] || item.planned_for || today;
    return (
      <div
        key={item.id}
        className={`border-[3px] border-black p-2 shadow-[2px_2px_0_#000] ${suggested || main ? 'bg-cyan-100' : 'bg-white'}`}
      >
        {(suggested || main) && (
          <div className="mb-1 text-[9px] font-black uppercase text-cyan-700">
            {suggested ? `Suggested task · ${focusSuggestion.task_rank?.explanation}` : 'Main task'}
          </div>
        )}
        <div className="flex items-start gap-2">
          <div className={`mt-1 h-3 w-3 shrink-0 border-2 border-black ${importanceColor(item.importance)}`} />
          <div className="min-w-0 flex-1">
            <div className="break-words text-xs font-black text-black">{item.title}</div>
            <div className="mt-1 text-[9px] font-bold uppercase text-gray-500">
              {goalName(item.goal_id)}
              {item.parent_id ? ` › ${parentName(item.parent_id)}` : ''}
            </div>
            <div className="mt-1 flex flex-wrap gap-1 text-[9px] font-black">
              <span className="border border-black bg-gray-100 px-1">{item.estimate_minutes || 25} MIN</span>
              {item.planned_for && <span className="border border-black bg-yellow-100 px-1">{item.planned_for}</span>}
            </div>
          </div>
          <button
            type="button"
            disabled={sessionState !== 'idle' || busyId === item.id}
            onClick={() => void openFocusDraft(item, rank, visibleCount, selectedView, sortMode)}
            className="border-2 border-black bg-cyan-400 p-1 disabled:opacity-40"
            title="Start focus"
          >
            <Play className="h-3 w-3" />
          </button>
          <button
            type="button"
            disabled={busyId === item.id}
            onClick={() => void run(item.id, () => api.completePlanItem(item.id, item.version, {
              view: selectedView,
              rank,
              visible_task_count: visibleCount,
              sort_mode: sortMode,
              timezone_offset: -new Date().getTimezoneOffset(),
            }))}
            className="border-2 border-black bg-green-300 p-1 disabled:opacity-40"
            title="Complete task"
          >
            <Check className="h-3 w-3" />
          </button>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1 border-t-2 border-dashed border-gray-300 pt-2">
          <input
            type="date"
            value={selectedDate}
            onChange={event => setRescheduleDates(current => ({
              ...current,
              [item.id]: event.target.value,
            }))}
            className="min-w-0 flex-1 border-2 border-black bg-gray-50 px-1 py-0.5 text-[9px] font-bold"
          />
          <button
            type="button"
            disabled={busyId === item.id || selectedDate === item.planned_for}
            onClick={() => void run(item.id, () => api.reschedulePlanItem(item.id, selectedDate, item.version))}
            className="border-2 border-black bg-yellow-200 p-1 disabled:opacity-30"
            title="Reschedule"
          >
            <CalendarDays className="h-3 w-3" />
          </button>
          <button
            type="button"
            disabled={busyId === item.id}
            onClick={() => void run(item.id, () => api.movePlanItemToInbox(item.id, item.version))}
            className="border-2 border-black bg-white p-1 disabled:opacity-30"
            title="Back to inbox"
          >
            <Inbox className="h-3 w-3" />
          </button>
          <button
            type="button"
            disabled={busyId === item.id}
            onClick={() => {
              if (window.confirm(`Drop “${item.title}”? Focus history will be kept.`)) {
                void run(item.id, () => api.dropPlanItem(item.id, item.version));
              }
            }}
            className="border-2 border-black bg-red-300 p-1 disabled:opacity-30"
            title="Drop task"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="absolute inset-0 flex flex-col bg-gray-100 font-mono">
      <div className="grid grid-cols-4 border-b-[3px] border-black bg-white">
        {([
          ['inbox', Inbox, 'Inbox'],
          ['today', ListTodo, 'Today'],
          ['week', CalendarDays, 'Week'],
          ['month', Clock3, 'Month'],
        ] as const).map(([id, Icon, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setView(id)}
            className={`flex items-center justify-center gap-1 border-r-2 border-black py-2 text-[9px] font-black uppercase last:border-r-0 ${
              view === id ? 'bg-yellow-300' : 'bg-white hover:bg-gray-100'
            }`}
          >
            <Icon className="h-3 w-3" /> {label}
          </button>
        ))}
      </div>

      {error && (
        <div role="alert" className="flex items-center gap-2 border-b-2 border-black bg-red-100 px-3 py-2 text-[10px] font-bold text-red-700">
          <span className="min-w-0 flex-1 break-words">{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="shrink-0 border-2 border-red-700 bg-white p-0.5 text-red-700 hover:bg-red-200"
            aria-label="Dismiss error"
            title="Dismiss error"
          >
            <X className="h-3 w-3" strokeWidth={3} />
          </button>
        </div>
      )}
      {notice && (
        <button
          type="button"
          onClick={() => setNotice(null)}
          className="border-b-2 border-black bg-green-200 px-3 py-2 text-left text-[10px] font-black text-green-900"
        >
          {notice} · CLICK TO DISMISS
        </button>
      )}

      {focusDraft && (
        <div className="border-b-[3px] border-black bg-cyan-50 p-3">
          <div className="text-[10px] font-black uppercase">Start focus · {focusDraft.item.title}</div>
          {focusDraft.suggestion.duration && (
            <div className="mt-1 text-[8px] font-bold text-cyan-800">
              {focusDraft.suggestion.duration.explanation}: {focusDraft.suggestion.duration.minutes} min
              {focusDraft.suggestion.duration.mode === 'suggestion' ? ' (optional suggestion)' : ''}
            </div>
          )}
          <div className="mt-2 flex gap-2">
            <input
              aria-label="Focus duration in minutes"
              type="number"
              min={1}
              max={240}
              value={focusDraft.minutes}
              onChange={event => setFocusDraft(current => current ? { ...current, minutes: Number(event.target.value) } : current)}
              className="min-w-0 flex-1 border-2 border-black px-2 py-1 text-xs font-black"
            />
            {focusDraft.suggestion.duration?.mode === 'suggestion' && focusDraft.minutes !== focusDraft.suggestion.duration.minutes && (
              <button type="button" onClick={() => setFocusDraft(current => current ? { ...current, minutes: current.suggestion.duration?.minutes || current.minutes } : current)} className="border-2 border-black bg-yellow-200 px-2 text-[8px] font-black">USE SUGGESTION</button>
            )}
            <button type="button" onClick={() => setFocusDraft(null)} className="border-2 border-black bg-white px-2 text-[8px] font-black">CANCEL</button>
            <button type="button" onClick={confirmFocusDraft} disabled={focusDraft.minutes < 1 || focusDraft.minutes > 240} className="border-2 border-black bg-cyan-400 px-3 text-[8px] font-black disabled:opacity-40">START</button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-3 scrollbar-thin scrollbar-thumb-black">
        {loading ? (
          <div className="flex h-full items-center justify-center text-xs font-black uppercase text-gray-500">
            Loading plan…
          </div>
        ) : (
          <>
            {view === 'inbox' && (
              <div className="space-y-3">
                <div>
                  <h4 className="text-sm font-black uppercase">Inbox</h4>
                  <p className="text-[9px] font-bold text-gray-500">Unscheduled actions. Nothing moves automatically.</p>
                </div>
                {inboxItems.length === 0 ? (
                  <div className="border-2 border-dashed border-gray-400 p-5 text-center text-[10px] font-bold text-gray-500">
                    INBOX ZERO. {petName.toUpperCase()} APPROVES.
                  </div>
                ) : inboxItems.map(item => (
                  <div key={item.id} className="border-[3px] border-black bg-white p-2 shadow-[2px_2px_0_#000]">
                    <div className="flex items-center gap-2">
                      <span className={`h-3 w-3 border-2 border-black ${importanceColor(item.importance)}`} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-xs font-black">{item.title}</span>
                        {item.goal_id && <span className="block truncate text-[8px] font-bold text-violet-700">GOAL: {goalName(item.goal_id)}</span>}
                      </span>
                      <span className="text-[9px] font-bold">{item.estimate_minutes || 25}m</span>
                      <button
                        type="button"
                        onClick={() => {
                           const opening = assigningId !== item.id;
                           const goalId = opening ? item.goal_id || '' : '';
                           const matchingWeek = weekItems.find(
                             week => week.goal_id === goalId && week.period_start === weekDates[0],
                           );
                           setAssigningId(opening ? item.id : null);
                           setAssignGoalId(goalId);
                           setAssignWeekId(matchingWeek?.id || '');
                        }}
                        className="border-2 border-black bg-cyan-300 p-1"
                        title="Schedule or assign"
                      >
                        <ChevronRight className="h-3 w-3" />
                      </button>
                    </div>
                    {assigningId === item.id && (
                      <div className="mt-2 grid grid-cols-2 gap-1 border-t-2 border-dashed border-gray-300 pt-2">
                         <select
                           value={assignGoalId}
                           onChange={event => {
                             const goalId = event.target.value;
                             const matchingWeek = weekItems.find(
                               week => week.goal_id === goalId && week.period_start === weekDates[0],
                             );
                             setAssignGoalId(goalId);
                             setAssignWeekId(matchingWeek?.id || '');
                             if (matchingWeek?.period_start) {
                               setAssignDate(today);
                             }
                           }}
                           className="col-span-2 border-2 border-black bg-violet-50 px-1 py-1 text-[9px] font-bold"
                         >
                           <option value="">NO GOAL — GENERAL TASK</option>
                           {goals.map(goal => (
                             <option key={goal.id} value={goal.id}>GOAL: {goal.title}</option>
                           ))}
                         </select>
                        <select
                          value={assignWeekId}
                          onChange={event => {
                            const weekId = event.target.value;
                            setAssignWeekId(weekId);
                            const week = weekItems.find(candidate => candidate.id === weekId);
                            if (week?.period_start) setAssignDate(week.period_start);
                          }}
                           disabled={!assignGoalId}
                          className="border-2 border-black bg-gray-50 px-1 py-1 text-[9px] font-bold"
                        >
                           <option value="">
                             {assignGoalId ? 'CHOOSE WEEKLY OUTCOME…' : 'NO WEEKLY OUTCOME'}
                           </option>
                           {weekItems.filter(week => week.goal_id === assignGoalId).map(week => (
                            <option key={week.id} value={week.id}>{goalName(week.goal_id)} › {week.title}</option>
                          ))}
                        </select>
                        <input
                          type="date"
                          value={assignDate}
                          onChange={event => setAssignDate(event.target.value)}
                          className="border-2 border-black bg-gray-50 px-1 py-1 text-[9px] font-bold"
                        />
                        <button
                          type="button"
                          onClick={() => void assignInboxItem(item)}
                           disabled={Boolean(assignGoalId && !assignWeekId)}
                          className="col-span-2 border-2 border-black bg-cyan-400 py-1 text-[9px] font-black uppercase disabled:opacity-40"
                        >
                          Assign & schedule
                        </button>
                      </div>
                    )}
                  </div>
                ))}
                <form onSubmit={createInboxItem} className="space-y-2 border-[3px] border-black bg-white p-2">
                  <input
                    value={inboxTitle}
                    onChange={event => setInboxTitle(event.target.value)}
                    placeholder="QUICK ADD TO INBOX…"
                    className="w-full border-2 border-black bg-gray-50 px-2 py-1 text-xs font-bold outline-none focus:bg-cyan-50"
                  />
                  <select
                    value={inboxGoalId}
                    onChange={event => setInboxGoalId(event.target.value)}
                    className="w-full border-2 border-black bg-violet-50 px-2 py-1 text-[9px] font-bold"
                  >
                    <option value="">NO GOAL — GENERAL INBOX</option>
                    {goals.map(goal => <option key={goal.id} value={goal.id}>GOAL: {goal.title}</option>)}
                  </select>
                  <div className="flex gap-1">
                    <select
                      value={inboxImportance}
                      onChange={event => setInboxImportance(event.target.value as Importance)}
                      className="min-w-0 flex-1 border-2 border-black bg-gray-50 px-1 text-[9px] font-bold uppercase"
                    >
                      <option value="high">High</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                    <input
                      type="number"
                      min={5}
                      max={120}
                      value={inboxEstimate}
                      onChange={event => setInboxEstimate(Number(event.target.value))}
                      className="w-16 border-2 border-black bg-gray-50 px-1 text-[9px] font-bold"
                      title="Estimate in minutes"
                    />
                    <button
                      disabled={!inboxTitle.trim() || busyId === 'new-inbox'}
                      className="border-2 border-black bg-black px-3 py-1 text-[9px] font-black text-white disabled:opacity-40"
                    >
                      ADD
                    </button>
                  </div>
                </form>
              </div>
            )}

            {view === 'today' && (
              <div className="space-y-3">
                <div>
                  <h4 className="text-sm font-black uppercase">Today · {today}</h4>
                  <p className="text-[9px] font-bold text-gray-500">Only daily tasks can start focus.</p>
                </div>
                {todayItems.length === 0 ? (
                  <div className="border-2 border-dashed border-gray-400 p-5 text-center text-[10px] font-bold text-gray-500">
                    NOTHING SCHEDULED TODAY. CHECK INBOX OR WEEK.
                  </div>
                ) : todayItems.map((item, index) => renderDailyTask(item, index, todayItems.length, 'today', 'importance'))}
              </div>
            )}

            {view === 'week' && (
              <div className="space-y-4">
                <div>
                  <h4 className="text-sm font-black uppercase">Week · {weekDates[0]} → {weekEnd}</h4>
                  <p className="text-[9px] font-bold text-gray-500">Vertical days for a compact desktop window.</p>
                </div>

                {goals.map(goal => {
                  const planned = items
                    .filter(item => item.horizon === 'day' && item.goal_id === goal.id && item.planned_for && item.planned_for >= weekDates[0] && item.planned_for <= weekEnd)
                    .reduce((total, item) => total + (item.estimate_minutes || 0), 0);
                  const overflow = goal.weekly_capacity_minutes > 0 && planned > goal.weekly_capacity_minutes;
                  return (
                    <div key={goal.id} className={`border-2 border-black px-2 py-1 text-[9px] font-black ${overflow ? 'bg-red-200' : 'bg-white'}`}>
                      {goal.title}: {planned}/{goal.weekly_capacity_minutes || '—'} MIN {overflow ? '· OVER CAPACITY' : ''}
                    </div>
                  );
                })}

                {currentWeekOutcomes.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-[9px] font-black uppercase text-gray-500">Weekly outcomes</div>
                    {currentWeekOutcomes.map(outcome => (
                       <div key={outcome.id} className="border-2 border-black bg-yellow-100 px-2 py-1 text-[10px] font-black">
                         <div className="flex items-center gap-1">
                           <span className="min-w-0 flex-1">{goalName(outcome.goal_id)} › {outcome.title}</span>
                           <button
                             type="button"
                             onClick={() => beginPlanItemEdit(outcome)}
                             className="border border-black bg-white p-1"
                             title="Edit weekly outcome"
                           >
                             <Pencil className="h-3 w-3" />
                           </button>
                         </div>
                         {editingItemId === outcome.id && renderPlanItemEditor(outcome)}
                      </div>
                    ))}
                  </div>
                )}

                {weekDates.map(dateValue => {
                  const dateItems = items
                    .filter(item => item.horizon === 'day' && item.planned_for === dateValue)
                    .sort((a, b) => importanceRank[a.importance] - importanceRank[b.importance]);
                  return (
                    <section key={dateValue} className="space-y-2">
                      <div className={`sticky top-0 z-10 border-2 border-black px-2 py-1 text-[10px] font-black uppercase ${dateValue === today ? 'bg-cyan-300' : 'bg-black text-white'}`}>
                        {new Date(`${dateValue}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short' })} · {dateValue}
                      </div>
                      {dateItems.length === 0 ? (
                        <div className="border-l-2 border-gray-300 px-2 py-1 text-[9px] font-bold text-gray-400">No tasks</div>
                      ) : dateItems.map((item, index) => renderDailyTask(item, index, dateItems.length, 'week', 'date_importance'))}
                    </section>
                  );
                })}

                <form onSubmit={createOutcome} className="space-y-1 border-[3px] border-black bg-white p-2">
                  <div className="text-[9px] font-black uppercase">Add weekly outcome</div>
                  <input value={outcomeTitle} onChange={event => setOutcomeTitle(event.target.value)} placeholder="OUTCOME…" className="w-full border-2 border-black px-2 py-1 text-[10px] font-bold" />
                  <div className="grid grid-cols-2 gap-1">
                    <select value={outcomeMonthId} onChange={event => setOutcomeMonthId(event.target.value)} className="border-2 border-black px-1 text-[9px] font-bold">
                      <option value="">Monthly parent…</option>
                      {monthItems.map(month => <option key={month.id} value={month.id}>{goalName(month.goal_id)} › {month.title}</option>)}
                    </select>
                    <input type="date" value={outcomeStart} onChange={event => setOutcomeStart(event.target.value)} className="border-2 border-black px-1 text-[9px] font-bold" />
                  </div>
                  <button disabled={!outcomeTitle.trim() || !outcomeMonthId} className="w-full border-2 border-black bg-yellow-300 py-1 text-[9px] font-black disabled:opacity-40">ADD OUTCOME (MONDAY)</button>
                </form>

                <form onSubmit={createDailyTask} className="space-y-1 border-[3px] border-black bg-white p-2">
                  <div className="text-[9px] font-black uppercase">Add daily task</div>
                  <input value={dailyTitle} onChange={event => setDailyTitle(event.target.value)} placeholder="NEXT ACTION…" className="w-full border-2 border-black px-2 py-1 text-[10px] font-bold" />
                  <select value={dailyWeekId} onChange={event => {
                    const weekId = event.target.value;
                    setDailyWeekId(weekId);
                    const week = weekItems.find(candidate => candidate.id === weekId);
                    if (week?.period_start) setDailyDate(week.period_start);
                  }} className="w-full border-2 border-black px-1 py-1 text-[9px] font-bold">
                    <option value="">Weekly parent…</option>
                    {weekItems.map(week => <option key={week.id} value={week.id}>{goalName(week.goal_id)} › {week.title}</option>)}
                  </select>
                  <div className="flex gap-1">
                    <input type="date" value={dailyDate} onChange={event => setDailyDate(event.target.value)} className="min-w-0 flex-1 border-2 border-black px-1 text-[9px] font-bold" />
                    <input type="number" min={5} max={120} value={dailyEstimate} onChange={event => setDailyEstimate(Number(event.target.value))} className="w-16 border-2 border-black px-1 text-[9px] font-bold" />
                    <button disabled={!dailyTitle.trim() || !dailyWeekId} className="border-2 border-black bg-cyan-400 px-2 py-1 text-[9px] font-black disabled:opacity-40">ADD</button>
                  </div>
                </form>
              </div>
            )}

            {view === 'month' && (
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h4 className="text-sm font-black uppercase">Goals & milestones</h4>
                    <p className="text-[9px] font-bold text-gray-500">Create a goal, then plan manually or with AI.</p>
                  </div>
                  <button type="button" onClick={() => setShowGoalForm(value => !value)} className="flex items-center gap-1 border-2 border-black bg-cyan-400 px-2 py-1 text-[9px] font-black">
                    <Plus className="h-3 w-3" /> GOAL
                  </button>
                </div>

                {showGoalForm && (
                  <form onSubmit={createGoal} className="space-y-1 border-[3px] border-black bg-cyan-50 p-2">
                    <input value={goalTitle} onChange={event => setGoalTitle(event.target.value)} placeholder="GOAL TITLE…" className="w-full border-2 border-black px-2 py-1 text-[10px] font-bold" />
                    <textarea value={goalDone} onChange={event => setGoalDone(event.target.value)} placeholder="DEFINITION OF DONE…" rows={2} className="w-full resize-none border-2 border-black px-2 py-1 text-[10px] font-bold" />
                    <div className="grid grid-cols-2 gap-1">
                      <input type="date" value={goalDeadline} onChange={event => setGoalDeadline(event.target.value)} className="border-2 border-black px-1 text-[9px] font-bold" />
                      <select value={goalImportance} onChange={event => setGoalImportance(event.target.value as Importance)} className="border-2 border-black px-1 text-[9px] font-bold uppercase">
                        <option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
                      </select>
                    </div>
                    <label className="flex items-center gap-2 text-[9px] font-black uppercase">
                      Weekly capacity
                      <input type="number" min={0} max={10080} value={goalCapacity} onChange={event => setGoalCapacity(Number(event.target.value))} className="min-w-0 flex-1 border-2 border-black px-1 py-1" />
                      min
                    </label>
                    <button disabled={!goalTitle.trim() || !goalDone.trim() || !goalDeadline} className="w-full border-2 border-black bg-cyan-400 py-1 text-[9px] font-black disabled:opacity-40">CREATE GOAL</button>
                  </form>
                )}

                {aiGoalId && !aiDraft && (
                  <form onSubmit={generateDraft} className="space-y-2 border-[3px] border-black bg-violet-50 p-2">
                    <div className="flex items-center gap-1 text-[10px] font-black uppercase"><Sparkles className="h-3 w-3" /> Plan with AI · {provider}</div>
                    <textarea value={aiCurrentState} onChange={event => setAiCurrentState(event.target.value)} placeholder="CURRENT STATE…" rows={2} className="w-full resize-none border-2 border-black px-2 py-1 text-[9px] font-bold" />
                    <input value={aiWeaknesses} onChange={event => setAiWeaknesses(event.target.value)} placeholder="WEAKNESSES, COMMA-SEPARATED…" className="w-full border-2 border-black px-2 py-1 text-[9px] font-bold" />
                    <input value={aiTopics} onChange={event => setAiTopics(event.target.value)} placeholder="TOPICS / SYLLABUS, COMMA-SEPARATED…" className="w-full border-2 border-black px-2 py-1 text-[9px] font-bold" />
                    <div className="flex flex-wrap gap-1">
                      {['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'].map((label, day) => (
                        <button key={label} type="button" onClick={() => setAiWeekdays(current => current.includes(day) ? current.filter(value => value !== day) : [...current, day].sort())} className={`border-2 border-black px-1 py-0.5 text-[8px] font-black ${aiWeekdays.includes(day) ? 'bg-violet-300' : 'bg-white'}`}>{label}</button>
                      ))}
                    </div>
                    <div className="grid grid-cols-2 gap-1">
                      <label className="text-[8px] font-black">MIN / DAY<input type="number" min={5} max={720} value={aiMinutesPerDay} onChange={event => setAiMinutesPerDay(Number(event.target.value))} className="mt-0.5 w-full border-2 border-black px-1 py-1" /></label>
                      <label className="text-[8px] font-black">SESSION MIN<input type="number" min={5} max={120} value={aiSessionDuration} onChange={event => setAiSessionDuration(Number(event.target.value))} className="mt-0.5 w-full border-2 border-black px-1 py-1" /></label>
                    </div>
                    <div className="flex gap-1">
                      <button type="button" onClick={() => setAiGoalId(null)} className="flex-1 border-2 border-black bg-white py-1 text-[9px] font-black">CANCEL</button>
                      <button disabled={busyId === 'ai-draft' || aiWeekdays.length === 0} className="flex-1 border-2 border-black bg-violet-300 py-1 text-[9px] font-black disabled:opacity-40">{busyId === 'ai-draft' ? 'GENERATING…' : 'GENERATE DRAFT'}</button>
                    </div>
                  </form>
                )}

                {aiDraft && (
                  <div className="space-y-2 border-[3px] border-black bg-violet-50 p-2 shadow-[2px_2px_0_#000]">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-[10px] font-black uppercase">AI draft · edit before adding</div>
                        <div className="text-[8px] font-bold text-gray-500">Draft only — tasks are created after you click ADD TASKS TO PLAN.</div>
                      </div>
                      <div className={`border-2 border-black px-1 py-0.5 text-[8px] font-black ${draftOverCapacity ? 'bg-red-300' : 'bg-green-200'}`}>{draftPlannedMinutes}/{aiDraft.capacity.planning_limit_minutes} MIN</div>
                    </div>
                    {aiDraft.draft.assumptions.length > 0 && (
                      <div className="border-2 border-black bg-yellow-100 p-1 text-[8px] font-bold">ASSUMPTIONS: {aiDraft.draft.assumptions.join(' · ')}</div>
                    )}
                    <div className="max-h-64 space-y-1 overflow-y-auto pr-1">
                      {aiDraft.draft.items.map(item => (
                        <div key={item.client_id} className={`grid grid-cols-[1fr_auto] gap-1 border-2 border-black p-1 ${item.horizon === 'month' ? 'bg-cyan-100' : item.horizon === 'week' ? 'ml-2 bg-yellow-100' : 'ml-4 bg-white'}`}>
                          <div className="min-w-0 space-y-1">
                            <div className="text-[7px] font-black uppercase text-gray-500">{item.horizon} · {item.client_id}</div>
                            <input value={item.title} onChange={event => updateDraftItem(item.client_id, { title: event.target.value })} className="w-full border border-black px-1 text-[9px] font-bold" />
                            <div className="flex gap-1">
                              <input type="date" value={item.planned_for || item.period_start || ''} onChange={event => updateDraftItem(item.client_id, item.horizon === 'day' ? { planned_for: event.target.value } : { period_start: event.target.value })} className="min-w-0 flex-1 border border-black px-1 text-[8px]" />
                              {item.horizon === 'day' && <input type="number" min={5} max={120} value={item.estimate_minutes || 25} onChange={event => updateDraftItem(item.client_id, { estimate_minutes: Number(event.target.value) })} className="w-12 border border-black px-1 text-[8px]" />}
                            </div>
                          </div>
                          <div className="flex flex-col gap-1 self-start">
                            {item.horizon !== 'day' && <button type="button" onClick={() => void regenerateDraftBranch(item.client_id)} disabled={busyId !== null} className="border border-black bg-yellow-200 p-1 disabled:opacity-40" title="Regenerate only this branch"><RotateCcw className="h-3 w-3" /></button>}
                            <button type="button" onClick={() => removeDraftBranch(item.client_id)} disabled={busyId !== null} className="border border-black bg-red-200 p-1 disabled:opacity-40" title="Remove item and children"><Trash2 className="h-3 w-3" /></button>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="grid grid-cols-2 gap-1 border-t-2 border-dashed border-gray-400 pt-2">
                      <input value={draftDayTitle} onChange={event => setDraftDayTitle(event.target.value)} placeholder="ADD DAILY TASK…" className="border-2 border-black px-1 text-[8px] font-bold" />
                      <select value={draftDayParent} onChange={event => {
                        const parentId = event.target.value;
                        setDraftDayParent(parentId);
                        const parent = aiDraft.draft.items.find(item => item.client_id === parentId);
                        if (parent?.period_start) setDraftDayDate(parent.period_start);
                      }} className="border-2 border-black px-1 text-[8px] font-bold"><option value="">Weekly parent…</option>{aiDraft.draft.items.filter(item => item.horizon === 'week').map(item => <option key={item.client_id} value={item.client_id}>{item.title}</option>)}</select>
                      <input type="date" value={draftDayDate} onChange={event => setDraftDayDate(event.target.value)} className="border-2 border-black px-1 text-[8px]" />
                      <button type="button" onClick={addDraftDay} disabled={!draftDayTitle.trim() || !draftDayParent} className="border-2 border-black bg-cyan-300 py-1 text-[8px] font-black disabled:opacity-40">ADD TO DRAFT</button>
                    </div>
                    {draftOverCapacity && <label className="flex items-center gap-2 border-2 border-red-500 bg-red-100 p-1 text-[8px] font-black"><input type="checkbox" checked={capacityOverride} onChange={event => setCapacityOverride(event.target.checked)} /> EXPLICITLY OVERRIDE 80% CAPACITY LIMIT</label>}
                    <div className="grid grid-cols-2 gap-1">
                      <button type="button" onClick={() => void cancelDraft()} disabled={busyId !== null} className="border-2 border-black bg-white py-1 text-[8px] font-black disabled:opacity-40">DISCARD DRAFT</button>
                      <button type="button" onClick={() => void generateDraft()} disabled={busyId !== null} className="border-2 border-black bg-yellow-200 py-1 text-[8px] font-black disabled:opacity-40">REGENERATE</button>
                      <button type="button" onClick={() => void approveDraft()} disabled={busyId !== null || (draftOverCapacity && !capacityOverride) || draftDayCount === 0} className="col-span-2 border-[3px] border-black bg-green-300 py-2 text-[9px] font-black shadow-[2px_2px_0_#000] disabled:opacity-40">{busyId === 'ai-approve' ? 'ADDING TASKS…' : `ADD ${draftDayCount} DAILY TASK${draftDayCount === 1 ? '' : 'S'} TO PLAN`}</button>
                    </div>
                  </div>
                )}

                {goals.length === 0 ? (
                  <div className="border-2 border-dashed border-violet-500 bg-violet-50 p-5 text-center text-[10px] font-bold text-gray-600">CREATE YOUR FIRST GOAL, THEN CHOOSE PLAN WITH AI.</div>
                ) : goals.map(goal => {
                  const goalProgress = progress[goal.id];
                  const milestones = monthItems.filter(item => item.goal_id === goal.id);
                  return (
                    <div key={goal.id} className="border-[3px] border-black bg-white p-3 shadow-[2px_2px_0_#000]">
                      <div className="flex items-start gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="break-words text-xs font-black">{goal.title}</div>
                          <div className="mt-1 text-[9px] font-bold text-gray-500">DONE WHEN: {goal.definition_of_done}</div>
                        </div>
                        <span className="border-2 border-black bg-yellow-200 px-1 text-[9px] font-black">{goal.deadline}</span>
                         <button type="button" onClick={() => beginGoalEdit(goal)} className="border-2 border-black bg-cyan-100 p-1" title="Edit goal"><Pencil className="h-3 w-3" /></button>
                        <button type="button" onClick={() => {
                          if (window.confirm(`Archive “${goal.title}”? Children and focus history will remain.`)) {
                            void run(goal.id, () => api.archiveGoal(goal.id, goal.version));
                          }
                        }} className="border-2 border-black bg-gray-100 p-1" title="Archive goal"><Archive className="h-3 w-3" /></button>
                        <button type="button" onClick={() => {
                          if (window.confirm(`Delete “${goal.title}” permanently? Monthly and weekly structure will be removed. Daily tasks and focus history will be kept; open tasks move to Inbox.`)) {
                            void run(`delete-${goal.id}`, () => api.deleteGoal(goal.id, goal.version));
                          }
                        }} className="border-2 border-black bg-red-200 p-1" title="Delete goal"><Trash2 className="h-3 w-3" /></button>
                      </div>
                       {editingGoalId === goal.id && (
                         <form onSubmit={event => void saveGoalEdit(event, goal)} className="mt-2 space-y-1 border-2 border-black bg-cyan-50 p-2">
                           <input value={editGoalTitle} onChange={event => setEditGoalTitle(event.target.value)} className="w-full border-2 border-black px-2 py-1 text-[9px] font-bold" />
                           <textarea value={editGoalDone} onChange={event => setEditGoalDone(event.target.value)} rows={2} className="w-full resize-none border-2 border-black px-2 py-1 text-[9px] font-bold" />
                           <div className="grid grid-cols-2 gap-1">
                             <input type="date" value={editGoalDeadline} onChange={event => setEditGoalDeadline(event.target.value)} className="border-2 border-black px-1 text-[8px] font-bold" />
                             <select value={editGoalImportance} onChange={event => setEditGoalImportance(event.target.value as Importance)} className="border-2 border-black px-1 text-[8px] font-bold uppercase">
                               <option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
                             </select>
                           </div>
                           <label className="flex items-center gap-2 text-[8px] font-black uppercase">
                             Weekly capacity
                             <input type="number" min={0} max={10080} value={editGoalCapacity} onChange={event => setEditGoalCapacity(Number(event.target.value))} className="min-w-0 flex-1 border-2 border-black px-1 py-1" />
                             min
                           </label>
                           <div className="grid grid-cols-2 gap-1">
                             <button type="button" onClick={() => setEditingGoalId(null)} className="border-2 border-black bg-white py-1 text-[8px] font-black">CANCEL</button>
                             <button disabled={!editGoalTitle.trim() || !editGoalDone.trim() || !editGoalDeadline || busyId === `edit-goal-${goal.id}`} className="border-2 border-black bg-green-300 py-1 text-[8px] font-black disabled:opacity-40">SAVE GOAL</button>
                           </div>
                         </form>
                       )}
                      <div className="mt-2 grid grid-cols-3 gap-1 text-center text-[9px] font-black">
                        <div className="border-2 border-black bg-gray-50 p-1"><div>{goalProgress?.actual_focus_minutes || 0}m</div><div className="text-[7px] text-gray-500">FOCUS</div></div>
                        <div className="border-2 border-black bg-gray-50 p-1"><div>{goalProgress?.completed_daily_task_count || 0}/{goalProgress?.daily_task_count || 0}</div><div className="text-[7px] text-gray-500">TASKS</div></div>
                        <div className="border-2 border-black bg-gray-50 p-1"><div>{goalProgress?.focus_session_count || 0}</div><div className="text-[7px] text-gray-500">SESSIONS</div></div>
                      </div>
                      <button type="button" onClick={() => { setAiGoalId(goal.id); setAiDraft(null); }} className="mt-2 flex w-full items-center justify-center gap-1 border-2 border-black bg-violet-300 py-1.5 text-[9px] font-black shadow-[2px_2px_0_#000]">
                        <Sparkles className="h-3 w-3" /> PLAN THIS GOAL WITH AI
                      </button>
                      <div className="mt-2 space-y-1">
                         {milestones.length === 0 ? <div className="text-[9px] font-bold text-gray-400">No monthly milestones yet.</div> : milestones.map(milestone => {
                           const outcomes = weekItems.filter(item => item.parent_id === milestone.id);
                           return (
                             <div key={milestone.id} className="border-l-4 border-cyan-400 bg-gray-50 px-2 py-1 text-[9px] font-bold">
                               <div className="flex items-center gap-1">
                                 <span className="min-w-0 flex-1">{milestone.title}</span>
                                 <span>{milestone.period_start?.slice(0, 7)}</span>
                                 <button type="button" onClick={() => beginPlanItemEdit(milestone)} className="border border-black bg-cyan-100 p-1" title="Edit monthly milestone"><Pencil className="h-3 w-3" /></button>
                               </div>
                               {editingItemId === milestone.id && renderPlanItemEditor(milestone)}
                               {outcomes.length > 0 && (
                                 <div className="mt-1 space-y-1 border-l-2 border-yellow-400 pl-2">
                                   {outcomes.map(outcome => (
                                     <div key={outcome.id} className="bg-yellow-100 px-1 py-1">
                                       <div className="flex items-center gap-1">
                                         <span className="min-w-0 flex-1">↳ {outcome.title}</span>
                                         <span>{outcome.period_start}</span>
                                         <button type="button" onClick={() => beginPlanItemEdit(outcome)} className="border border-black bg-white p-1" title="Edit weekly outcome"><Pencil className="h-3 w-3" /></button>
                                       </div>
                                       {editingItemId === outcome.id && renderPlanItemEditor(outcome)}
                                     </div>
                                   ))}
                                 </div>
                               )}
                             </div>
                           );
                         })}
                      </div>
                    </div>
                  );
                })}

                <form onSubmit={createMilestone} className="space-y-1 border-[3px] border-black bg-white p-2">
                  <div className="text-[9px] font-black uppercase">Add monthly milestone</div>
                  <input value={milestoneTitle} onChange={event => setMilestoneTitle(event.target.value)} placeholder="MONTHLY OUTCOME…" className="w-full border-2 border-black px-2 py-1 text-[10px] font-bold" />
                  <div className="flex gap-1">
                    <select value={milestoneGoalId} onChange={event => setMilestoneGoalId(event.target.value)} className="min-w-0 flex-1 border-2 border-black px-1 text-[9px] font-bold">
                      <option value="">Goal…</option>
                      {goals.map(goal => <option key={goal.id} value={goal.id}>{goal.title}</option>)}
                    </select>
                    <input type="month" value={milestoneMonth} onChange={event => setMilestoneMonth(event.target.value)} className="border-2 border-black px-1 text-[9px] font-bold" />
                    <button disabled={!milestoneTitle.trim() || !milestoneGoalId} className="border-2 border-black bg-yellow-300 px-2 py-1 text-[9px] font-black disabled:opacity-40">ADD</button>
                  </div>
                </form>
              </div>
            )}
          </>
        )}
      </div>

      <button type="button" onClick={() => void refresh()} className="flex items-center justify-center gap-1 border-t-[3px] border-black bg-white py-1 text-[8px] font-black uppercase hover:bg-gray-100">
        <RotateCcw className="h-3 w-3" /> Refresh plan
      </button>
    </div>
  );
}
