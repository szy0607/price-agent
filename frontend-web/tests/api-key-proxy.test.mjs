import assert from 'node:assert/strict'
import { once } from 'node:events'
import { readFile } from 'node:fs/promises'
import { createServer as createHttpServer } from 'node:http'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { createServer, loadConfigFromFile } from 'vite'

test('API key helpers reach the backend through the configured Vite proxy', async (t) => {
  const requests = []
  const backend = createHttpServer(async (request, response) => {
    let body = ''
    for await (const chunk of request) body += chunk
    requests.push({
      method: request.method,
      path: request.url,
      body: body ? JSON.parse(body) : null,
      writeHeader: request.headers['x-requested-with'],
    })
    response.writeHead(200, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify({ code: 0, data: { id: 42 } }))
  })
  t.after(() => new Promise((resolve) => backend.close(resolve)))
  backend.listen(0, '127.0.0.1')
  await once(backend, 'listening')

  const root = fileURLToPath(new URL('../', import.meta.url))
  const { config } = await loadConfigFromFile(
    { command: 'serve', mode: 'development' },
    fileURLToPath(new URL('../vite.config.js', import.meta.url)),
  )
  // Preserve the real proxy paths; redirect their targets to an isolated backend.
  const proxy = Object.fromEntries(Object.entries(config.server.proxy).map(([path, options]) => [
    path, { ...options, target: `http://127.0.0.1:${backend.address().port}` },
  ]))
  const vite = await createServer({
    ...config,
    configFile: false,
    root,
    logLevel: 'silent',
    server: { ...config.server, host: '127.0.0.1', port: 0, open: false, proxy },
  })
  t.after(() => vite.close())
  await vite.listen()

  const origin = `http://127.0.0.1:${vite.httpServer.address().port}`
  const source = await readFile(new URL('../src/utils/api.js', import.meta.url), 'utf8')
  const api = await import(`data:text/javascript;base64,${Buffer.from(
    source.replace('import.meta.env.VITE_API_BASE_URL', JSON.stringify(origin)) + '\n//# sourceURL=api-client-under-test.js',
  ).toString('base64')}`)
  const key = { provider: 'test', base_url: 'https://example.com', api_key: 'dummy-key', model_name: 'test-model' }

  assert.deepEqual(await api.listApiKeys(), { id: 42 })
  assert.deepEqual(await api.createApiKey(key), { id: 42 })
  assert.deepEqual(await api.updateApiKey(42, key), { id: 42 })
  assert.deepEqual(await api.deleteApiKey(42), { id: 42 })
  assert.deepEqual(await api.setDefaultApiKey(42), { id: 42 })
  assert.deepEqual(requests, [
    { method: 'GET', path: '/setting/api-keys', body: null, writeHeader: undefined },
    { method: 'POST', path: '/setting/api-keys', body: key, writeHeader: 'price-agent' },
    { method: 'PUT', path: '/setting/api-keys/42', body: key, writeHeader: 'price-agent' },
    { method: 'DELETE', path: '/setting/api-keys/42', body: null, writeHeader: 'price-agent' },
    { method: 'PUT', path: '/setting/api-keys/42/default', body: null, writeHeader: 'price-agent' },
  ])
})
