import React from 'react';
import { StyleProp, StyleSheet, TextStyle, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { useTheme } from '@/hooks/use-theme';

type MessageRichContentProps = {
  content: string;
  isUser?: boolean;
};

type TimetableData = {
  classes?: string;
  conflicts: string[];
  days: Array<{ day: string; items: string[] }>;
};

type Block =
  | { type: 'heading'; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'bulletList'; items: string[] }
  | { type: 'numberedList'; items: string[] }
  | { type: 'code'; text: string };

const DAY_PATTERN =
  /^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b/i;

function parseTimetableContent(content: string): TimetableData | null {
  const lines = content.split('\n').map((line) => line.trim());
  const days: TimetableData['days'] = [];
  const conflicts: string[] = [];
  let classes = '';
  let currentDay: TimetableData['days'][number] | null = null;
  let readingConflicts = false;

  for (const line of lines) {
    if (!line) {
      continue;
    }

    if (/^Classes:/i.test(line)) {
      classes = line.replace(/^Classes:\s*/i, '');
      continue;
    }

    if (/^Conflicts detected:?/i.test(line)) {
      readingConflicts = true;
      currentDay = null;
      continue;
    }

    const dayMatch = line.match(DAY_PATTERN);
    if (dayMatch) {
      readingConflicts = false;
      currentDay = { day: dayMatch[1], items: [] };
      days.push(currentDay);
      continue;
    }

    const cleanedLine = line.replace(/^[-*•]\s*/, '').replace(/^\d+\.\s*/, '');
    if (readingConflicts) {
      conflicts.push(cleanedLine);
      continue;
    }

    if (currentDay) {
      currentDay.items.push(cleanedLine);
    }
  }

  const hasStructuredDays = days.some((day) => day.items.length > 0);
  if (!hasStructuredDays) {
    return null;
  }

  return {
    classes,
    conflicts,
    days,
  };
}

function parseMarkdownBlocks(content: string): Block[] {
  const lines = content.split('\n');
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    if (/^```/.test(line)) {
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !/^```/.test(lines[index].trim())) {
        codeLines.push(lines[index]);
        index += 1;
      }
      blocks.push({ type: 'code', text: codeLines.join('\n') });
      index += 1;
      continue;
    }

    if (/^#{1,3}\s+/.test(line)) {
      blocks.push({ type: 'heading', text: line.replace(/^#{1,3}\s+/, '') });
      index += 1;
      continue;
    }

    if (/^[-*•]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length) {
        const currentLine = lines[index].trim();
        if (/^[-*•]\s+/.test(currentLine)) {
          items.push(currentLine.replace(/^[-*•]\s+/, ''));
          index += 1;
          continue;
        }

        if (!currentLine) {
          const nextLine = lines[index + 1]?.trim() ?? '';
          if (/^[-*•]\s+/.test(nextLine)) {
            index += 1;
            continue;
          }
        }

        break;
      }
      blocks.push({ type: 'bulletList', items });
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length) {
        const currentLine = lines[index].trim();
        if (/^\d+\.\s+/.test(currentLine)) {
          items.push(currentLine.replace(/^\d+\.\s+/, ''));
          index += 1;
          continue;
        }

        if (!currentLine) {
          const nextLine = lines[index + 1]?.trim() ?? '';
          if (/^\d+\.\s+/.test(nextLine)) {
            index += 1;
            continue;
          }
        }

        break;
      }
      blocks.push({ type: 'numberedList', items });
      continue;
    }

    const paragraphLines: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^#{1,3}\s+/.test(lines[index].trim()) &&
      !/^[-*•]\s+/.test(lines[index].trim()) &&
      !/^\d+\.\s+/.test(lines[index].trim()) &&
      !/^```/.test(lines[index].trim())
    ) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ type: 'paragraph', text: paragraphLines.join(' ') });
  }

  return blocks;
}

function renderInlineText(
  text: string,
  baseStyle: StyleProp<TextStyle>,
  boldStyle: StyleProp<TextStyle>,
  codeStyle: StyleProp<TextStyle>,
) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);

  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <ThemedText key={index} style={[baseStyle, boldStyle]}>
          {part.slice(2, -2)}
        </ThemedText>
      );
    }

    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <ThemedText key={index} style={[baseStyle, codeStyle]}>
          {part.slice(1, -1)}
        </ThemedText>
      );
    }

    return (
      <ThemedText key={index} style={baseStyle}>
        {part}
      </ThemedText>
    );
  });
}

export function MessageRichContent({ content, isUser = false }: MessageRichContentProps) {
  const theme = useTheme();

  if (isUser) {
    return <ThemedText style={[styles.userText, { color: theme.text }]}>{content}</ThemedText>;
  }

  const timetable = parseTimetableContent(content);
  if (timetable) {
    return (
      <View style={styles.container}>
        {timetable.classes ? (
          <View style={[styles.classesWrap, { backgroundColor: theme.primarySoft }]}>
            <ThemedText style={styles.classesLabel}>Classes</ThemedText>
            <ThemedText style={styles.classesText}>{timetable.classes}</ThemedText>
          </View>
        ) : null}

        {timetable.days.map((day) => (
          <View
            key={day.day}
            style={[
              styles.timetableCard,
              {
                backgroundColor: theme.backgroundElement,
                borderColor: theme.border,
              },
            ]}>
            <ThemedText style={[styles.dayTitle, { color: theme.text }]}>{day.day}</ThemedText>
            <View style={styles.dayItems}>
              {day.items.map((item, index) => (
                <ThemedText
                  key={`${day.day}-${index}`}
                  themeColor="textSecondary"
                  style={styles.dayItem}>
                  {item}
                </ThemedText>
              ))}
            </View>
          </View>
        ))}

        {timetable.conflicts.length ? (
          <View style={styles.conflictsWrap}>
            <ThemedText style={styles.conflictsTitle}>Conflicts detected</ThemedText>
            {timetable.conflicts.map((conflict, index) => (
              <ThemedText key={index} style={styles.conflictItem}>
                {conflict}
              </ThemedText>
            ))}
          </View>
        ) : null}
      </View>
    );
  }

  const blocks = parseMarkdownBlocks(content);

  return (
    <View style={styles.container}>
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          return (
            <ThemedText key={index} style={[styles.heading, { color: theme.text }]}>
              {block.text}
            </ThemedText>
          );
        }

        if (block.type === 'bulletList' || block.type === 'numberedList') {
          return (
            <View key={index} style={styles.listBlock}>
              {block.items.map((item, itemIndex) => (
                <View key={itemIndex} style={styles.listRow}>
                  <ThemedText style={[styles.listMarker, { color: theme.primary }]}>
                    •
                  </ThemedText>
                  <ThemedText themeColor="textSecondary" style={styles.listText}>
                    {renderInlineText(
                      item,
                      [styles.inlineText, { color: theme.textSecondary }],
                      [styles.boldText, { color: theme.text }],
                      [styles.codeText, { color: theme.primary }],
                    )}
                  </ThemedText>
                </View>
              ))}
            </View>
          );
        }

        if (block.type === 'code') {
          return (
            <View
              key={index}
              style={[
                styles.codeBlock,
                {
                  backgroundColor: theme.backgroundSelected,
                  borderColor: theme.border,
                },
              ]}>
              <ThemedText style={[styles.codeBlockText, { color: theme.primary }]}>{block.text}</ThemedText>
            </View>
          );
        }

        return (
          <ThemedText key={index} style={[styles.paragraph, { color: theme.textSecondary }]}>
            {renderInlineText(
              block.text,
              [styles.inlineText, { color: theme.textSecondary }],
              [styles.boldText, { color: theme.text }],
              [styles.codeText, { color: theme.primary }],
            )}
          </ThemedText>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 10,
  },
  userText: {
    fontSize: 15,
    lineHeight: 22,
  },
  heading: {
    fontSize: 17,
    lineHeight: 22,
    fontWeight: 700,
  },
  paragraph: {
    fontSize: 15,
    lineHeight: 22,
  },
  inlineText: {
    fontSize: 15,
    lineHeight: 22,
  },
  boldText: {
    fontWeight: 700,
  },
  codeText: {
    backgroundColor: 'rgba(57, 87, 216, 0.08)',
    paddingHorizontal: 4,
    borderRadius: 6,
  },
  listBlock: {
    gap: 8,
  },
  listRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  listMarker: {
    width: 18,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: 700,
  },
  listText: {
    flex: 1,
    fontSize: 15,
    lineHeight: 22,
  },
  codeBlock: {
    borderRadius: 14,
    padding: 12,
  },
  codeBlockText: {
    color: '#d9e9ff',
    fontFamily: 'ui-monospace',
    fontSize: 13,
    lineHeight: 19,
  },
  classesWrap: {
    borderRadius: 16,
    padding: 12,
    gap: 4,
  },
  classesLabel: {
    color: '#1a2942',
    fontSize: 12,
    lineHeight: 16,
    fontWeight: 700,
  },
  classesText: {
    color: '#1a2942',
    fontSize: 14,
    lineHeight: 20,
    fontWeight: 600,
  },
  timetableCard: {
    borderRadius: 16,
    padding: 12,
    gap: 8,
  },
  dayTitle: {
    fontSize: 15,
    lineHeight: 20,
    fontWeight: 700,
  },
  dayItems: {
    gap: 6,
  },
  dayItem: {
    fontSize: 14,
    lineHeight: 20,
  },
  conflictsWrap: {
    borderRadius: 16,
    backgroundColor: '#fee2e2',
    padding: 12,
    gap: 6,
  },
  conflictsTitle: {
    color: '#b91c1c',
    fontSize: 14,
    lineHeight: 18,
    fontWeight: 700,
  },
  conflictItem: {
    color: '#b91c1c',
    fontSize: 13,
    lineHeight: 18,
  },
});
