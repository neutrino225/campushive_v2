import { useState } from 'react';
import { Pressable, StyleSheet, TextInput, TextInputProps, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { useTheme } from '@/hooks/use-theme';

type AuthInputProps = TextInputProps & {
  label: string;
  error?: string;
};

export function AuthInput({ label, error, secureTextEntry, style, ...props }: AuthInputProps) {
  const theme = useTheme();
  const [visible, setVisible] = useState(false);
  const canToggleVisibility = Boolean(secureTextEntry);

  return (
    <View style={styles.wrapper}>
      <ThemedText style={styles.label}>{label}</ThemedText>

      <View
        style={[
          styles.inputShell,
          {
            backgroundColor: theme.backgroundElement,
            borderColor: error ? '#dc2626' : theme.border,
          },
        ]}>
        <TextInput
          placeholderTextColor={theme.textSecondary}
          secureTextEntry={canToggleVisibility ? !visible : false}
          style={[styles.input, { color: theme.text }, style]}
          {...props}
        />

        {canToggleVisibility ? (
          <Pressable onPress={() => setVisible((current) => !current)} style={styles.toggleButton}>
            <ThemedText themeColor="textSecondary" style={styles.toggleText}>
              {visible ? 'Hide' : 'Show'}
            </ThemedText>
          </Pressable>
        ) : null}
      </View>

      {error ? (
        <ThemedText style={styles.errorText}>{error}</ThemedText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    gap: 8,
  },
  label: {
    fontSize: 14,
    fontWeight: 700,
  },
  inputShell: {
    minHeight: 58,
    borderWidth: 1,
    borderRadius: 18,
    flexDirection: 'row',
    alignItems: 'center',
    paddingLeft: 16,
    paddingRight: 12,
  },
  input: {
    flex: 1,
    minHeight: 58,
    fontSize: 16,
  },
  toggleButton: {
    paddingHorizontal: 6,
    paddingVertical: 4,
  },
  toggleText: {
    fontSize: 13,
    fontWeight: 700,
  },
  errorText: {
    fontSize: 13,
    color: '#dc2626',
    lineHeight: 18,
  },
});
