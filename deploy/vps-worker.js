export default {
  fetch(request, env) {
    const url = new URL(request.url)
    if (url.pathname.startsWith('/api/')) {
      const origin = new URL('http://127.0.0.1:8080')
      origin.pathname = url.pathname
      origin.search = url.search
      return env.AINO_MONEY_ORIGIN.fetch(new Request(origin, request))
    }
    return env.ASSETS.fetch(request)
  },
}
