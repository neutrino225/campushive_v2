import { Pressable, StyleSheet, TextInput, View } from 'react-native';
import { SymbolView } from 'expo-symbols';

import { ThemedText } from '@/components/themed-text';
import { useTheme } from '@/hooks/use-theme';

type ChatComposerProps = {
  value: string;
  onChange: (text: string) => void;
  onSend: () => void;
  disabled?: boolean;
};

export function ChatComposer({ value, onChange, onSend, disabled = false }: ChatComposerProps) {
  const theme = useTheme();
  const canSend = value.trim().length > 0 && !disabled;

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: theme.backgroundElement,
        },
      ]}>
      <TextInput
        editable={!disabled}
        multiline
        onChangeText={onChange}
        placeholder="Ask about timetables, faculty, or campus information..."
        placeholderTextColor={theme.textSecondary}
        style={[styles.input, { color: theme.text }]}
        value={value}
      />

      <View style={styles.footer}>
        <View style={styles.footerSpacer} />

        <Pressable
          disabled={!canSend}
          onPress={onSend}
          style={({ pressed }) => [
            styles.sendButton,
            {
              backgroundColor: canSend ? theme.primary : theme.primarySoft,
              opacity: pressed && canSend ? 0.9 : 1,
            },
          ]}>
          {disabled ? (
            <ThemedText style={[styles.sendLabel, { color: theme.backgroundElement }]}>...</ThemedText>
          ) : (
            <SymbolView
              name={{ ios: 'paperplane.fill', android: 'send', web: 'send' }}
              size={18}
              tintColor={theme.backgroundElement}
            />
          )}
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 24,
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 14,
    gap: 12,
  },
  input: {
    minHeight: 76,
    maxHeight: 150,
    fontSize: 15,
    lineHeight: 22,
    textAlignVertical: 'top',
  },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 16,
  },
  footerSpacer: {
    flex: 1,
  },
  sendButton: {
    minWidth: 76,
    minHeight: 42,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  sendLabel: {
    fontSize: 14,
    fontWeight: 700,
  },
});
