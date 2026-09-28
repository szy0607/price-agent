const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

/**
 * Thin client for the FastAPI envelope used by the auth endpoints.
 * Keeping the envelope handling here prevents views from depending on transport details.
 */
export async function apiRequest(path, options = {}) {
  const { headers: customHeaders = {}, ...requestOptions } = options
  const method = (options.method || 'GET').toUpperCase()
  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...requestOptions,
      credentials: 'include',
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(method !== 'GET' ? { 'X-Requested-With': 'price-agent' } : {}),
        ...customHeaders,
      },
    })
  } catch {
    throw new Error('无法连接服务器')
  }

  let payload = null
  try {
    payload = await response.json()
  } catch {
    throw new Error('服务器返回了无法识别的响应')
  }

  if (!response.ok || payload?.code !== 0) {
    const error = new Error(payload?.msg || `请求失败（${response.status}）`)
    error.code = payload?.code
    error.status = response.status
    throw error
  }

  return payload.data
}

export function registerUser({ user_email, username, password }) {
  return apiRequest('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ user_email, username, password }),
  })
}

export function loginUser({ user_email, password }) {
  return apiRequest('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ user_email, password }),
  })
}

export function getCurrentUser() {
  return apiRequest('/auth/me')
}

export function logoutUser() {
  return apiRequest('/auth/logout', { method: 'POST' })
}

export function listApiKeys() {
  return apiRequest('/settings/api-keys')
}

export function saveApiKey(provider, apiKey) {
  return apiRequest(`/settings/api-keys/${encodeURIComponent(provider)}`, {
    method: 'PUT',
    body: JSON.stringify({ api_key: apiKey }),
  })
}

export function deleteApiKey(provider) {
  return apiRequest(`/settings/api-keys/${encodeURIComponent(provider)}`, { method: 'DELETE' })
}
