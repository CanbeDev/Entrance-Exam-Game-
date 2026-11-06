import { createHash } from 'node:crypto';

/** Preserve the existing CRLF-based text identifiers on LF and CRLF checkouts.
 * This is for declared text inputs only; binary/SVG identity hashes stay exact. */
export function textChecksum(text) {
  return createHash('sha256').update(text.replace(/\r\n?/g, '\n').replace(/\n/g, '\r\n')).digest('hex');
}
