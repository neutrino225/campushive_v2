# CampusHive Mobile

Expo React Native scaffold for the CampusHive mobile app.

## Status

The Expo SDK 55 project is now scaffolded in this directory.

Current state:
- Expo Router entry is configured
- TypeScript scaffold is in place
- Base mobile project files exist
- Project branding is normalized to `CampusHive`

## Run

```bash
cd mobile
npm install
npx expo start
```

Platform targets:

```bash
npm run android
npm run ios
npm run web
```

## Recommended Next Build Order

1. Auth token storage with `expo-secure-store`
2. Shared API client for FastAPI backend
3. Login/signup screens
4. Chat shell + session list
5. Multiagent chat integration
6. Streaming support with fallback

## Planned Structure

```text
mobile/
  src/
    app/
    components/
    constants/
    features/
      auth/
      chat/
      faculty/
      timetable/
    hooks/
    lib/
    theme/
```

## Backend Reuse

The mobile app should reuse the existing backend APIs:
- `/auth/login`
- `/auth/signup`
- `/auth/me`
- `/chats`
- `/chats/{id}`
- `/multiagent/chat`

## Notes

- Keep mobile student-first initially.
- Do not port the web UI directly.
- Treat SSE streaming as an implementation risk to validate early on device.
