import { generateCodeVerifier, generateCodeChallenge } from '../utils/pkce';
import apiClient from './client';

const CLIENT_ID = import.meta.env.VITE_VK_CLIENT_ID;
// Браузер сам подставит https://www.qaizzy.localhost.cc или localhost
const REDIRECT_URI = `${window.location.origin}/auth/vk/callback`; 
const AUTH_URL = 'https://id.vk.ru/authorize';

export const initiateVkLogin = async () => {
  const codeVerifier = generateCodeVerifier();
  const codeChallenge = await generateCodeChallenge(codeVerifier);
  const state = generateCodeVerifier();

  sessionStorage.setItem('vk_code_verifier', codeVerifier);
  sessionStorage.setItem('vk_state', state);

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
    state: state,
    scope: 'vkid.personal_info email',
  });

  window.location.href = `${AUTH_URL}?${params.toString()}`;
};

export const completeVkLogin = async (code: string, state: string, deviceId: string) => {
  const savedState = sessionStorage.getItem('vk_state');
  const codeVerifier = sessionStorage.getItem('vk_code_verifier');

  if (state !== savedState) {
    throw new Error('Ошибка валидации state (возможная CSRF-атака)');
  }
  if (!codeVerifier) {
    throw new Error('Отсутствует code_verifier');
  }

  // ВНИМАНИЕ: Пишем просто '/auth/vk/callback'. 
  // apiClient сам превратит это в '/api/auth/vk/callback'
  const response = await apiClient.post('/auth/vk/callback', {
    code,
    codeVerifier,
    state,
    deviceId,
  });

  sessionStorage.removeItem('vk_code_verifier');
  sessionStorage.removeItem('vk_state');

  return response.data; 
};