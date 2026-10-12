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
  return apiRequest('/setting/api-keys')
}

export function createApiKey({ provider, base_url, api_key, model_name }) {
  return apiRequest('/setting/api-keys', {
    method: 'POST',
    body: JSON.stringify({ provider, base_url, api_key, model_name }),
  })
}

export function updateApiKey(id, { provider, base_url, api_key, model_name }) {
  return apiRequest(`/setting/api-keys/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify({ provider, base_url, api_key, model_name }),
  })
}

export function deleteApiKey(id) {
  return apiRequest(`/setting/api-keys/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function setDefaultApiKey(id) {
  return apiRequest(`/setting/api-keys/${encodeURIComponent(id)}/default`, {
    method: 'PUT',
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

export function listLatestOwnedItems() {
  return apiRequest('/items/latest')
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

export function completeCartItemDraft({ name, category }) {
  return apiRequest('/cart/items/ai-draft', {
    method: 'POST',
    body: JSON.stringify({ name, category: category || null }),
  })
}

// 上传展示图：FormData 必须让浏览器自带 boundary，所以不走 apiRequest（它会强塞 JSON 头），
// 只手工补同源写保护头。返回相对路径（如 /uploads/xxx.jpg）。
export async function uploadImage(file) {
  const form = new FormData()
  form.append('image', file)
  const resp = await fetch(`${API_BASE_URL}/upload/image`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-Requested-With': 'price-agent' },
    body: form,
  })
  const payload = await resp.json().catch(() => null)
  if (!resp.ok || payload?.code !== 0) throw new Error(payload?.msg || '上传失败')
  return payload.data.image
}

// 后端图片统一解析：相对路径（/uploads/...）拼后端地址，http(s) 直接用，空值返回空串
export function resolveImageUrl(path) {
  if (!path) return ''
  return path.startsWith('/') ? `${API_BASE_URL}${path}` : path
}
