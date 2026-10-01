import Phaser from 'phaser';

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

  queueGroup(scene: Phaser.Scene, group: string): void {
    for (const record of this.listGroup(group)) {
      if (!record.approved) continue;

      if (record.type === 'image') {
        if (!scene.textures.exists(record.key)) scene.load.image(record.key, record.src);
        continue;
      }

      if (record.type === 'spritesheet') {
        if (scene.textures.exists(record.key)) continue;
        if (!record.frameWidth || !record.frameHeight) {
          throw new Error(`Spritesheet ${record.key} is missing frame dimensions`);
        }
        scene.load.spritesheet(record.key, record.src, {
          frameWidth: record.frameWidth,
          frameHeight: record.frameHeight
        });
        continue;
      }

      if (!scene.cache.audio.exists(record.key)) scene.load.audio(record.key, record.src);
    }
  }
}

export const assetRegistry = new AssetRegistry();
