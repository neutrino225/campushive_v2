import { apiRequest } from '@/lib/api';

import type { AuthTokenResponse, AuthUser, LoginPayload, SignupPayload } from './auth-types';

export function loginRequest(payload: LoginPayload) {
  return apiRequest<AuthTokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function signupRequest(payload: SignupPayload) {
  return apiRequest<AuthTokenResponse>('/auth/signup', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchCurrentUser(token: string) {
  return apiRequest<AuthUser>('/auth/me', {
    method: 'GET',
    token,
  });
}

export function logoutRequest(token: string) {
  return apiRequest<{ message: string }>('/auth/logout', {
    method: 'POST',
    token,
  });
}
