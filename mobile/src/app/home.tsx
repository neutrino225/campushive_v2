import { router } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Dimensions,
  Easing,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { useAuthStore } from '@/features/auth/auth-store';
import { fetchCurrentUser } from '@/features/auth/auth-api';
import { ChatComposer } from '@/features/chat/components/chat-composer';
import { ChatMessageBubble } from '@/features/chat/components/chat-message-bubble';
import { SidebarSessionRow } from '@/features/chat/components/sidebar-session-row';
import {
  createChatSession,
  deleteChatSession,
  getChatSession,
  listChatSessions,
  sendMultiagentMessage,
} from '@/features/chat/chat-api';
import type { ChatMessage, ChatSessionDetail } from '@/features/chat/chat-types';
import { buildSessionName, extractAssistantText } from '@/features/chat/chat-utils';
import { fetchBackendHealth } from '@/features/system/backend-api';
import { useTheme } from '@/hooks/use-theme';

export default function MobileHomeScreen() {
  const theme = useTheme();
  const user = useAuthStore((state) => state.user);
  const token = useAuthStore((state) => state.token);
  const hydrated = useAuthStore((state) => state.hydrated);
  const restoring = useAuthStore((state) => state.restoring);
  const logout = useAuthStore((state) => state.logout);
  const queryClient = useQueryClient();
  const sidebarWidth = Math.min(Math.round(Dimensions.get('window').width * 0.82), 340);
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [isSidebarOpen, setSidebarOpen] = useState(false);
  const [isSidebarRendered, setSidebarRendered] = useState(false);
  const [draft, setDraft] = useState('');
  const [chatError, setChatError] = useState<string | null>(null);
  const [pendingMessages, setPendingMessages] = useState<ChatMessage[]>([]);
  const scrollViewRef = useRef<ScrollView | null>(null);
  const sidebarAnimation = useRef(new Animated.Value(0)).current;
  const backendHealth = useQuery({
    queryKey: ['backend-health'],
    queryFn: fetchBackendHealth,
    retry: 0,
    staleTime: 20_000,
  });
  const currentUserQuery = useQuery({
    queryKey: ['auth-me', token],
    queryFn: () => fetchCurrentUser(token ?? ''),
    enabled: Boolean(token),
    retry: 0,
    staleTime: 20_000,
  });
  const sessionsQuery = useQuery({
    queryKey: ['chat-sessions', token],
    queryFn: () => listChatSessions(token ?? ''),
    enabled: Boolean(token),
    retry: 0,
    staleTime: 5_000,
  });
  const sessionDetailQuery = useQuery({
    queryKey: ['chat-session', token, selectedSessionId],
    queryFn: () => getChatSession(token ?? '', selectedSessionId as number),
    enabled: Boolean(token && selectedSessionId),
    retry: 0,
    staleTime: 2_000,
  });
  const createSessionMutation = useMutation({
    mutationFn: (sessionName: string) => createChatSession(token ?? '', sessionName),
    onSuccess: async (session) => {
      setSelectedSessionId(session.id);
      await queryClient.refetchQueries({ queryKey: ['chat-sessions', token] });
    },
    onError: (error) => {
      setChatError(error instanceof Error ? error.message : 'Unable to create a new chat.');
    },
  });
  const sendMessageMutation = useMutation({
    mutationFn: async ({ question, sessionId }: { question: string; sessionId: number }) => {
      return sendMultiagentMessage(token ?? '', question, sessionId);
    },
    onError: (error) => {
      setPendingMessages([]);
      setChatError(error instanceof Error ? error.message : 'Unable to send your message right now.');
    },
  });
  const deleteSessionMutation = useMutation({
    mutationFn: (sessionId: number) => deleteChatSession(token ?? '', sessionId),
    onSuccess: async (_, sessionId) => {
      setPendingMessages([]);
      if (selectedSessionId === sessionId) {
        setSelectedSessionId(null);
      }
      await queryClient.refetchQueries({ queryKey: ['chat-sessions', token] });
    },
    onError: (error) => {
      setChatError(error instanceof Error ? error.message : 'Unable to delete this chat.');
    },
  });

  useEffect(() => {
    if (hydrated && !restoring && !user) {
      router.replace('/');
    }
  }, [hydrated, restoring, user]);

  useEffect(() => {
    const sessions = sessionsQuery.data ?? [];
    if (!sessions.length) {
      if (selectedSessionId !== null) {
        setSelectedSessionId(null);
      }
      return;
    }

    const exists = sessions.some((session) => session.id === selectedSessionId);
    if (!selectedSessionId || !exists) {
      setSelectedSessionId(sessions[0].id);
    }
  }, [sessionsQuery.data, selectedSessionId]);

  useEffect(() => {
    if (sessionDetailQuery.data?.messages || pendingMessages.length) {
      requestAnimationFrame(() => {
        scrollViewRef.current?.scrollToEnd({ animated: true });
      });
    }
  }, [sessionDetailQuery.data?.messages, pendingMessages]);

  useEffect(() => {
    if (isSidebarOpen) {
      setSidebarRendered(true);
      Animated.timing(sidebarAnimation, {
        toValue: 1,
        duration: 220,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }).start();
      return;
    }

    Animated.timing(sidebarAnimation, {
      toValue: 0,
      duration: 180,
      easing: Easing.in(Easing.cubic),
      useNativeDriver: true,
    }).start(({ finished }) => {
      if (finished) {
        setSidebarRendered(false);
      }
    });
  }, [isSidebarOpen, sidebarAnimation]);

  const sessions = sessionsQuery.data ?? [];
  const selectedSession = sessions.find((session) => session.id === selectedSessionId) ?? null;
  const currentMessages = useMemo(() => {
    return [...(sessionDetailQuery.data?.messages ?? []), ...pendingMessages];
  }, [sessionDetailQuery.data?.messages, pendingMessages]);
  const sidebarTranslateX = sidebarAnimation.interpolate({
    inputRange: [0, 1],
    outputRange: [-sidebarWidth, 0],
  });
  const backdropOpacity = sidebarAnimation.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 1],
  });

  if (!user) {
    return <View style={[styles.container, { backgroundColor: theme.background }]} />;
  }

  const handleCreateSession = async () => {
    setChatError(null);
    await createSessionMutation.mutateAsync(buildSessionName(sessions.length));
    setSidebarOpen(false);
  };

  const handleDeleteCurrentSession = async () => {
    if (!selectedSessionId) {
      return;
    }
    setChatError(null);
    await deleteSessionMutation.mutateAsync(selectedSessionId);
    setSidebarOpen(false);
  };

  const handleSend = async () => {
    const question = draft.trim();
    if (!question || !token) {
      return;
    }

    setChatError(null);
    setDraft('');

    let targetSessionId = selectedSessionId;
    if (!targetSessionId) {
      const session = await createSessionMutation.mutateAsync(buildSessionName(sessions.length));
      targetSessionId = session.id;
    }

    const now = new Date().toISOString();
    const userMessage: ChatMessage = {
      id: Number(`9${Date.now()}`),
      session_id: targetSessionId,
      message_type: 'user',
      content: question,
      created_at: now,
      agent_type: null,
      message_metadata: null,
    };
    const assistantMessage: ChatMessage = {
      id: Number(`8${Date.now()}`),
      session_id: targetSessionId,
      message_type: 'agent',
      content: 'Thinking through your request...',
      created_at: now,
      agent_type: 'supervisor',
      message_metadata: null,
    };

    setPendingMessages([userMessage, assistantMessage]);
    setSelectedSessionId(targetSessionId);

    try {
      const response = await sendMessageMutation.mutateAsync({
        question,
        sessionId: targetSessionId,
      });

      const finalAssistantMessage: ChatMessage = {
        ...assistantMessage,
        content: extractAssistantText(response),
      };

      queryClient.setQueryData<ChatSessionDetail | undefined>(
        ['chat-session', token, targetSessionId],
        (current) => {
          if (!current) {
            return {
              id: targetSessionId as number,
              user_id: user.id,
              session_name: response.title || 'New Chat',
              display_title: response.title || null,
              created_at: now,
              updated_at: now,
              messages: [userMessage, finalAssistantMessage],
            };
          }

          return {
            ...current,
            display_title: response.title || current.display_title,
            updated_at: now,
            messages: [...current.messages, userMessage, finalAssistantMessage],
          };
        },
      );

      setPendingMessages([]);
      setChatError(null);

      void Promise.all([
        queryClient.refetchQueries({ queryKey: ['chat-sessions', token] }),
        queryClient.refetchQueries({ queryKey: ['chat-session', token, targetSessionId] }),
      ]);
    } catch {
      // onError handles state updates
    }
  };

  return (
    <View style={[styles.container, { backgroundColor: theme.background }]}>
      <SafeAreaView style={styles.safeArea}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.keyboardContainer}>
          <View style={styles.topBar}>
            <Pressable
              onPress={() => setSidebarOpen(true)}
              style={({ pressed }) => [
                styles.topBarButton,
                {
                  backgroundColor: theme.backgroundElement,
                  opacity: pressed ? 0.9 : 1,
                },
              ]}>
              <SymbolView
                name={{ ios: 'sidebar.left', android: 'menu', web: 'menu' }}
                size={18}
                tintColor={theme.text}
              />
            </Pressable>

            <View style={styles.topBarTitleBlock}>
              <ThemedText themeColor="textSecondary" style={styles.eyebrow}>
                CAMPUSHIVE CHAT
              </ThemedText>
              <ThemedText numberOfLines={1} style={styles.activeTitle}>
                {selectedSession?.display_title || selectedSession?.title || selectedSession?.session_name || 'New conversation'}
              </ThemedText>
            </View>

            <Pressable
              onPress={() => void handleCreateSession()}
              style={({ pressed }) => [
                styles.topBarButton,
                {
                  backgroundColor: theme.backgroundElement,
                  opacity: pressed ? 0.9 : 1,
                },
              ]}>
              <SymbolView
                name={{ ios: 'square.and.pencil', android: 'edit', web: 'edit' }}
                size={18}
                tintColor={theme.primary}
              />
            </Pressable>
          </View>

          {chatError ? (
            <View style={styles.errorBanner}>
              <ThemedText style={styles.errorBannerText}>{chatError}</ThemedText>
            </View>
          ) : null}

          <View style={styles.workspace}>
            <View style={styles.threadCard}>
              <ScrollView
                ref={scrollViewRef}
                contentContainerStyle={styles.threadContent}
                showsVerticalScrollIndicator={false}>
                {sessionDetailQuery.isLoading && selectedSessionId ? (
                  <View style={styles.threadLoader}>
                    <ActivityIndicator color={theme.primary} />
                  </View>
                ) : currentMessages.length ? (
                  currentMessages.map((message) => (
                    <ChatMessageBubble
                      key={`${message.id}-${message.created_at}`}
                      content={message.content}
                      createdAt={message.created_at}
                      isPending={
                        sendMessageMutation.isPending &&
                        message.message_type !== 'user' &&
                        message.content === 'Thinking through your request...'
                      }
                      isUser={message.message_type === 'user'}
                    />
                  ))
                ) : (
                  <View style={styles.emptyThread}>
                    <ThemedText style={styles.emptyThreadTitle}>Start the conversation</ThemedText>
                    <ThemedText themeColor="textSecondary" style={styles.emptyThreadCopy}>
                      Ask about timetables, faculty, admissions, or other campus workflows.
                    </ThemedText>
                  </View>
                )}
              </ScrollView>
            </View>

            <ChatComposer
              disabled={sendMessageMutation.isPending || createSessionMutation.isPending}
              onChange={setDraft}
              onSend={() => void handleSend()}
              value={draft}
            />
          </View>

          {isSidebarRendered ? (
            <>
              <Animated.View style={[styles.sidebarBackdrop, { opacity: backdropOpacity }]}>
                <Pressable style={StyleSheet.absoluteFillObject} onPress={() => setSidebarOpen(false)} />
              </Animated.View>
              <Animated.View
                style={[
                  styles.sidebarPanel,
                  {
                    backgroundColor: theme.backgroundElement,
                    width: sidebarWidth,
                    transform: [{ translateX: sidebarTranslateX }],
                  },
                ]}>
                <View style={styles.sidebarHeader}>
                  <View>
                    <ThemedText style={styles.sidebarTitle}>Chat history</ThemedText>
                    <ThemedText themeColor="textSecondary" style={styles.sidebarSubtitle}>
                      Compact session list for {user.username}
                    </ThemedText>
                  </View>

                  <Pressable
                    onPress={() => setSidebarOpen(false)}
                    style={({ pressed }) => [
                      styles.sidebarCloseButton,
                      {
                        backgroundColor: theme.backgroundSelected,
                        opacity: pressed ? 0.9 : 1,
                      },
                    ]}>
                    <SymbolView
                      name={{ ios: 'xmark', android: 'close', web: 'close' }}
                      size={14}
                      tintColor={theme.textSecondary}
                    />
                  </Pressable>
                </View>

                <View style={styles.sidebarActions}>
                  <Pressable
                    onPress={() => void handleCreateSession()}
                    style={({ pressed }) => [
                      styles.sidebarPrimaryAction,
                      {
                        backgroundColor: theme.primary,
                        opacity: pressed || createSessionMutation.isPending ? 0.9 : 1,
                      },
                    ]}>
                    <ThemedText style={styles.sidebarPrimaryLabel}>New chat</ThemedText>
                  </Pressable>

                  <Pressable
                    disabled={!selectedSessionId || deleteSessionMutation.isPending}
                    onPress={() => void handleDeleteCurrentSession()}
                    style={({ pressed }) => [
                      styles.sidebarSecondaryAction,
                      {
                        backgroundColor:
                          pressed && selectedSessionId ? theme.primarySoft : theme.backgroundSelected,
                        opacity: !selectedSessionId ? 0.55 : 1,
                      },
                    ]}>
                    <ThemedText themeColor="textSecondary" style={styles.sidebarSecondaryLabel}>
                      Delete selected
                    </ThemedText>
                  </Pressable>
                </View>

                <ScrollView
                  showsVerticalScrollIndicator={false}
                  contentContainerStyle={styles.sidebarSessionsContent}>
                  {sessionsQuery.isLoading ? (
                    <View
                      style={[
                        styles.sidebarLoadingCard,
                        { backgroundColor: theme.backgroundSelected },
                      ]}>
                      <ActivityIndicator color={theme.primary} />
                    </View>
                  ) : sessions.length ? (
                    sessions.map((session) => (
                      <SidebarSessionRow
                        key={session.id}
                        onDelete={() => {
                          setSelectedSessionId(session.id);
                          void deleteSessionMutation.mutateAsync(session.id);
                        }}
                        onPress={() => {
                          setChatError(null);
                          setPendingMessages([]);
                          setSelectedSessionId(session.id);
                          setSidebarOpen(false);
                        }}
                        selected={selectedSessionId === session.id}
                        session={session}
                      />
                    ))
                  ) : (
                    <View
                      style={[
                        styles.emptySessionsCard,
                        { backgroundColor: theme.backgroundSelected },
                      ]}>
                      <ThemedText style={styles.emptySessionsTitle}>No chats yet</ThemedText>
                      <ThemedText themeColor="textSecondary" style={styles.emptySessionsCopy}>
                        Create a new chat and the history will appear here.
                      </ThemedText>
                    </View>
                  )}
                </ScrollView>

                <Pressable
                  onPress={() => void logout().then(() => router.replace('/'))}
                  style={({ pressed }) => [
                    styles.sidebarSignOutButton,
                    { backgroundColor: theme.backgroundSelected, opacity: pressed ? 0.92 : 1 },
                  ]}>
                  <ThemedText themeColor="textSecondary" style={styles.sidebarSignOutLabel}>Sign out</ThemedText>
                </Pressable>
              </Animated.View>
            </>
          ) : null}
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
    paddingHorizontal: 18,
    paddingVertical: 16,
  },
  keyboardContainer: {
    flex: 1,
    gap: 12,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  topBarTitleBlock: {
    flex: 1,
    minWidth: 0,
  },
  topBarButton: {
    minHeight: 42,
    minWidth: 56,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  topBarButtonLabel: {
    fontSize: 20,
    fontWeight: 700,
  },
  topBarActionLabel: {
    fontSize: 13,
    fontWeight: 700,
  },
  eyebrow: {
    fontSize: 11,
    letterSpacing: 1.6,
  },
  activeTitle: {
    fontSize: 20,
    lineHeight: 26,
    fontWeight: 700,
    marginTop: 2,
  },
  workspace: {
    flex: 1,
    gap: 12,
  },
  threadCard: {
    flex: 1,
    overflow: 'visible',
  },
  threadContent: {
    paddingTop: 8,
    paddingBottom: 14,
    gap: 12,
    flexGrow: 1,
  },
  threadLoader: {
    flex: 1,
    minHeight: 180,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyThread: {
    flex: 1,
    minHeight: 220,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingHorizontal: 20,
  },
  emptyThreadTitle: {
    fontSize: 18,
    fontWeight: 700,
    textAlign: 'center',
  },
  emptyThreadCopy: {
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
  },
  errorBanner: {
    borderRadius: 18,
    backgroundColor: '#fee2e2',
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  errorBannerText: {
    color: '#b91c1c',
    fontSize: 14,
    lineHeight: 20,
  },
  sidebarBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(15, 23, 42, 0.18)',
  },
  sidebarPanel: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: 0,
    paddingHorizontal: 16,
    paddingTop: 18,
    paddingBottom: 16,
    gap: 14,
  },
  sidebarHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
    alignItems: 'flex-start',
  },
  sidebarTitle: {
    fontSize: 20,
    fontWeight: 700,
    lineHeight: 24,
  },
  sidebarSubtitle: {
    fontSize: 13,
    lineHeight: 18,
    marginTop: 4,
  },
  sidebarCloseButton: {
    minHeight: 38,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
    minWidth: 38,
  },
  sidebarCloseLabel: {
    fontSize: 13,
    fontWeight: 700,
  },
  sidebarActions: {
    gap: 10,
  },
  sidebarPrimaryAction: {
    minHeight: 44,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sidebarPrimaryLabel: {
    color: '#f8fbff',
    fontSize: 14,
    fontWeight: 700,
  },
  sidebarSecondaryAction: {
    minHeight: 44,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sidebarSecondaryLabel: {
    fontSize: 14,
    fontWeight: 700,
  },
  sidebarSessionsContent: {
    gap: 10,
    paddingBottom: 40,
  },
  sidebarLoadingCard: {
    height: 88,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptySessionsCard: {
    borderRadius: 16,
    padding: 16,
    gap: 8,
  },
  emptySessionsTitle: {
    fontSize: 15,
    fontWeight: 700,
  },
  emptySessionsCopy: {
    fontSize: 13,
    lineHeight: 18,
  },
  sidebarSignOutButton: {
    minHeight: 46,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
  },
  sidebarSignOutLabel: {
    fontSize: 14,
    fontWeight: 700,
  },
});
