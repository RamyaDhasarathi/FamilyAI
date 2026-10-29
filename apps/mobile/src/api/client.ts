import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import { ApiError } from '../types';

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL || 'http://10.0.2.2:8000';

const TOKEN_KEY = 'family_os_access_token';
const REFRESH_KEY = 'family_os_refresh_token';

export const saveTokens = async (accessToken: string, refreshToken: string): Promise<void> => {
  try {
    await SecureStore.setItemAsync(TOKEN_KEY, accessToken);
    await SecureStore.setItemAsync(REFRESH_KEY, refreshToken);
  } catch (err) {
    console.warn('SecureStore not available or failed:', err);
  }
};

export const clearTokens = async (): Promise<void> => {
  try {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    await SecureStore.deleteItemAsync(REFRESH_KEY);
  } catch (err) {
    console.warn('Failed to clear tokens:', err);
  }
};

export const getAccessToken = async (): Promise<string | null> => {
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY);
  } catch {
    return null;
  }
};

export const getRefreshToken = async (): Promise<string | null> => {
  try {
    return await SecureStore.getItemAsync(REFRESH_KEY);
  } catch {
    return null;
  }
};

export const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const token = await getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  config.headers['X-Correlation-ID'] = Math.random().toString(36).substring(2, 10);
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // Auto-refresh token if 401 and refresh token exists
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const rToken = await getRefreshToken();
        if (rToken) {
          const refreshRes = await axios.post(`${BASE_URL}/api/v1/auth/refresh`, {
            refresh_token: rToken,
          });
          if (refreshRes.data?.access_token) {
            await saveTokens(refreshRes.data.access_token, rToken);
            originalRequest.headers.Authorization = `Bearer ${refreshRes.data.access_token}`;
            return apiClient(originalRequest);
          }
        }
      } catch (refreshErr) {
        await clearTokens();
      }
    }

    const apiError: ApiError = {
      code: 'NETWORK_ERROR',
      message: 'Network connection failed. Verify laptop backend is running and reachable.',
      correlation_id: '',
    };

    if (error.response) {
      const data = error.response.data as { error?: ApiError };
      if (data && data.error) {
        apiError.code = data.error.code;
        apiError.message = data.error.message;
        apiError.correlation_id = data.error.correlation_id;
        apiError.details = data.error.details;
      } else {
        apiError.code = `HTTP_${error.response.status}`;
        apiError.message = `Server returned error ${error.response.status}`;
      }
    } else if (error.request) {
      apiError.code = 'CONNECTION_REFUSED';
      apiError.message = `Cannot reach backend at ${BASE_URL}. Ensure phone and laptop are on the same Wi-Fi and firewall allows port 8000.`;
    }

    return Promise.reject(apiError);
  }
);

export default apiClient;
