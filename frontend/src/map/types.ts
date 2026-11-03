import type { PublicCountry, PublicParticipant } from '../api/index.ts';
import type { Point } from './geometry.ts';

export type AtlasCountry = Pick<PublicCountry, 'id' | 'name' | 'soldiers' | 'owner_id'>;
export type AtlasParticipant = PublicParticipant;
export interface CountryMapEntry { id: string; name: string; groupKey: string | null; anchor: Point; missingShape: boolean }
export interface MapData {
  viewBox: number[];
  paths: { d: string; groupKey: string }[];
  groups: { key: string; canonicalId: string | null; pathIndices: number[] }[];
  countries: CountryMapEntry[];
}
export interface AtlasProps {
  countries: readonly AtlasCountry[];
  players: readonly AtlasParticipant[];
  turnOrder: readonly string[];
  onSelect: (countryId: string) => void;
  selectedId?: string | null;
  fromId?: string | null;
  targetId?: string | null;
  playingId?: string | null;
  battle?: { source_id: string; target_id: string; preview: boolean } | null;
  /** Optional fixed viewport for reproducible local fixtures/SSR. Browser otherwise measures its container. */
  viewportWidth?: number;
  /** Shells can place the same accessible roster separately. Defaults to inline. */
  showRoster?: boolean;
  /** Presentation-only feedback for a newly observed committed conquest. */
  capturedIds?: readonly string[];
  onCaptureSettled?: (countryId: string) => void;
}
