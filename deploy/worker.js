import { DurableObject } from 'cloudflare:workers'

const CONTAINER_ENV = [
  'DEMO_CUSTOMER_ID', 'CHAT_PROVIDER', 'ANTHROPIC_API_KEY', 'ANTHROPIC_MODEL',
  'ANTHROPIC_WORKSPACE_ID', 'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_MODEL',
  'OPENAI_EXTRA_HEADERS', 'TYPESAFE_API_KEY', 'TYPESAFE_MODEL',
]

export class AinoMoneyBackend extends DurableObject {
  starting

  async fetch(request) {
    const container = this.ctx.container
    const port = container.getTcpPort(8080)
    this.starting ??= this.waitUntilReady(container, port).finally(() => { this.starting = undefined })
    await this.starting

    const url = new URL(request.url)
    url.protocol = 'http:'
    url.host = 'container'
    url.pathname = url.pathname.slice('/api'.length) || '/'
    const forwarded = new Request(url, request)
    forwarded.headers.delete('host')
    return port.fetch(forwarded)
  }

  async waitUntilReady(container, port) {
    if (!container.running) {
      const envVars = {}
      for (const key of CONTAINER_ENV) {
        if (this.env[key]) envVars[key] = this.env[key]
      }
      container.start({ image: container.images.base, instance: 'basic', enableInternet: true, envVars })
      await container.setInactivityTimeout(5 * 60 * 1000)
    }

    for (let attempt = 0; attempt < 100; attempt++) {
      try {
        const response = await port.fetch('http://container/health', { signal: AbortSignal.timeout(1000) })
        await response.body?.cancel()
        if (response.ok) return
      } catch {
        // The application may still be starting.
      }
      await scheduler.wait(250)
    }
    throw new Error('Aino Money backend did not become ready')
  }
}

export default {
  fetch(request, env) {
    const path = new URL(request.url).pathname
    if (path === '/api' || path.startsWith('/api/')) {
      return env.BACKEND.getByName('demo').fetch(request)
    }
    return env.ASSETS.fetch(request)
  },
}
