export type LocationStatus = 'available' | 'locked' | 'coming-soon';

export interface IslandLocation {
  id: string;
  label: string;
  mapPosition: { x: number; y: number };
  status: LocationStatus;
  miniGameId?: string;
  assetGroup?: string;
}

export const ISLAND_LOCATIONS: readonly IslandLocation[] = Object.freeze([
  {
    id: 'sunset-town',
    label: 'SUNSET TOWN',
    mapPosition: { x: 0.31, y: 0.72 },
    status: 'available',
    miniGameId: 'no-brakes',
    assetGroup: 'location-sunset-town'
  },
  {
    id: 'hon-thom',
    label: 'HON THOM',
    mapPosition: { x: 0.49, y: 0.91 },
    status: 'locked'
  },
  {
    id: 'bai-sao',
    label: 'BAI SAO',
    mapPosition: { x: 0.63, y: 0.67 },
    status: 'locked'
  },
  {
    id: 'night-market',
    label: 'NIGHT MARKET',
    mapPosition: { x: 0.39, y: 0.49 },
    status: 'locked'
  },
  {
    id: 'grand-world',
    label: 'GRAND WORLD',
    mapPosition: { x: 0.35, y: 0.24 },
    status: 'locked'
  },
  {
    id: 'safari',
    label: 'SAFARI',
    mapPosition: { x: 0.44, y: 0.17 },
    status: 'locked'
  }
]);
