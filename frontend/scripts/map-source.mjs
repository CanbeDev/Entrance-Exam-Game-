// Strict parser for the audited SVG subset, not a general XML/HTML importer.
const rootAttributes = new Set(['xmlns', 'baseprofile', 'baseProfile', 'fill', 'height', 'width', 'stroke',
  'stroke-linecap', 'stroke-linejoin', 'stroke-width', 'version', 'viewbox', 'viewBox']);
function attributes(text) {
  const result = {};
  let rest = text.trim();
  while (rest) {
    const match = /^([A-Za-z_][\w:.-]*)\s*=\s*("[^"<>]*"|'[^'<>]*')\s*/.exec(rest);
    if (!match || Object.hasOwn(result, match[1])) throw new Error('Malformed or duplicate XML attribute');
    const raw = match[2].slice(1, -1);
    if (/&(?!(?:amp|lt|gt|quot|apos);)/.test(raw)) throw new Error('Unsupported XML entity');
    result[match[1]] = raw.replace(/&(amp|lt|gt|quot|apos);/g,
      (_, key) => ({ amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" })[key]);
    rest = rest.slice(match[0].length);
  }
  return result;
}

export function parseMapSvg(source) {
  if (/<!DOCTYPE|<!ENTITY|<!\[CDATA\[/i.test(source)) throw new Error('Unsupported XML declaration');
  const tokens = source.match(/<!--[\s\S]*?-->|<\?[\s\S]*?\?>|<[^>]*>|[^<]+/g) ?? [];
  if (tokens.join('') !== source) throw new Error('Malformed XML');
  const stack = [], paths = [], circles = [], ids = new Set();
  let root, closed = false, licenseNotice;
  for (const token of tokens) {
    if (token.startsWith('<!--')) {
      if (token.slice(4, -3).includes('--')) throw new Error('Malformed comment');
      if (token.includes('The MIT License (MIT)') && token.includes('Simplemaps.com')) licenseNotice = token;
      continue;
    }
    if (token.startsWith('<?')) {
      if (root || !/^<\?xml\s+version="1\.0"\s*\?>$/.test(token)) throw new Error('Unsupported processing instruction');
      continue;
    }
    if (!token.startsWith('<')) { if (token.trim()) throw new Error('Unexpected SVG text'); continue; }
    const closing = /^<\/([A-Za-z]+)\s*>$/.exec(token);
    if (closing) {
      if (stack.pop() !== closing[1]) throw new Error('Mismatched XML closing tag');
      if (closing[1] === 'svg') closed = true;
      continue;
    }
    const open = /^<([A-Za-z]+)\s*([\s\S]*?)(\/?)>$/.exec(token);
    if (!open || closed) throw new Error('Unsupported SVG markup');
    const [, tag, raw, slash] = open, attrs = attributes(raw);
    if (tag === 'svg') {
      if (root || stack.length || slash) throw new Error('Invalid SVG root');
      if (Object.keys(attrs).some((key) => !rootAttributes.has(key))) throw new Error('Unsafe root attribute');
      if (attrs.xmlns !== 'http://www.w3.org/2000/svg') throw new Error('Invalid SVG namespace');
      if (!/^#[0-9a-f]{6}$/i.test(attrs.fill ?? '') || !/^(?:black|#[0-9a-f]{6})$/i.test(attrs.stroke ?? '')
        || attrs['stroke-linecap'] !== 'round' || attrs['stroke-linejoin'] !== 'round'
        || !/^(?:\d+)?\.\d+$/.test(attrs['stroke-width'] ?? '') || Number(attrs['stroke-width']) > 10) throw new Error('Unsupported paint/stroke');
      root = attrs;
    } else {
      if (stack.length !== 1 || stack[0] !== 'svg' || !['path', 'circle'].includes(tag)) throw new Error('Unsupported SVG element');
      const allowed = tag === 'path' ? ['d', 'id', 'name', 'class'] : ['cx', 'cy', 'id'];
      if (Object.keys(attrs).some((key) => !allowed.includes(key))) throw new Error('Unsafe SVG attribute');
      if (attrs.id) { if (ids.has(attrs.id)) throw new Error('Duplicate SVG id'); ids.add(attrs.id); }
      if (tag === 'path') {
        if (!attrs.d || !(attrs.id && attrs.name || attrs.class) || attrs.id && attrs.class) throw new Error('Unidentified path');
        paths.push({ d: attrs.d, key: attrs.id ?? attrs.class, name: attrs.name ?? attrs.class });
      } else {
        if (![attrs.cx, attrs.cy].every((v) => v !== undefined && Number.isFinite(Number(v)))) throw new Error('Invalid authoring circle');
        circles.push(attrs); // Audited zero-radius authoring markers, not country geometry.
      }
    }
    if (!slash) stack.push(tag);
  }
  if (!root || !closed || stack.length || !licenseNotice) throw new Error('Incomplete SVG or missing bundled licence');
  if (root.viewBox && root.viewbox) throw new Error('Ambiguous viewport');
  const viewBox = (root.viewBox ?? root.viewbox ?? '').split(/\s+/).map(Number);
  if (viewBox.join(' ') !== '0 0 2000 857' || root.width !== '2000' || root.height !== '857') throw new Error('Unexpected viewport');
  return { viewBox, paths, circles, licenseNotice };
}
