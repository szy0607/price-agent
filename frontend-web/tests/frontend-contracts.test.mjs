import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { parse as parseSfc } from 'vue/compiler-sfc'

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), 'utf8')

test('shared sign-out flow calls the backend and always clears local auth', async () => {
  const api = await read('src/utils/api.js')
  const auth = await read('src/utils/auth.js')

  assert.match(api, /apiRequest\(['"]\/auth\/logout['"],\s*\{\s*method:\s*['"]POST['"]\s*\}\)/s)
  assert.match(auth, /export async function signOut\s*\(/)
  assert.match(auth, /await logoutUser\s*\(/)
  assert.match(auth, /finally\s*\{\s*clearAuth\s*\(\s*\)/s)
})

test('the global navigation exposes the shared sign-out action', async () => {
  const app = await read('src/App.vue')

  assert.match(app, /signOut as logoutCurrentUser/)
  assert.match(app, /@click=["]handleSignOut["]/)
})

test('settings no longer duplicates the account and logout panel', async () => {
  const settings = await read('src/views/SettingsView.vue')

  assert.doesNotMatch(settings, />账号<\/h2>/)
  assert.doesNotMatch(settings, /getAuthUser/)
  assert.doesNotMatch(settings, /@click=["]signOut["]/)
})

test('消费记录卡片组：点「其他」筛得出并入其中的那几笔', async () => {
  const { filterByGroup, groupByPlatform } = await import('../src/utils/platformGroups.js')
  const records = [
    { name: '键盘', platform: '京东', price: 300 },
    { name: '鼠标', platform: '京东', price: 100 },
    { name: '显示器', platform: '淘宝', price: 900 },
    { name: '台灯', platform: '闲鱼', price: 50 },
    { name: '杯子', platform: '得物' },
    { name: '耳机', platform: ' 拼多多 ', price: 20 },
  ]

  const { groups, members } = groupByPlatform(records, 4)

  assert.deepEqual(groups.map((group) => group.key), ['京东', '淘宝', '闲鱼', '其他'])
  assert.deepEqual(groups[3].merged, ['得物', '拼多多'])
  assert.equal(groups[3].count, 2)
  // 这一行就是原先的 bug：卡片 key 是「其他」，记录里却没有一条 platform 叫这个名字
  assert.deepEqual(filterByGroup(records, members, '其他').map((item) => item.name), ['杯子', '耳机'])
  assert.deepEqual(filterByGroup(records, members, '京东').map((item) => item.name), ['键盘', '鼠标'])
  assert.deepEqual(filterByGroup(records, members, null), records)
  assert.deepEqual(filterByGroup(records, members, '闲鱼'), records.slice(3, 4))
  // 组消失后（不再需要合并）旧 key 只能筛出空集，交给视图去取消筛选
  assert.deepEqual(filterByGroup(records, members, '得物'), [])
})

test('settings uses the key list endpoint without the removed model setting flow', async () => {
  const source = await read('src/views/SettingsView.vue')
  const loadKeys = source.match(/async function loadKeys\(\)[\s\S]*?\n\}/)

  assert.ok(loadKeys, 'loadKeys not found')
  assert.doesNotMatch(source, /getModelSetting|listProviderModels|setModelSetting|<select/)
  assert.match(loadKeys[0], /listApiKeys\(\)/)
  assert.match(source, /base_url/)
  assert.match(source, /model_name/)
  assert.match(source, /setDefaultApiKey/)
})

test('api key helpers use the five current setting endpoints', async () => {
  const api = await read('src/utils/api.js')
  assert.match(api, /apiRequest\('\/setting\/api-keys'\)/)
  assert.match(api, /apiRequest\('\/setting\/api-keys', \{[\s\S]*method: 'POST'/)
  assert.match(api, /apiRequest\(`\/setting\/api-keys\/\$\{encodeURIComponent\(id\)\}`, \{[\s\S]*method: 'PUT'/)
  assert.match(api, /apiRequest\(`\/setting\/api-keys\/\$\{encodeURIComponent\(id\)\}`, \{ method: 'DELETE' \}\)/)
  assert.match(api, /\/default`, \{[\s\S]*method: 'PUT'/)
  assert.doesNotMatch(api, /\/settings\/api-keys|\/settings\/model|\/settings\/models/)
  const chat = await read('src/views/ChatView.vue')
  assert.doesNotMatch(chat, /getModelSetting|modelSetting/)
  const cart = await read('src/views/CartView.vue')
  assert.match(cart, /completeCartItemDraft\(/)
  assert.match(cart, /key\.endsWith\('\(AI\)'\)[\s\S]*来源：网络/)
  assert.match(cart, /网络参考价可能过时/)
})

test('every route view keeps a single element root so the page transition can animate it', async () => {
  const router = await read('src/router/index.js')
  const viewNames = [...router.matchAll(/import\('\.\.\/views\/([A-Za-z]+\.vue)'\)/g)].map((m) => m[1])
  assert.ok(viewNames.length >= 8, `router 里只找到 ${viewNames.length} 个懒加载视图`)

  for (const name of new Set(viewNames)) {
    const { descriptor, errors } = parseSfc(await read(`src/views/${name}`), { filename: name })
    assert.deepEqual(errors, [], `${name} 模板解析失败`)
    const roots = (descriptor.template?.ast?.children ?? []).filter(
      (node) => node.type === 1 || node.type === 5 || node.type === 8 || (node.type === 2 && node.value.trim()),
    )
    // App.vue 用 <Transition mode="out-in"> 包 RouterView：多根组件会渲染成 Fragment，
    // leave 回调永不完成，切页后 <main> 会一直空白，只能整页刷新才恢复。
    assert.equal(roots.length, 1, `${name} 有 ${roots.length} 个根节点，路由过渡会卡死`)
    assert.equal(roots[0].type, 1, `${name} 的根节点不是元素`)
  }
})

test('shopping group api helpers hit the /groups endpoints', async () => {
  const api = await read('src/utils/api.js')
  assert.match(api, /apiRequest\('\/groups'\)/)
  assert.match(api, /apiRequest\('\/groups', \{[\s\S]*method: 'POST'/)
  assert.match(api, /apiRequest\(`\/groups\/\$\{encodeURIComponent\(id\)\}`, \{[\s\S]*method: 'PATCH'/)
  assert.match(api, /apiRequest\(`\/groups\/\$\{encodeURIComponent\(id\)\}`, \{ method: 'DELETE' \}\)/)
  assert.match(api, /apiRequest\(`\/groups\/\$\{encodeURIComponent\(id\)\}`, \{[\s\S]*method: 'DELETE'/)
  assert.match(api, /apiRequest\(`\/groups\/\$\{encodeURIComponent\(groupId\)\}\/items`, \{[\s\S]*method: 'POST'/)
  assert.match(api, /apiRequest\(`\/groups\/\$\{encodeURIComponent\(groupId\)\}\/items\/\$\{itemType\}\/\$\{encodeURIComponent\(itemId\)\}`, \{[\s\S]*method: 'DELETE'/)
})

test('group view shows both zones and the unpriced hint', async () => {
  const view = await read('src/views/GroupView.vue')
  assert.match(view, /getGroupDetail\(/)
  assert.match(view, /removeGroupItem\(/)
  assert.match(view, /未购买合计（购物车）/)
  assert.match(view, /已购买合计（物品库）/)
  assert.match(view, /未填价/)
  assert.match(view, /未计入合计/)
})

test('cart and library pages add items into a group through the shared picker', async () => {
  for (const name of ['src/views/CartView.vue', 'src/views/ItemsView.vue']) {
    const view = await read(name)
    assert.match(view, /GroupPickerModal/)
    assert.match(view, /openGroupPicker\(/)
  }
  const picker = await read('src/components/GroupPickerModal.vue')
  assert.match(picker, /addGroupItem\(/)
  assert.match(picker, /createGroup\(/)
})
