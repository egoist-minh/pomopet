export type PersonalMemoryKey =
  | 'preferred_name'
  | 'preferred_address'
  | 'communication_style'
  | 'explicit_focus_duration'
  | 'like'
  | 'dislike'
  | 'productivity_preference';

export interface UserProfile {
  id: string;
  display_name: string | null;
  personalization_on: boolean;
  memory_prompts_on: boolean;
  relationship_context_on: boolean;
  proactive_enabled: boolean;
  proactive_jokes_on: boolean;
  proactive_planning_on: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface PersonalMemory {
  id: string;
  profile_id: string;
  kind: string;
  key: PersonalMemoryKey;
  value: string | number;
  source_type: 'explicit_user' | 'verified_app_event' | 'behavioral_inference' | 'agent_suggestion';
  confidence: number;
  sensitivity: 'low' | 'sensitive';
  scope: string;
  active: boolean;
  created_at: string | null;
  updated_at: string | null;
  last_confirmed_at: string | null;
}

export interface HabitProfile {
  id: string;
  habit_key: 'focus_duration' | 'task_rank' | 'focus_start_time' | 'extension_pattern';
  context: Record<string, string>;
  value: string | number;
  distribution: Record<string, { count: number; weight: number }>;
  evidence_count: number;
  matching_count: number;
  confidence: number;
  active: boolean;
  model_version: string;
  last_observed_at: string;
  explanation: string;
}

export interface FocusSuggestionItem {
  source: 'explicit_preference' | 'behavioral_inference';
  confidence: number;
  evidence_count: number;
  explanation: string;
}

export interface FocusSuggestion {
  duration: (FocusSuggestionItem & { minutes: number; mode: 'prefill' | 'suggestion' }) | null;
  task_rank: (FocusSuggestionItem & { rank: number }) | null;
}

export type RelationshipMemoryAction = 'archived' | 'deleted' | 'never_mention';

export interface RelationshipEpisode {
  id: string;
  kind: 'milestone' | 'recovery' | 'shared_event' | 'important_correction';
  summary: string;
  source_type: 'explicit_user' | 'verified_app_event';
  source_reference: string | null;
  source_references: string[];
  entity_type: string | null;
  entity_id: string | null;
  salience: number;
  confidence: number;
  emotional_tone: 'positive' | 'neutral' | 'difficult' | null;
  status: 'active' | 'archived' | 'deleted' | 'never_mention';
  created_at: string | null;
  updated_at: string | null;
}

export interface SharedRitual {
  id: string;
  label: string;
  description: string;
  source_type: 'explicit_user';
  source_references: string[];
  confidence: number;
  evidence_count: number;
  explicitly_confirmed: boolean;
  status: 'active' | 'archived' | 'deleted' | 'never_mention';
  created_at: string | null;
  updated_at: string | null;
}

export interface RelationalState {
  familiarity: number;
  warmth: number;
  playfulness: number;
  concern: number;
  pride: number;
  rule_version: string;
  evidence_count: number;
  updated_at: string | null;
}
