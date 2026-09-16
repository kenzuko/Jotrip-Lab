import Phaser from 'phaser';
import { SceneKeys } from '../app/scene-keys';

export class BootScene extends Phaser.Scene {
  constructor() {
    super(SceneKeys.Boot);
  }

  create(): void {
    this.scene.start(SceneKeys.Landing);
  }
}
