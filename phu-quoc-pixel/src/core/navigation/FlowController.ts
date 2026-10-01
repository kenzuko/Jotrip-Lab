import Phaser from 'phaser';
import { SceneKeys, type SceneKey } from '../../app/scene-keys';

const allowedTransitions: Readonly<Record<SceneKey, readonly SceneKey[]>> = {
  [SceneKeys.Boot]: [SceneKeys.Landing],
  [SceneKeys.Landing]: [SceneKeys.Airport],
  [SceneKeys.Airport]: [SceneKeys.Character, SceneKeys.Landing],
  [SceneKeys.Character]: [SceneKeys.IslandMap, SceneKeys.Airport],
  [SceneKeys.IslandMap]: [SceneKeys.Character, SceneKeys.NoBrakes],
  [SceneKeys.NoBrakes]: [SceneKeys.Result, SceneKeys.IslandMap],
  [SceneKeys.Result]: [SceneKeys.NoBrakes, SceneKeys.IslandMap]
};

export class FlowController {
  canGo(from: SceneKey, to: SceneKey): boolean {
    return allowedTransitions[from].includes(to);
  }

  go(scene: Phaser.Scene, to: SceneKey, data?: object): void {
    const from = scene.sys.settings.key as SceneKey;
    if (!this.canGo(from, to)) {
      throw new Error(`Blocked scene transition: ${from} -> ${to}`);
    }
    scene.scene.start(to, data);
  }
}

export const flowController = new FlowController();
