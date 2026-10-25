import type { ChatActionStatus, ChatMessageItem, ChatResponse } from './api';
import type { ProactiveDecision } from './proactive-agent';

interface ChatActionClient {
  confirmChatAction(actionId: string, threadId: string): Promise<ChatResponse>;
  cancelChatAction(actionId: string, threadId: string): Promise<ChatResponse>;
}

export function updateChatActionStatus(
  messages: ChatMessageItem[],
  actionId: string,
  status: ChatActionStatus,
): ChatMessageItem[] {
  return messages.map(message => (
    message.action?.id === actionId
      ? { ...message, actionStatus: status }
      : message
  ));
}

export function hasUnresolvedChatAction(messages: ChatMessageItem[]): boolean {
  return messages.some(
    message => message.actionStatus === 'pending' || message.actionStatus === 'processing',
  );
}

export function appendProactivePlanSuggestion(
  messages: ChatMessageItem[],
  decision: ProactiveDecision,
): ChatMessageItem[] {
  if (
    decision.action !== 'SUGGEST_PLAN'
    || decision.target !== 'plan'
    || !decision.message
    || messages.some(message => message.proactiveSuggestion?.decisionId === decision.decision_id)
  ) {
    return messages;
  }
  return [
    ...messages,
    {
      role: 'pet',
      text: decision.message,
      proactiveSuggestion: { decisionId: decision.decision_id, target: 'plan' },
    },
  ];
}

export async function resolveChatActionRequest(
  actionId: string,
  decision: 'confirm' | 'cancel',
  threadId: string,
  refreshAfterConfirm: () => Promise<void>,
  client: ChatActionClient,
): Promise<ChatResponse> {
  const response = decision === 'confirm'
    ? await client.confirmChatAction(actionId, threadId)
    : await client.cancelChatAction(actionId, threadId);
  if (decision === 'confirm') {
    try {
      await refreshAfterConfirm();
    } catch {
      // The write already succeeded. API calls report refresh failures separately.
    }
  }
  return response;
}
