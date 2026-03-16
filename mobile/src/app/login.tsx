import { router } from 'expo-router';
import { Controller, useForm } from 'react-hook-form';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { AuthInput } from '@/features/auth/components/auth-input';
import { loginSchema, type LoginFormValues, applyZodIssues } from '@/features/auth/auth-schemas';
import { useAuthStore } from '@/features/auth/auth-store';
import { useTheme } from '@/hooks/use-theme';

export default function LoginScreen() {
  const theme = useTheme();
  const login = useAuthStore((state) => state.login);
  const {
    control,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    defaultValues: {
      username: '',
      password: '',
    },
  });

  const onSubmit = handleSubmit(async (values) => {
    const parsed = loginSchema.safeParse(values);
    if (!parsed.success) {
      applyZodIssues(setError, parsed.error.issues);
      return;
    }

    try {
      await login(parsed.data);
      router.replace('../home');
    } catch (error) {
      setError('root', {
        type: 'server',
        message: error instanceof Error ? error.message : 'Unable to log in right now',
      });
    }
  });

  return (
    <View style={[styles.container, { backgroundColor: theme.background }]}>
      <SafeAreaView style={styles.safeArea}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.keyboardContainer}>
          <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
            <Pressable onPress={() => router.back()} style={styles.backButton}>
              <ThemedText themeColor="textSecondary">Back</ThemedText>
            </Pressable>

            <View style={styles.content}>
              <View style={styles.header}>
                <ThemedText type="title" style={styles.title}>
                  Login
                </ThemedText>
                <ThemedText themeColor="textSecondary" style={styles.subtitle}>
                  Sign in with your CampusHive account to continue on mobile.
                </ThemedText>
              </View>

              <View
                style={[
                  styles.formCard,
                  { backgroundColor: theme.backgroundElement, borderColor: theme.border },
                ]}>
                <Controller
                  control={control}
                  name="username"
                  render={({ field: { onChange, onBlur, value } }) => (
                    <AuthInput
                      autoCapitalize="none"
                      autoCorrect={false}
                      error={errors.username?.message}
                      label="Username"
                      onBlur={onBlur}
                      onChangeText={onChange}
                      placeholder="Enter your username"
                      returnKeyType="next"
                      value={value}
                    />
                  )}
                />

                <Controller
                  control={control}
                  name="password"
                  render={({ field: { onChange, onBlur, value } }) => (
                    <AuthInput
                      autoCapitalize="none"
                      autoCorrect={false}
                      error={errors.password?.message}
                      label="Password"
                      onBlur={onBlur}
                      onChangeText={onChange}
                      placeholder="Enter your password"
                      returnKeyType="done"
                      secureTextEntry
                      value={value}
                    />
                  )}
                />

                {errors.root?.message ? (
                  <View style={styles.errorBanner}>
                    <ThemedText style={styles.errorBannerText}>{errors.root.message}</ThemedText>
                  </View>
                ) : null}

                <Pressable
                  onPress={() => void onSubmit()}
                  style={({ pressed }) => [
                    styles.primaryButton,
                    { backgroundColor: theme.primary, opacity: pressed || isSubmitting ? 0.9 : 1 },
                  ]}>
                  {isSubmitting ? (
                    <ActivityIndicator color="#f8fbff" />
                  ) : (
                    <ThemedText style={styles.primaryButtonLabel}>Login</ThemedText>
                  )}
                </Pressable>

                <Pressable onPress={() => router.replace('../signup')} style={styles.switchAction}>
                  <ThemedText themeColor="textSecondary">
                    Don&apos;t have an account?{' '}
                    <ThemedText style={[styles.linkText, { color: theme.primary }]}>Sign up</ThemedText>
                  </ThemedText>
                </Pressable>
              </View>
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  safeArea: {
    flex: 1,
  },
  keyboardContainer: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: 28,
    paddingVertical: 20,
  },
  backButton: {
    alignSelf: 'flex-start',
    paddingVertical: 8,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    gap: 24,
  },
  header: {
    gap: 10,
  },
  title: {
    fontSize: 42,
    lineHeight: 46,
  },
  subtitle: {
    fontSize: 16,
    lineHeight: 24,
  },
  formCard: {
    borderWidth: 1,
    borderRadius: 28,
    padding: 20,
    gap: 16,
  },
  errorBanner: {
    borderRadius: 16,
    backgroundColor: '#fee2e2',
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  errorBannerText: {
    color: '#b91c1c',
    fontSize: 14,
    lineHeight: 20,
  },
  primaryButton: {
    minHeight: 56,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 4,
  },
  primaryButtonLabel: {
    color: '#f8fbff',
    fontSize: 16,
    fontWeight: 700,
  },
  switchAction: {
    alignItems: 'center',
    paddingTop: 8,
  },
  linkText: {
    fontWeight: 700,
  },
});
