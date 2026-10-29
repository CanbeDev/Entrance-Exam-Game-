// Local development is loopback-only; no production target is inferred.
export function stripApiPrefix(path) {
  const stripped = path.replace(/^\/api(?=\/|\?|$)/, '') || '/';
  return stripped.startsWith('?') ? `/${stripped}` : stripped;
}

export function developmentProxy(target = 'http://127.0.0.1:8000') {
  const url = new URL(target);
  if (!['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
      || !['http:', 'https:'].includes(url.protocol) || url.username || url.password
      || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('Development API target must be a credential-free loopback origin');
  }
  return {
    '^/api(?:/|\\?|$)': {
      target: url.origin,
      changeOrigin: false,
      secure: true,
      rewrite: stripApiPrefix,
      // Do not rewrite Origin, Cookie, Set-Cookie, cookie Domain or Path.
    },
  };
}
