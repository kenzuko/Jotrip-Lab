import Phaser from 'phaser';
import { SceneKeys } from '../app/scene-keys';
import { assetRegistry } from '../core/assets/AssetRegistry';

export class BootScene extends Phaser.Scene {
  constructor() {
    super(SceneKeys.Boot);
  }

  preload(): void {
    assetRegistry.queueGroup(this, 'shell-map');
  }

  create(): void {
    this.scene.start(SceneKeys.Landing);
  }
}
