import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { useTheme } from '@/hooks/use-theme';

import type { ChatSession } from '../chat-types';
import { formatSessionLabel } from '../chat-utils';

type ChatSessionPillProps = {
  session: ChatSession;
  selected: boolean;
  onPress: () => void;
};

export function ChatSessionPill({ session, selected, onPress }: ChatSessionPillProps) {
  const theme = useTheme();
  const title = session.display_title || session.title || session.session_name;

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        {
          backgroundColor: selected ? theme.primarySoft : theme.backgroundElement,
          borderColor: selected ? theme.primary : theme.border,
          opacity: pressed ? 0.9 : 1,
        },
      ]}>
      <View style={styles.content}>
        <ThemedText numberOfLines={1} style={[styles.title, selected ? { color: theme.primary } : null]}>
          {title}
        </ThemedText>

        <View style={styles.metaRow}>
          <ThemedText themeColor="textSecondary" style={styles.meta}>
            {formatSessionLabel(session.updated_at)}
          </ThemedText>
          <ThemedText themeColor="textSecondary" style={styles.meta}>
            {session.message_count ?? 0} messages
          </ThemedText>
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  content: {
    gap: 8,
  },
  title: {
    fontSize: 15,
    lineHeight: 20,
    fontWeight: 700,
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
  },
  meta: {
    fontSize: 12,
    lineHeight: 16,
    flexShrink: 1,
  },
});
