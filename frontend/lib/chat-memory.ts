const CHAT_THREAD_ID_KEY = 'pomo_chat_thread_id';

type ThreadStorage = Pick<Storage, 'getItem' | 'setItem'>;

export function getOrCreateChatThreadId(
  storage: ThreadStorage,
  createId: () => string = () => globalThis.crypto.randomUUID(),
): string {
  const existing = storage.getItem(CHAT_THREAD_ID_KEY)?.trim();
  if (existing) return existing;

  const threadId = createId();
  storage.setItem(CHAT_THREAD_ID_KEY, threadId);
  return threadId;
}
