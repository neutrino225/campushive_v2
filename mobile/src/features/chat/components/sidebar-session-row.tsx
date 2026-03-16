import { Pressable, StyleSheet, View } from 'react-native';
import Swipeable from 'react-native-gesture-handler/ReanimatedSwipeable';

import { ThemedText } from '@/components/themed-text';
import { useTheme } from '@/hooks/use-theme';

import type { ChatSession } from '../chat-types';
import { formatSessionLabel } from '../chat-utils';

type SidebarSessionRowProps = {
  onDelete: () => void;
  onPress: () => void;
  selected: boolean;
  session: ChatSession;
};

export function SidebarSessionRow({
  onDelete,
  onPress,
  selected,
  session,
}: SidebarSessionRowProps) {
  const theme = useTheme();
  const title = session.display_title || session.title || session.session_name;

  return (
    <Swipeable
      friction={2}
      overshootRight={false}
      renderRightActions={() => (
        <View style={styles.actionWrap}>
          <Pressable onPress={onDelete} style={styles.deleteAction}>
            <ThemedText style={styles.deleteLabel}>Delete</ThemedText>
          </Pressable>
        </View>
      )}>
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [
          styles.card,
          {
            backgroundColor: selected ? theme.primarySoft : theme.backgroundSelected,
            opacity: pressed ? 0.92 : 1,
          },
        ]}>
        <View style={styles.main}>
          <ThemedText
            numberOfLines={1}
            style={[styles.title, selected ? { color: theme.primary } : null]}>
            {title}
          </ThemedText>
          <ThemedText themeColor="textSecondary" style={styles.meta}>
            {formatSessionLabel(session.updated_at)}
          </ThemedText>
        </View>

        <ThemedText themeColor="textSecondary" style={styles.meta}>
          {session.message_count ?? 0} messages
        </ThemedText>
      </Pressable>
    </Swipeable>
  );
}

const styles = StyleSheet.create({
  actionWrap: {
    justifyContent: 'center',
    marginLeft: 10,
  },
  deleteAction: {
    minWidth: 92,
    minHeight: 56,
    borderRadius: 16,
    backgroundColor: '#dc2626',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  deleteLabel: {
    color: '#fff',
    fontSize: 13,
    fontWeight: 700,
  },
  card: {
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 8,
  },
  main: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  title: {
    flex: 1,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: 700,
  },
  meta: {
    fontSize: 12,
    lineHeight: 16,
  },
});
