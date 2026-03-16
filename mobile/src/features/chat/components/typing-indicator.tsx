import { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { useTheme } from '@/hooks/use-theme';

export function TypingIndicator() {
  const theme = useTheme();
  const animations = useRef([
    new Animated.Value(0.35),
    new Animated.Value(0.35),
    new Animated.Value(0.35),
  ]).current;

  useEffect(() => {
    const loops = animations.map((value, index) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(index * 140),
          Animated.timing(value, {
            toValue: 1,
            duration: 260,
            easing: Easing.out(Easing.quad),
            useNativeDriver: true,
          }),
          Animated.timing(value, {
            toValue: 0.35,
            duration: 260,
            easing: Easing.in(Easing.quad),
            useNativeDriver: true,
          }),
        ]),
      ),
    );

    loops.forEach((loop) => loop.start());
    return () => loops.forEach((loop) => loop.stop());
  }, [animations]);

  return (
    <View style={styles.container}>
      <View style={styles.dotsRow}>
        {animations.map((value, index) => (
          <Animated.View
            key={index}
            style={[
              styles.dot,
              {
                backgroundColor: theme.primary,
                opacity: value,
                transform: [
                  {
                    translateY: value.interpolate({
                      inputRange: [0.35, 1],
                      outputRange: [2, -2],
                    }),
                  },
                ],
              },
            ]}
          />
        ))}
      </View>
      <ThemedText style={[styles.label, { color: theme.textSecondary }]}>
        Thinking through your request...
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 10,
  },
  dotsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 999,
  },
  label: {
    fontSize: 13,
    lineHeight: 18,
  },
});
