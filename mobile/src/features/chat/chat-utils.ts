export function formatSessionLabel(isoDate?: string) {
  if (!isoDate) return '';

  const value = new Date(isoDate);
  const now = new Date();
  const sameDay = value.toDateString() === now.toDateString();

  if (sameDay) {
    return value.toLocaleTimeString([], {
      hour: 'numeric',
      minute: '2-digit',
    });
  }

  return value.toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
  });
}

export function buildSessionName(count: number) {
  return count === 0 ? 'New Chat' : `New Chat ${count + 1}`;
}

export function extractAssistantText(result: { result?: string; response?: string }) {
  return result.result || result.response || 'No response received.';
}
