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

export function listEmbeddingKeys() {
  return apiRequest('/setting/embedding-keys')
}

export function createEmbeddingKey({ provider, base_url, api_key, model_name }) {
  return apiRequest('/setting/embedding-keys', {
    method: 'POST',
    body: JSON.stringify({ provider, base_url, api_key, model_name }),
  })
}

export function updateEmbeddingKey(id, { provider, base_url, api_key, model_name }) {
  return apiRequest(`/setting/embedding-keys/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify({ provider, base_url, api_key, model_name }),
  })
}

export function deleteEmbeddingKey(id) {
  return apiRequest(`/setting/embedding-keys/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function setDefaultEmbeddingKey(id) {
  return apiRequest(`/setting/embedding-keys/${encodeURIComponent(id)}/default`, {
    method: 'PUT',
  })
}

// 新版对话契约：conversation_id 懒创建（首条消息传 null，后端返回真实 id），
// item_refs 是右侧面板勾选的商品引用（src: cart/owned + id）。
export function sendChatMessage({ conversationId = null, text, itemRefs = [] }) {
  return apiRequest('/chat/message', {
    method: 'POST',
    body: JSON.stringify({
      conversation_id: conversationId,
      text,
      item_refs: itemRefs.map((ref) => ({ src: ref.src, id: ref.id })),
    }),
  })
}

/**
 * 流式发送。**必须 fetch + ReadableStream，禁止 EventSource**（设计文档 §5.8）：
 * EventSource 规范上只支持 GET 且不允许自定义头，而 POST /chat/stream 依赖
 * X-Requested-With 头过 require_same_origin_write 校验，用 EventSource 必挂。
 *
 * onEvent(event, data) 每收到一帧回调一次：
 *   meta  {conversation_id, model}  —— 先于任何文本，前端据此把草稿标题转正
 *   delta {text}                   —— 文本增量，追加渲染
 *   done  {status, message_id}     —— 流正常收尾，status 三态见后端
 *   error {error}                  —— 模型异常，文案是后端翻译好的用户可读中文
 *   agent {agent, label, phase}    —— 子 agent「在调用」提示位（当前后端还没发）
 *
 * 传给 signal 可主动中断（AbortController）。**中断只断开连接，不保证服务端已落库**
 * （设计文档 §5.9）——中断后要确认落库得重拉 listConversationMessages。
 */
export async function streamChatMessage(
  { conversationId = null, text, itemRefs = [] },
  onEvent,
  signal,
) {
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: 'POST',
    credentials: 'include',
    signal,
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'price-agent',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({
      conversation_id: conversationId,
      text,
      item_refs: itemRefs.map((ref) => ({ src: ref.src, id: ref.id })),
    }),
  })

  // 阶段①出错时后端还没开始流，走的是正常 JSON 错误响应，这里要把 msg 取出来。
  // 不能直接 response.json()——成功时是 text/event-stream。
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload = await response.json()
      if (payload?.msg) message = payload.msg
    } catch {
      /* 非 JSON 响应，保留状态码文案 */
    }
    throw new Error(message)
  }
  if (!response.body) throw new Error('当前浏览器不支持流式响应')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // SSE 用空行分帧；最后一段可能不完整，留在 buffer 等下一批
      let split
      while ((split = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, split)
        buffer = buffer.slice(split + 2)
        const parsed = parseSseFrame(frame)
        if (parsed) onEvent(parsed.event, parsed.data)
      }
    }
  } finally {
    // 正常读完也要释放；中断时 read() 会抛 AbortError，由上层捕获
    reader.releaseLock()
  }
}

// 解析一帧：`event: delta\ndata: {...}` → {event:'delta', data:{...}}
function parseSseFrame(frame) {
  let event = 'message'
  const dataLines = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return null
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) }
  } catch {
    return null
  }
}

export function listConversations(limit = 50) {
  return apiRequest(`/conversations?limit=${limit}`)
}

export function listConversationMessages(conversationId, limit = 200) {
  return apiRequest(`/conversations/${encodeURIComponent(conversationId)}/messages?limit=${limit}`)
}

/**
 * RAG 索引状态 —— 对话页那条提示的数据源（2026-10-18）。
 *
 * 静态路径 `/rag-index-status` 与 `/{conversationId}/messages` 同前缀，
 * 但实测 FastAPI 按段匹配（静态段优先于动态段），**声明顺序不影响**。
 *
 * @returns {Promise<{code:number,msg:string,data:{has_key:boolean,pending:number,retrievable:boolean}}>}
 *   has_key     用户是否配了可用的向量模型
 *   pending     三张表里「还没 SYNCED」的行数合计
 *   retrievable 检索完全可用（配了 key 且没有待索引）
 */
export function getRagIndexStatus() {
  return apiRequest('/conversations/rag-index-status')
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

// 购物分组：列表/详情都带价格统计（未购买=购物车参考价，已购买=档案价，无价格不计入合计）。
// item_type 固定 'cart'（购物车·未购买）/ 'owned'（物品库·已购买）。
export function listGroups() {
  return apiRequest('/groups')
}

export function createGroup(group) {
  return apiRequest('/groups', { method: 'POST', body: JSON.stringify(group) })
}

export function updateGroup(id, group) {
  return apiRequest(`/groups/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(group),
  })
}

export function deleteGroup(id) {
  return apiRequest(`/groups/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function getGroupDetail(id) {
  return apiRequest(`/groups/${encodeURIComponent(id)}`)
}

export function addGroupItem(groupId, item) {
  return apiRequest(`/groups/${encodeURIComponent(groupId)}/items`, {
    method: 'POST',
    body: JSON.stringify(item),
  })
}

export function removeGroupItem(groupId, itemType, itemId) {
  return apiRequest(`/groups/${encodeURIComponent(groupId)}/items/${itemType}/${encodeURIComponent(itemId)}`, {
    method: 'DELETE',
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
