import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { parse as parseSfc } from 'vue/compiler-sfc'

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), 'utf8')

test('price comparison is an explicit local demo and has no price API dependency', async () => {
  const source = await read('src/views/CompareView.vue')

  assert.match(source, /演示数据/)
  assert.match(source, /非实时/)
  assert.doesNotMatch(source, /from ['"]\.\.\/utils\/api/)
  assert.doesNotMatch(source, /fetch\s*\(/)
})

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

test('comparison page exposes a local JSON and CSV product library demo', async () => {
  const source = await read('src/views/CompareView.vue')

  assert.match(source, /自定义商品库 Demo/)
  assert.match(source, /accept=["]\.json,\.csv/)
  assert.match(source, /handleLibraryUpload/)
  assert.match(source, /本地解析/)
})

test('product library parser normalizes JSON and CSV prices', async () => {
  const { parseProductLibrary } = await import('../src/utils/productLibrary.js')
  const fallbackImages = ['/fallback.jpg']
  const json = JSON.stringify([{ name: '测试耳机', taobao_price: 299, jd_price: 289, pdd_price: 279 }])
  const csv = 'name,category,brand,model,sku,taobao_price,jd_price,pdd_price\n测试水杯,家居,示例品牌,X1,蓝色,99,89,79'

  const [jsonProduct] = parseProductLibrary(json, { fileName: 'products.json', fallbackImages })
  const [csvProduct] = parseProductLibrary(csv, { fileName: 'products.csv', fallbackImages })

  assert.equal(jsonProduct.skus[0].prices.jd.b, 289)
  assert.equal(csvProduct.name, '测试水杯')
  assert.equal(csvProduct.skus[0].prices.pdd.b, 79)
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
  assert.ok(viewNames.length >= 10, `router 里只找到 ${viewNames.length} 个懒加载视图`)

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
