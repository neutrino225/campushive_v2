import { apiRequest } from '@/lib/api';

export type BackendHealth = {
  status: string;
  timestamp: string;
  service: string;
};

export function fetchBackendHealth() {
  return apiRequest<BackendHealth>('/admin/health', {
    method: 'GET',
  });
}
