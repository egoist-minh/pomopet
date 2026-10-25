import type { AIProvider, AIProviderStatus, ChatMessageItem, Task } from '@/lib/api';
import type { Emotion, SessionState } from '@/components/FloatingPet';

export type MainTab = 'chat' | 'tasks' | 'stats' | 'settings';
export type PetProactiveAnimation = 'drink-water' | null;

export interface PetWindowState {
  petName: string | null;
  emotion: Emotion;
  isSpeaking: boolean;
  speechText: string | null;
  proactiveAnimation: PetProactiveAnimation;
  sessionState: SessionState;
  timeLeft: number;
  currentTaskName?: string;
}

export type PetWindowAction =
  | { type: 'open-main'; tab: MainTab }
  | { type: 'send-message'; message: string }
  | { type: 'pause-session' }
  | { type: 'resume-session' }
  | { type: 'extend-session'; minutes: number }
  | { type: 'cancel-session' };

export interface MainWindowState {
  petName: string;
  emotion: Emotion;
  chatMessages: ChatMessageItem[];
  activeTab: MainTab;
  isDesktopMode: boolean;
  tasks: Task[];
  focusHoursToday: number;
  focusHoursWeek: number;
  sessionsCompleted: number;
  sessionState: SessionState;
  distractionChain: number;
  distractionData: { time: string; distractions: number }[];
  aiProvider: AIProvider;
  configuredProviders: AIProviderStatus;
  apiError: string | null;
  backendConnected: boolean;
}

export interface DistractionTrackingSettings {
  enabled: boolean;
  detectionThresholdSeconds: number;
  idleThresholdSeconds: number;
}

export interface AutoDistractionRecorded {
  eventId: string;
  source: 'app_switch' | 'idle';
  application: string | null;
  distractionCount: number;
}
