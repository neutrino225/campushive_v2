import { create } from 'zustand';

import { STORAGE_KEYS } from '@/lib/config';
import { deleteSecureValue, getSecureValue, setSecureValue } from '@/lib/secure-store';

import { fetchCurrentUser, loginRequest, logoutRequest, signupRequest } from './auth-api';
import type { AuthUser, LoginPayload, SignupPayload } from './auth-types';

type AuthState = {
  token: string | null;
  user: AuthUser | null;
  hydrated: boolean;
  restoring: boolean;
  bootstrap: () => Promise<void>;
  login: (payload: LoginPayload) => Promise<AuthUser>;
  signup: (payload: SignupPayload) => Promise<AuthUser>;
  logout: () => Promise<void>;
};

async function clearStoredSession() {
  await deleteSecureValue(STORAGE_KEYS.authToken);
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  hydrated: false,
  restoring: false,
  bootstrap: async () => {
    set({ restoring: true });

    try {
      const token = await getSecureValue(STORAGE_KEYS.authToken);
      if (!token) {
        set({ token: null, user: null, hydrated: true, restoring: false });
        return;
      }

      const user = await fetchCurrentUser(token);
      set({ token, user, hydrated: true, restoring: false });
    } catch {
      await clearStoredSession();
      set({ token: null, user: null, hydrated: true, restoring: false });
    }
  },
  login: async (payload) => {
    const response = await loginRequest(payload);
    await setSecureValue(STORAGE_KEYS.authToken, response.access_token);
    set({
      token: response.access_token,
      user: response.user,
      hydrated: true,
      restoring: false,
    });
    return response.user;
  },
  signup: async (payload) => {
    const response = await signupRequest(payload);
    await setSecureValue(STORAGE_KEYS.authToken, response.access_token);
    set({
      token: response.access_token,
      user: response.user,
      hydrated: true,
      restoring: false,
    });
    return response.user;
  },
  logout: async () => {
    try {
      const token = await getSecureValue(STORAGE_KEYS.authToken);
      if (token) {
        await logoutRequest(token);
      }
    } catch {
      // Logout should still clear the local session if the server call fails.
    } finally {
      await clearStoredSession();
      set({
        token: null,
        user: null,
        hydrated: true,
        restoring: false,
      });
    }
  },
}));
