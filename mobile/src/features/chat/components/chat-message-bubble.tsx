import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { useTheme } from '@/hooks/use-theme';

import { formatSessionLabel } from '../chat-utils';
import { MessageRichContent } from './message-rich-content';
import { TypingIndicator } from './typing-indicator';

type ChatMessageBubbleProps = {
  content: string;
  createdAt?: string;
  isUser: boolean;
  isPending?: boolean;
};

export function ChatMessageBubble({
  content,
  createdAt,
  isUser,
  isPending = false,
}: ChatMessageBubbleProps) {
  const theme = useTheme();

  return (
    <View style={[styles.row, isUser ? styles.userRow : styles.agentRow]}>
      <View
        style={[
          styles.bubble,
          isUser
            ? styles.userBubble
            : styles.agentBubble,
        ]}>
        {isPending ? (
          <TypingIndicator />
        ) : (
          <MessageRichContent content={content} isUser={isUser} />
        )}

        <ThemedText
          themeColor={isUser ? undefined : 'textSecondary'}
          style={[
            styles.timestamp,
            isUser ? styles.userTimestamp : { color: theme.textSecondary },
          ]}>
          {isPending ? 'Thinking...' : formatSessionLabel(createdAt)}
        </ThemedText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    width: '100%',
  },
  userRow: {
    alignItems: 'flex-end',
  },
  agentRow: {
    alignItems: 'flex-start',
  },
  bubble: {
    maxWidth: '88%',
    borderRadius: 24,
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 8,
  },
  userBubble: {
    backgroundColor: '#cfe4ff',
  },
  agentBubble: {
    backgroundColor: 'transparent',
    paddingHorizontal: 0,
    paddingVertical: 4,
  },
  timestamp: {
    fontSize: 12,
    lineHeight: 16,
  },
  userTimestamp: {
    color: '#51637e',
  },
});
