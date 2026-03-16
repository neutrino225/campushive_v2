export type ChatSession = {
  id: number;
  user_id: number;
  session_name: string;
  title?: string | null;
  display_title?: string | null;
  created_at: string;
  updated_at: string;
  message_count?: number;
};

export type ChatMessage = {
  id: number;
  session_id: number;
  message_type: string;
  content: string;
  agent_type?: string | null;
  message_metadata?: string | null;
  created_at: string;
};

export type ChatSessionDetail = {
  id: number;
  user_id: number;
  session_name: string;
  display_title?: string | null;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
};

export type MultiagentChatResponse = {
  result?: string;
  response?: string;
  route?: string[];
  session_id?: string;
  title?: string;
  awaiting_user_input?: boolean;
};
