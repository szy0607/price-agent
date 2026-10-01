import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

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

test('the settings page never blocks mount on a provider model listing', async () => {
  const source = await read('src/views/SettingsView.vue')
  const loadKeys = source.match(/async function loadKeys\(\)[\s\S]*?\n\}/)

  assert.ok(loadKeys, 'loadKeys not found')
  // 拉模型列表要走服务商，挂在 @change 上按需触发；挂载时只读本地接口
  assert.doesNotMatch(loadKeys[0], /listProviderModels/)
  assert.match(loadKeys[0], /Promise\.all\(\[listApiKeys\(\), getModelSetting\(\)\]\)/)
  assert.match(source, /@change="onProviderChange\(selectedModelProvider\)"/)
})

test('model listing and selection go through the guarded client calls', async () => {
  const api = await read('src/utils/api.js')
  const listing = api.match(/export function listProviderModels\(provider\)[\s\S]*?\n\}/)
  const setting = api.match(/export function setModelSetting\(provider, modelName = null\)[\s\S]*?\n\}/)

  assert.ok(listing && setting, 'api.js helpers not found')
  // apiRequest 只在非 GET 时自动注入同源头；这个 GET 会解密用户 Key，必须手动带上
  assert.match(listing[0], /'X-Requested-With': 'price-agent'/)
  assert.match(setting[0], /JSON\.stringify\(\{ provider, model_name: modelName \}\)/)
})

test('the model select always offers the saved choice and the provider default', async () => {
  const source = await read('src/views/SettingsView.vue')
  const choices = source.match(/const availableModels = computed\(\(\) => \{[\s\S]*?\n\}\)/)

  assert.ok(choices, 'availableModels not found')
  assert.match(choices[0], /selectedModelName\.value/)
  assert.match(choices[0], /（已保存）/)
  assert.match(choices[0], /（服务商默认）/)
  // 提交条件必须同时比对厂商和模型，否则「同一厂商换个模型」这个主场景会是禁用状态
  assert.match(source, /selectedModelProvider === modelSetting\.provider && selectedModelName === storedModelName/)
})
