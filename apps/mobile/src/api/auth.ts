import apiClient from './client';
import { User } from '../types';

export const loginApi = async (email: string, password: string) => {
  const resp = await apiClient.post('/api/v1/auth/login', { email, password });
  return resp.data;
};

export const bootstrapApi = async (payload: {
  bootstrap_token: string;
  email: string;
  password: string;
  display_name: string;
  family_name: string;
}) => {
  const resp = await apiClient.post('/api/v1/auth/bootstrap', payload);
  return resp.data;
};

export const logoutApi = async () => {
  try {
    await apiClient.post('/api/v1/auth/logout');
  } catch {
    // Ignore error on logout
  }
};

export const getMeApi = async (): Promise<User> => {
  const resp = await apiClient.get<User>('/api/v1/auth/me');
  return resp.data;
};

export const getSystemStatusApi = async () => {
  const resp = await apiClient.get('/api/v1/system/status');
  return resp.data;
};
