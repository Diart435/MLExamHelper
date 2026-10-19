import apiClient from './client';

export interface User {
  userId: string;
  email: string;
  firstName: string;
  lastName: string;
}

export interface ChangePersonalRequest {
  email: string;
  firstName: string;
  lastName: string;
}

export interface ChangePasswordRequest {
  oldPassword: string;
  newPassword: string;
}

export const getMe = async (): Promise<User> => {
  const response = await apiClient.get<User>('/api/user/me');
  return response.data;
};

export const changePersonal = async (data: ChangePersonalRequest): Promise<void> => {
  await apiClient.put('/api/user/change/personal', data);
};

export const changePassword = async (data: ChangePasswordRequest): Promise<void> => {
  await apiClient.put('/api/user/change/password', data);
};