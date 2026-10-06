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

export function getCaptcha() {
  return apiRequest('/auth/captcha')
}

export function loginUser({ user_email, password, captcha_token, captcha_code }) {
  return apiRequest('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ user_email, password, captcha_token, captcha_code }),
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

export function getModelSetting() {
  return apiRequest('/settings/model')
}

export function listProviderModels(provider) {
  // 这个 GET 会让后端解密用户自己的 Key、并可能把 Key 标为失效，
  // 所以显式带上同源写保护头——apiRequest 只在非 GET 时才自动注入它。
  return apiRequest(`/settings/models/${encodeURIComponent(provider)}`, {
    headers: { 'X-Requested-With': 'price-agent' },
  })
}

export function setModelSetting(provider, modelName = null) {
  return apiRequest('/settings/model', {
    method: 'PUT',
    body: JSON.stringify({ provider, model_name: modelName }),
  })
}

export function sendChatMessage(messages, recordIds = []) {
  // record_ids 只当索引用，商品名和价格由后端按登录用户反查展开，前端改不动。
  return apiRequest('/chat/message', {
    method: 'POST',
    body: JSON.stringify({ messages, record_ids: recordIds }),
  })
}

export function listPurchaseRecords() {
  return apiRequest('/purchase-records')
}

export function createPurchaseRecord(record) {
  return apiRequest('/purchase-records', { method: 'POST', body: JSON.stringify(record) })
}

export function updatePurchaseRecord(id, record) {
  return apiRequest(`/purchase-records/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(record),
  })
}

export function deletePurchaseRecord(id) {
  return apiRequest(`/purchase-records/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// 抓页面只出草稿，用户确认后再调 createPurchaseRecord 落库；POST 的同源头由 apiRequest 注入。
export function previewPurchaseLink(productUrl) {
  return apiRequest('/purchase-records/link-preview', {
    method: 'POST',
    body: JSON.stringify({ product_url: productUrl }),
  })
}

export function listCartItems() {
  return apiRequest('/cart/items')
}

export function createCartItem(item) {
  return apiRequest('/cart/items', { method: 'POST', body: JSON.stringify(item) })
}

export function updateCartItem(id, item) {
  return apiRequest(`/cart/items/${encodeURIComponent(id)}/update`, {
    method: 'PATCH',
    body: JSON.stringify(item),
  })
}

export function deleteCartItem(id) {
  return apiRequest(`/cart/items/${encodeURIComponent(id)}/delete`, { method: 'DELETE' })
}

export function transferCartItem(id, purchase = {}) {
  return apiRequest(`/cart/items/${encodeURIComponent(id)}/transform`, {
    method: 'POST',
    body: JSON.stringify(purchase),
  })
}

export function listOwnedItems() {
  return apiRequest('/items')
}

export function createOwnedItem(item) {
  return apiRequest('/items', { method: 'POST', body: JSON.stringify(item) })
}

export function updateOwnedItem(id, item) {
  return apiRequest(`/items/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(item),
  })
}

export function deleteOwnedItem(id) {
  return apiRequest(`/items/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
