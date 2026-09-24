const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

/**
 * Thin client for the FastAPI envelope used by the auth endpoints.
 * Keeping the envelope handling here prevents views from depending on transport details.
 */
export async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

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
