import { apiRequest } from '@/lib/api';

import type { ChatSession, ChatSessionDetail, MultiagentChatResponse } from './chat-types';

export function listChatSessions(token: string) {
  return apiRequest<ChatSession[]>('/chats', {
    method: 'GET',
    token,
  });
}

export function createChatSession(token: string, sessionName: string) {
  return apiRequest<ChatSession>('/chats', {
    method: 'POST',
    token,
    body: JSON.stringify({ session_name: sessionName }),
  });
}

export function getChatSession(token: string, sessionId: number) {
  return apiRequest<ChatSessionDetail>(`/chats/${sessionId}`, {
    method: 'GET',
    token,
  });
}

export function deleteChatSession(token: string, sessionId: number) {
  return apiRequest<{ message?: string }>(`/chats/${sessionId}`, {
    method: 'DELETE',
    token,
  });
}

export function sendMultiagentMessage(token: string, question: string, sessionId: number) {
  return apiRequest<MultiagentChatResponse>('/multiagent/chat', {
    method: 'POST',
    token,
    body: JSON.stringify({
      question,
      session_id: sessionId,
      stream: false,
    }),
  });
}
