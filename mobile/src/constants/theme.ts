import '@/global.css';

import { Platform } from 'react-native';

export const Colors = {
  light: {
    text: '#16213d',
    background: '#f6f7ff',
    backgroundElement: '#ffffff',
    backgroundSelected: '#e8ecff',
    textSecondary: '#66758f',
    primary: '#3957d8',
    primarySoft: '#dbe2ff',
    accent: '#69b7fb',
    border: '#d8e0fb',
    hero: '#d8d1f6',
    heroSecondary: '#bfdcff',
  },
  dark: {
    text: '#f8fbff',
    background: '#0d1530',
    backgroundElement: '#132044',
    backgroundSelected: '#1b2d5b',
    textSecondary: '#b4c0df',
    primary: '#8babff',
    primarySoft: '#22376e',
    accent: '#78cdfd',
    border: '#2b4178',
    hero: '#2a3170',
    heroSecondary: '#1d4f7d',
  },
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;

export const Fonts = Platform.select({
  ios: {
    /** iOS `UIFontDescriptorSystemDesignDefault` */
    sans: 'system-ui',
    /** iOS `UIFontDescriptorSystemDesignSerif` */
    serif: 'ui-serif',
    /** iOS `UIFontDescriptorSystemDesignRounded` */
    rounded: 'ui-rounded',
    /** iOS `UIFontDescriptorSystemDesignMonospaced` */
    mono: 'ui-monospace',
  },
  default: {
    sans: 'normal',
    serif: 'serif',
    rounded: 'normal',
    mono: 'monospace',
  },
  web: {
    sans: 'var(--font-display)',
    serif: 'var(--font-serif)',
    rounded: 'var(--font-rounded)',
    mono: 'var(--font-mono)',
  },
});

export const Spacing = {
  half: 2,
  one: 4,
  two: 8,
  three: 16,
  four: 24,
  five: 32,
  six: 64,
} as const;

export const BottomTabInset = Platform.select({ ios: 50, android: 80 }) ?? 0;
export const MaxContentWidth = 800;
