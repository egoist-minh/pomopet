'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, formatAPIError } from '@/lib/api';
import {
  HabitProfile,
  PersonalMemory,
  RelationalState,
  RelationshipEpisode,
  RelationshipMemoryAction,
  SharedRitual,
  UserProfile,
} from '@/lib/relationship-types';

const MEMORY_LABELS: Record<PersonalMemory['key'], string> = {
  preferred_name: 'Preferred name',
  preferred_address: 'Call me',
  communication_style: 'Reply style',
  explicit_focus_duration: 'Focus duration',
  like: 'Likes',
  dislike: 'Dislikes',
  productivity_preference: 'Productivity preference',
};

export default function RelationshipMemories() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [memories, setMemories] = useState<PersonalMemory[]>([]);
  const [habits, setHabits] = useState<HabitProfile[]>([]);
  const [episodes, setEpisodes] = useState<RelationshipEpisode[]>([]);
  const [rituals, setRituals] = useState<SharedRitual[]>([]);
  const [relationalState, setRelationalState] = useState<RelationalState | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextProfile, nextMemories, nextHabits, nextEpisodes, nextRituals, nextState] = await Promise.all([
        api.getRelationshipProfile(),
        api.getRelationshipMemories(),
        api.getRelationshipHabits(),
        api.getRelationshipEpisodes(),
        api.getRelationshipRituals(),
        api.getRelationalState(),
      ]);
      setProfile(nextProfile);
      setMemories(nextMemories);
      setHabits(nextHabits);
      setEpisodes(nextEpisodes);
      setRituals(nextRituals);
      setRelationalState(nextState);
      setDrafts(Object.fromEntries(nextMemories.map(memory => [memory.id, String(memory.value)])));
    } catch (loadError) {
      setError(formatAPIError(loadError, 'Could not load memories.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleProfile = async (field:
    | 'personalization_on'
    | 'memory_prompts_on'
    | 'relationship_context_on'
    | 'proactive_enabled'
    | 'proactive_jokes_on'
    | 'proactive_planning_on'
  ) => {
    if (!profile) return;
    setError(null);
    try {
      setProfile(await api.updateRelationshipProfile({ [field]: !profile[field] }));
    } catch (updateError) {
      setError(formatAPIError(updateError, 'Could not update personalization.'));
    }
  };

  const updateEpisode = async (episodeId: string, action: RelationshipMemoryAction) => {
    setBusyId(episodeId);
    setError(null);
    try {
      await api.updateRelationshipEpisode(episodeId, action);
      setEpisodes(current => current.filter(item => item.id !== episodeId));
    } catch (updateError) {
      setError(formatAPIError(updateError, 'Could not update shared moment.'));
    } finally {
      setBusyId(null);
    }
  };

  const updateRitual = async (ritualId: string, action: RelationshipMemoryAction) => {
    setBusyId(ritualId);
    setError(null);
    try {
      await api.updateRelationshipRitual(ritualId, action);
      setRituals(current => current.filter(item => item.id !== ritualId));
    } catch (updateError) {
      setError(formatAPIError(updateError, 'Could not update ritual.'));
    } finally {
      setBusyId(null);
    }
  };

  const saveMemory = async (memory: PersonalMemory) => {
    const raw = drafts[memory.id] ?? '';
    const value = memory.key === 'explicit_focus_duration' ? Number(raw) : raw.trim();
    setBusyId(memory.id);
    setError(null);
    try {
      const replacement = await api.updateRelationshipMemory(memory.id, value);
      setMemories(current => current.map(item => item.id === memory.id ? replacement : item));
      setDrafts(current => ({ ...current, [replacement.id]: String(replacement.value) }));
    } catch (updateError) {
      setError(formatAPIError(updateError, 'Could not update memory.'));
    } finally {
      setBusyId(null);
    }
  };

  const removeMemory = async (memory: PersonalMemory, neverMention = false) => {
    setBusyId(memory.id);
    setError(null);
    try {
      await api.deleteRelationshipMemory(memory.id, neverMention ? 'never_mention' : 'deleted');
      setMemories(current => current.filter(item => item.id !== memory.id));
    } catch (deleteError) {
      setError(formatAPIError(deleteError, 'Could not remove memory.'));
    } finally {
      setBusyId(null);
    }
  };

  const deleteAll = async () => {
    if (!window.confirm('Delete all personal memories, learned habits, shared moments, rituals, and relationship state? This cannot be undone.')) return;
    setError(null);
    try {
      await api.deleteRelationshipData();
      setMemories([]);
      setHabits([]);
      setEpisodes([]);
      setRituals([]);
      setRelationalState(null);
      setDrafts({});
      setProfile(current => current ? {
        ...current,
        display_name: null,
        relationship_context_on: false,
      } : current);
    } catch (deleteError) {
      setError(formatAPIError(deleteError, 'Could not delete relationship data.'));
    }
  };

  return (
    <section className="space-y-3 border-[3px] border-black bg-cyan-50 p-3 font-mono">
      <div>
        <h3 className="text-xs font-black uppercase">What Pomo remembers</h3>
        <p className="mt-1 text-[9px] text-gray-600">
          Explicit preferences may be sent to your AI provider. Shared moments and rituals stay local unless you separately opt in.
        </p>
      </div>

      {loading ? <p className="text-[10px] font-bold">LOADING...</p> : null}
      {error ? <p role="alert" className="border-2 border-red-600 bg-red-100 p-2 text-[10px] font-bold text-red-800">{error}</p> : null}

      {profile ? (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <button
            type="button"
            role="switch"
            aria-checked={profile.personalization_on}
            onClick={() => void toggleProfile('personalization_on')}
            className={`border-2 border-black p-2 text-[9px] font-black ${profile.personalization_on ? 'bg-green-400' : 'bg-gray-300'}`}
          >
            PERSONALIZATION: {profile.personalization_on ? 'ON' : 'OFF'}
          </button>
          <button
            type="button"
            role="switch"
            aria-checked={profile.memory_prompts_on}
            onClick={() => void toggleProfile('memory_prompts_on')}
            className={`border-2 border-black p-2 text-[9px] font-black ${profile.memory_prompts_on ? 'bg-green-400' : 'bg-gray-300'}`}
          >
            MEMORY CAPTURE: {profile.memory_prompts_on ? 'ON' : 'OFF'}
          </button>
          <button
            type="button"
            role="switch"
            aria-checked={profile.relationship_context_on}
            onClick={() => void toggleProfile('relationship_context_on')}
            className={`border-2 border-black p-2 text-[9px] font-black ${profile.relationship_context_on ? 'bg-green-400' : 'bg-gray-300'}`}
          >
            SHARE RELATIONSHIP CONTEXT: {profile.relationship_context_on ? 'ON' : 'OFF'}
          </button>
          <button
            type="button"
            role="switch"
            aria-checked={profile.proactive_enabled}
            onClick={() => void toggleProfile('proactive_enabled')}
            className={`border-2 border-black p-2 text-[9px] font-black ${profile.proactive_enabled ? 'bg-green-400' : 'bg-gray-300'}`}
          >
            PROACTIVE POMO: {profile.proactive_enabled ? 'ON' : 'OFF'}
          </button>
          <button
            type="button"
            role="switch"
            aria-checked={profile.proactive_jokes_on}
            onClick={() => void toggleProfile('proactive_jokes_on')}
            className={`border-2 border-black p-2 text-[9px] font-black ${profile.proactive_jokes_on ? 'bg-green-400' : 'bg-gray-300'}`}
          >
            PROACTIVE COMPANION: {profile.proactive_jokes_on ? 'ON' : 'OFF'}
          </button>
          <button
            type="button"
            role="switch"
            aria-checked={profile.proactive_planning_on}
            onClick={() => void toggleProfile('proactive_planning_on')}
            className={`border-2 border-black p-2 text-[9px] font-black ${profile.proactive_planning_on ? 'bg-green-400' : 'bg-gray-300'}`}
          >
            PLAN SUGGESTIONS: {profile.proactive_planning_on ? 'ON' : 'OFF'}
          </button>
        </div>
      ) : null}

      {!loading && memories.length === 0 ? (
        <p className="border-2 border-dashed border-gray-400 bg-white p-2 text-[10px] text-gray-600">No active memories.</p>
      ) : null}

      <div className="space-y-2">
        {memories.map(memory => (
          <div key={memory.id} className="border-2 border-black bg-white p-2">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="text-[9px] font-black uppercase">{MEMORY_LABELS[memory.key]}</span>
              <span className="text-[8px] uppercase text-gray-500">Explicit</span>
            </div>
            <div className="flex gap-1">
              <input
                aria-label={MEMORY_LABELS[memory.key]}
                type={memory.key === 'explicit_focus_duration' ? 'number' : 'text'}
                min={memory.key === 'explicit_focus_duration' ? 5 : undefined}
                max={memory.key === 'explicit_focus_duration' ? 240 : undefined}
                value={drafts[memory.id] ?? ''}
                onChange={event => setDrafts(current => ({ ...current, [memory.id]: event.target.value }))}
                className="min-w-0 flex-1 border-2 border-black px-2 py-1 text-[10px] font-bold"
              />
              <button
                type="button"
                disabled={busyId === memory.id}
                onClick={() => void saveMemory(memory)}
                className="border-2 border-black bg-cyan-300 px-2 text-[9px] font-black disabled:opacity-50"
              >
                SAVE
              </button>
            </div>
            <div className="mt-2 flex gap-2">
              <button type="button" disabled={busyId === memory.id} onClick={() => void removeMemory(memory)} className="text-[9px] font-bold underline disabled:opacity-50">FORGET</button>
              <button type="button" disabled={busyId === memory.id} onClick={() => void removeMemory(memory, true)} className="text-[9px] font-bold text-red-700 underline disabled:opacity-50">NEVER MENTION</button>
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-2 border-t-2 border-dashed border-gray-400 pt-3">
        <div>
          <h4 className="text-[10px] font-black uppercase">Shared moments · local by default</h4>
          <p className="text-[9px] text-gray-600">Only meaningful, evidenced events. Source references are shown for verification.</p>
        </div>
        {episodes.length === 0 ? (
          <p className="border-2 border-dashed border-gray-400 bg-white p-2 text-[10px] text-gray-600">No active shared moments.</p>
        ) : episodes.map(episode => (
          <div key={episode.id} className="border-2 border-black bg-white p-2">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-[9px] font-black uppercase">{episode.kind.replaceAll('_', ' ')}</div>
                <div className="text-[10px] font-bold">{episode.summary}</div>
                <div className="mt-1 text-[8px] text-gray-600">
                  {episode.source_type.replaceAll('_', ' ')} · {Math.round(episode.confidence * 100)}% confidence · {Math.round(episode.salience * 100)}% salience
                </div>
                <div className="text-[8px] text-gray-500">
                  Evidence: {episode.entity_type && episode.entity_id ? `${episode.entity_type}:${episode.entity_id}` : episode.source_reference || 'source retained'}
                  {episode.source_references.length > 1 ? ` · ${episode.source_references.length} linked sources` : ''}
                  {episode.updated_at ? ` · updated ${episode.updated_at.slice(0, 10)}` : ''}
                </div>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" disabled={busyId === episode.id} onClick={() => void updateEpisode(episode.id, 'archived')} className="text-[8px] font-black underline disabled:opacity-50">ARCHIVE</button>
              <button type="button" disabled={busyId === episode.id} onClick={() => void updateEpisode(episode.id, 'deleted')} className="text-[8px] font-black underline disabled:opacity-50">DELETE</button>
              <button type="button" disabled={busyId === episode.id} onClick={() => void updateEpisode(episode.id, 'never_mention')} className="text-[8px] font-black text-red-700 underline disabled:opacity-50">NEVER MENTION</button>
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-2 border-t-2 border-dashed border-gray-400 pt-3">
        <div>
          <h4 className="text-[10px] font-black uppercase">Confirmed rituals</h4>
          <p className="text-[9px] text-gray-600">Activated only after explicit agreement.</p>
        </div>
        {rituals.length === 0 ? (
          <p className="border-2 border-dashed border-gray-400 bg-white p-2 text-[10px] text-gray-600">No active rituals.</p>
        ) : rituals.map(ritual => (
          <div key={ritual.id} className="border-2 border-black bg-white p-2">
            <div className="text-[9px] font-black uppercase">{ritual.label}</div>
            <div className="text-[10px] font-bold">{ritual.description}</div>
            <div className="mt-1 text-[8px] text-gray-600">
              Explicitly confirmed · {ritual.evidence_count} source{ritual.evidence_count === 1 ? '' : 's'} · {Math.round(ritual.confidence * 100)}% confidence
            </div>
            <div className="text-[8px] text-gray-500">
              Evidence: {ritual.source_references.join(', ') || 'source retained'}
              {ritual.updated_at ? ` · updated ${ritual.updated_at.slice(0, 10)}` : ''}
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" disabled={busyId === ritual.id} onClick={() => void updateRitual(ritual.id, 'archived')} className="text-[8px] font-black underline disabled:opacity-50">ARCHIVE</button>
              <button type="button" disabled={busyId === ritual.id} onClick={() => void updateRitual(ritual.id, 'deleted')} className="text-[8px] font-black underline disabled:opacity-50">DELETE</button>
              <button type="button" disabled={busyId === ritual.id} onClick={() => void updateRitual(ritual.id, 'never_mention')} className="text-[8px] font-black text-red-700 underline disabled:opacity-50">NEVER MENTION</button>
            </div>
          </div>
        ))}
        {relationalState ? (
          <p className="border-2 border-dashed border-gray-400 bg-white p-2 text-[8px] text-gray-600">
            Expression state {relationalState.rule_version} · bounded 0–100 · {relationalState.evidence_count} verified event{relationalState.evidence_count === 1 ? '' : 's'} · familiarity {Math.round(relationalState.familiarity * 100)} · warmth {Math.round(relationalState.warmth * 100)} · playfulness {Math.round(relationalState.playfulness * 100)} · concern {Math.round(relationalState.concern * 100)} · pride {Math.round(relationalState.pride * 100)}
          </p>
        ) : null}
      </div>

      <div className="space-y-2 border-t-2 border-dashed border-gray-400 pt-3">
        <div>
          <h4 className="text-[10px] font-black uppercase">Learned habits · local only</h4>
          <p className="text-[9px] text-gray-600">Inferences from focus actions. These are not sent to your AI provider.</p>
        </div>
        {habits.length === 0 ? (
          <p className="border-2 border-dashed border-gray-400 bg-white p-2 text-[10px] text-gray-600">No active habits yet.</p>
        ) : habits.map(habit => (
          <div key={habit.id} className="border-2 border-black bg-white p-2">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-[9px] font-black uppercase">{habit.habit_key.replaceAll('_', ' ')}</div>
                <div className="text-[10px] font-bold">{String(habit.value)}</div>
                <div className="mt-1 text-[8px] text-gray-600">
                  {habit.explanation} · {Math.round(habit.confidence * 100)}% confidence
                  {Object.keys(habit.context).length ? ` · ${Object.values(habit.context).join(' / ')}` : ''}
                </div>
              </div>
              <button
                type="button"
                disabled={busyId === habit.id}
                onClick={async () => {
                  setBusyId(habit.id);
                  setError(null);
                  try {
                    await api.dismissRelationshipHabit(habit.id);
                    setHabits(current => current.filter(item => item.id !== habit.id));
                  } catch (dismissError) {
                    setError(formatAPIError(dismissError, 'Could not dismiss habit.'));
                  } finally {
                    setBusyId(null);
                  }
                }}
                className="text-[8px] font-black text-red-700 underline disabled:opacity-50"
              >
                DISMISS
              </button>
            </div>
          </div>
        ))}
      </div>

      <button type="button" onClick={() => void deleteAll()} className="w-full border-2 border-black bg-red-500 py-2 text-[9px] font-black text-white">
        DELETE ALL PERSONALIZATION DATA
      </button>
    </section>
  );
}
