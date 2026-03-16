import { router } from 'expo-router';
import { Image } from 'expo-image';
import { useQuery } from '@tanstack/react-query';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { Colors, Spacing } from '@/constants/theme';
import { useAuthStore } from '@/features/auth/auth-store';
import { fetchBackendHealth } from '@/features/system/backend-api';
import { useTheme } from '@/hooks/use-theme';

export default function HomeScreen() {
  const theme = useTheme();
  const user = useAuthStore((state) => state.user);
  const hydrated = useAuthStore((state) => state.hydrated);
  const restoring = useAuthStore((state) => state.restoring);
  const logout = useAuthStore((state) => state.logout);
  const backendHealth = useQuery({
    queryKey: ['backend-health'],
    queryFn: fetchBackendHealth,
    retry: 0,
    staleTime: 20_000,
  });

  return (
    <View style={[styles.container, { backgroundColor: theme.background }]}>
      <View
        style={[
          styles.backgroundArcTop,
          { backgroundColor: theme.hero, shadowColor: Colors.light.primary },
        ]}
      />
      <View
        style={[
          styles.backgroundArcBottom,
          { backgroundColor: theme.heroSecondary, shadowColor: Colors.light.accent },
        ]}
      />

      <SafeAreaView style={styles.safeArea}>
        <View style={styles.header}>
          <View style={[styles.statusPill, { backgroundColor: theme.backgroundElement, borderColor: theme.border }]}>
            <View style={[styles.statusDot, { backgroundColor: theme.primary }]} />
            <ThemedText type="small" themeColor="textSecondary" style={styles.statusText}>
              {user ? `Signed in as ${user.username}` : 'FAST campus companion'}
            </ThemedText>
          </View>

          <View
            style={[
              styles.connectionBadge,
              {
                backgroundColor: theme.backgroundElement,
                borderColor: backendHealth.isError ? '#fecaca' : theme.border,
              },
            ]}>
            <View
              style={[
                styles.connectionDot,
                {
                  backgroundColor: backendHealth.isError
                    ? '#dc2626'
                    : backendHealth.data?.status === 'healthy'
                      ? '#16a34a'
                      : theme.textSecondary,
                },
              ]}
            />
            <ThemedText themeColor="textSecondary" style={styles.connectionText}>
              {backendHealth.isLoading
                ? 'Checking backend connection...'
                : backendHealth.isError
                  ? 'Mobile app cannot reach the CampusHive backend'
                  : 'Connected to the shared CampusHive backend'}
            </ThemedText>
          </View>
        </View>

        <View style={styles.heroSection}>
          <View style={[styles.mascotHalo, { backgroundColor: theme.primarySoft }]} />
          <Image
            source={require('@/assets/images/campushive-bot.png')}
            contentFit="contain"
            style={styles.mascot}
          />

          <View style={styles.brandBlock}>
            <ThemedText style={styles.brandTitle}>
              <ThemedText style={[styles.brandTitle, { color: theme.text }]}>Campus</ThemedText>
              <ThemedText style={[styles.brandTitle, { color: theme.primary }]}>Hive</ThemedText>
            </ThemedText>
            <ThemedText type="subtitle" style={styles.heroPrompt}>
              Are you ready to talk?
            </ThemedText>
            <ThemedText themeColor="textSecondary" style={styles.heroCopy}>
              Timetables, faculty discovery, exam help, and campus guidance in one focused mobile assistant.
            </ThemedText>
          </View>
        </View>

        {restoring && !hydrated ? (
          <View
            style={[
              styles.actionCard,
              {
                backgroundColor: theme.backgroundElement,
                borderColor: theme.border,
                shadowColor: theme.primary,
              },
            ]}>
            <ActivityIndicator color={theme.primary} />
            <ThemedText themeColor="textSecondary" style={styles.footerNote}>
              Restoring your session...
            </ThemedText>
          </View>
        ) : user ? (
          <View
            style={[
              styles.actionCard,
              {
                backgroundColor: theme.backgroundElement,
                borderColor: theme.border,
                shadowColor: theme.primary,
              },
            ]}>
            <ThemedText style={styles.authenticatedHeadline}>Welcome back</ThemedText>
            <ThemedText themeColor="textSecondary" style={styles.footerNote}>
              Your mobile session is active. This account is shared with the web app through the same backend and database.
            </ThemedText>

            <Pressable
              accessibilityRole="button"
              onPress={() => router.push('./home')}
              style={({ pressed }) => [
                styles.primaryButton,
                { backgroundColor: theme.primary, opacity: pressed ? 0.9 : 1 },
              ]}>
              <ThemedText style={styles.primaryButtonLabel}>Open workspace</ThemedText>
            </Pressable>

            <Pressable
              accessibilityRole="button"
              onPress={() => void logout()}
              style={({ pressed }) => [
                styles.secondaryButton,
                {
                  borderColor: theme.primary,
                  backgroundColor: pressed ? theme.primarySoft : 'transparent',
                },
              ]}>
              <ThemedText style={[styles.secondaryButtonLabel, { color: theme.primary }]}>Sign out</ThemedText>
            </Pressable>
          </View>
        ) : (
          <View
            style={[
              styles.actionCard,
              {
                backgroundColor: theme.backgroundElement,
                borderColor: theme.border,
                shadowColor: theme.primary,
              },
            ]}>
            <Pressable
              accessibilityRole="button"
              onPress={() => router.push('./signup')}
              style={({ pressed }) => [
                styles.primaryButton,
                { backgroundColor: theme.primary, opacity: pressed ? 0.9 : 1 },
              ]}>
              <ThemedText style={styles.primaryButtonLabel}>Sign up</ThemedText>
            </Pressable>

            <Pressable
              accessibilityRole="button"
              onPress={() => router.push('./login')}
              style={({ pressed }) => [
                styles.secondaryButton,
                {
                  borderColor: theme.primary,
                  backgroundColor: pressed ? theme.primarySoft : 'transparent',
                },
              ]}>
              <ThemedText style={[styles.secondaryButtonLabel, { color: theme.primary }]}>Login</ThemedText>
            </Pressable>

            <ThemedText themeColor="textSecondary" style={styles.footerNote}>
              Sign up or log in against the same backend the web app uses.
            </ThemedText>
          </View>
        )}
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
    paddingHorizontal: 28,
    paddingTop: Spacing.two,
    paddingBottom: Spacing.four,
  },
  backgroundArcTop: {
    position: 'absolute',
    top: -72,
    right: -96,
    width: 280,
    height: 420,
    borderBottomLeftRadius: 220,
    borderBottomRightRadius: 60,
    borderTopLeftRadius: 180,
    borderTopRightRadius: 180,
    opacity: 0.92,
    shadowOpacity: 0.16,
    shadowRadius: 42,
    shadowOffset: { width: 0, height: 14 },
  },
  backgroundArcBottom: {
    position: 'absolute',
    left: -80,
    bottom: 100,
    width: 220,
    height: 220,
    borderRadius: 999,
    opacity: 0.32,
    shadowOpacity: 0.12,
    shadowRadius: 40,
    shadowOffset: { width: 0, height: 10 },
  },
  header: {
    alignItems: 'flex-start',
    gap: 10,
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 999,
  },
  statusText: {
    letterSpacing: 0.2,
  },
  connectionBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
    borderWidth: 1,
    maxWidth: 320,
  },
  connectionDot: {
    width: 8,
    height: 8,
    borderRadius: 999,
  },
  connectionText: {
    fontSize: 13,
    lineHeight: 18,
    flex: 1,
  },
  heroSection: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 28,
    paddingTop: 18,
  },
  mascotHalo: {
    position: 'absolute',
    width: 240,
    height: 240,
    borderRadius: 999,
    top: 56,
    opacity: 0.75,
  },
  mascot: {
    width: 196,
    height: 196,
  },
  brandBlock: {
    alignItems: 'center',
    gap: 12,
    maxWidth: 320,
  },
  brandTitle: {
    fontSize: 46,
    fontWeight: 800,
    letterSpacing: -1.8,
    lineHeight: 48,
  },
  heroPrompt: {
    fontSize: 22,
    lineHeight: 28,
    textAlign: 'center',
  },
  heroCopy: {
    textAlign: 'center',
    lineHeight: 23,
    fontSize: 15,
  },
  actionCard: {
    borderWidth: 1,
    borderRadius: 28,
    paddingHorizontal: 18,
    paddingVertical: 18,
    gap: 12,
    shadowOpacity: 0.12,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 12 },
  },
  primaryButton: {
    minHeight: 54,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButtonLabel: {
    color: '#f8fbff',
    fontSize: 16,
    fontWeight: 700,
  },
  secondaryButton: {
    minHeight: 54,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
  },
  secondaryButtonLabel: {
    fontSize: 16,
    fontWeight: 700,
  },
  authenticatedHeadline: {
    fontSize: 18,
    fontWeight: 700,
    textAlign: 'center',
  },
  footerNote: {
    fontSize: 13,
    lineHeight: 18,
    textAlign: 'center',
    marginTop: 2,
  },
});
