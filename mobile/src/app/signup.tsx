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
import { applyZodIssues, signupSchema, type SignupFormValues } from '@/features/auth/auth-schemas';
import { useAuthStore } from '@/features/auth/auth-store';
import { useTheme } from '@/hooks/use-theme';

export default function SignupScreen() {
  const theme = useTheme();
  const signup = useAuthStore((state) => state.signup);
  const {
    control,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<SignupFormValues>({
    defaultValues: {
      username: '',
      email: '',
      password: '',
      confirmPassword: '',
    },
  });

  const onSubmit = handleSubmit(async (values) => {
    const parsed = signupSchema.safeParse(values);
    if (!parsed.success) {
      applyZodIssues(setError, parsed.error.issues);
      return;
    }

    try {
      await signup({
        username: parsed.data.username,
        email: parsed.data.email,
        password: parsed.data.password,
      });
      router.replace('../home');
    } catch (error) {
      setError('root', {
        type: 'server',
        message: error instanceof Error ? error.message : 'Unable to create your account right now',
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
                  Sign up
                </ThemedText>
                <ThemedText themeColor="textSecondary" style={styles.subtitle}>
                  Create your CampusHive student account to access the mobile assistant.
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
                      placeholder="Choose a username"
                      returnKeyType="next"
                      value={value}
                    />
                  )}
                />

                <Controller
                  control={control}
                  name="email"
                  render={({ field: { onChange, onBlur, value } }) => (
                    <AuthInput
                      autoCapitalize="none"
                      autoCorrect={false}
                      error={errors.email?.message}
                      keyboardType="email-address"
                      label="Email"
                      onBlur={onBlur}
                      onChangeText={onChange}
                      placeholder="Enter your email"
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
                      placeholder="Create a strong password"
                      returnKeyType="next"
                      secureTextEntry
                      value={value}
                    />
                  )}
                />

                <Controller
                  control={control}
                  name="confirmPassword"
                  render={({ field: { onChange, onBlur, value } }) => (
                    <AuthInput
                      autoCapitalize="none"
                      autoCorrect={false}
                      error={errors.confirmPassword?.message}
                      label="Confirm password"
                      onBlur={onBlur}
                      onChangeText={onChange}
                      placeholder="Re-enter your password"
                      returnKeyType="done"
                      secureTextEntry
                      value={value}
                    />
                  )}
                />

                <ThemedText themeColor="textSecondary" style={styles.helperText}>
                  Passwords must be at least 8 characters and include uppercase, lowercase, and a number.
                </ThemedText>

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
                    <ThemedText style={styles.primaryButtonLabel}>Create account</ThemedText>
                  )}
                </Pressable>

                <Pressable onPress={() => router.replace('../login')} style={styles.switchAction}>
                  <ThemedText themeColor="textSecondary">
                    Already have an account?{' '}
                    <ThemedText style={[styles.linkText, { color: theme.primary }]}>Login</ThemedText>
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
  helperText: {
    fontSize: 13,
    lineHeight: 19,
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
