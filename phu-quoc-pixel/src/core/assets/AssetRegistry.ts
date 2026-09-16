export type AssetType = 'image' | 'spritesheet' | 'audio';

export interface AssetRecord {
  key: string;
  type: AssetType;
  src: string;
  group: string;
  approved: boolean;
  width?: number;
  height?: number;
  frameWidth?: number;
  frameHeight?: number;
}

export class AssetRegistry {
  private readonly records = new Map<string, AssetRecord>();

  register(record: AssetRecord): void {
    if (this.records.has(record.key)) {
      throw new Error(`Duplicate asset key: ${record.key}`);
    }
    this.records.set(record.key, Object.freeze({ ...record }));
  }

  get(key: string): AssetRecord {
    const record = this.records.get(key);
    if (!record) throw new Error(`Unknown asset key: ${key}`);
    return record;
  }

  listGroup(group: string): AssetRecord[] {
    return [...this.records.values()].filter((record) => record.group === group);
  }

  has(key: string): boolean {
    return this.records.has(key);
  }
}

export const assetRegistry = new AssetRegistry();
