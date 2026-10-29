import apiClient from './client';
import { ChatResponse, ProductCandidate, PurchaseTask } from '../types';

export const sendChatMessage = async (
  agentType: string,
  payload: {
    conversation_id?: string;
    message: string;
    task_id?: string;
  }
): Promise<ChatResponse> => {
  const resp = await apiClient.post<ChatResponse>(`/api/v1/agents/${agentType}/chat`, payload);
  return resp.data;
};

export const getPurchaseTasks = async (): Promise<PurchaseTask[]> => {
  const resp = await apiClient.get<PurchaseTask[]>('/api/v1/purchases');
  return resp.data;
};

export const getPurchaseTask = async (taskId: string): Promise<PurchaseTask> => {
  const resp = await apiClient.get<PurchaseTask>(`/api/v1/purchases/${taskId}`);
  return resp.data;
};

export const getTaskCandidates = async (taskId: string): Promise<ProductCandidate[]> => {
  const resp = await apiClient.get<ProductCandidate[]>(`/api/v1/purchases/${taskId}/candidates`);
  return resp.data;
};

export const selectCandidateApi = async (taskId: string, productId: string): Promise<PurchaseTask> => {
  const resp = await apiClient.post<PurchaseTask>(`/api/v1/purchases/${taskId}/select`, {
    product_id: productId,
  });
  return resp.data;
};

export interface PrepareExecutionPayload {
  payment_mode?: string;
  card_last4?: string;
  card_nickname?: string;
  cvv?: string;
  action_type?: string;
}

export const prepareExecutionApi = async (taskId: string, payload?: PrepareExecutionPayload) => {
  const resp = await apiClient.post(`/api/v1/purchases/${taskId}/prepare-execution`, payload || {});
  return resp.data;
};

export const executeInstructionApi = async (instructionId: string) => {
  const resp = await apiClient.post(`/api/v1/mobile-use/instructions/${instructionId}/execute`);
  return resp.data;
};

export const cancelPurchaseTask = async (taskId: string): Promise<PurchaseTask> => {
  const resp = await apiClient.post<PurchaseTask>(`/api/v1/purchases/${taskId}/cancel`);
  return resp.data;
};

export const transcribeAudioApi = async (audioUri: string, mimeType: string = 'audio/m4a') => {
  const formData = new FormData();
  formData.append('file', {
    uri: audioUri,
    type: mimeType,
    name: 'voice_input.m4a',
  } as unknown as Blob);

  const resp = await apiClient.post('/api/v1/voice/transcribe', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return resp.data;
};
