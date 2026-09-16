import Phaser from 'phaser';
import { SceneKeys } from '../app/scene-keys';
import { flowController } from '../core/navigation/FlowController';
import { createButton } from '../ui/createButton';

export class NoBrakesScene extends Phaser.Scene {
  constructor() {
    super(SceneKeys.NoBrakes);
  }

  create(): void {
    const { width } = this.scale;
    this.cameras.main.setBackgroundColor('#392d25');

    this.add
      .text(width / 2, 220, 'SUNSET TOWN', {
        fontFamily: 'monospace',
        fontSize: '18px',
        color: '#fcbd22'
      })
      .setOrigin(0.5);

    this.add
      .text(width / 2, 300, 'NO BRAKES', {
        fontFamily: 'monospace',
        fontSize: '46px',
        fontStyle: 'bold',
        color: '#ffffff'
      })
      .setOrigin(0.5);

    this.add
      .text(width / 2, 430, 'MODULE BOUNDARY READY\nGAMEPLAY NOT MIGRATED YET', {
        fontFamily: 'monospace',
        fontSize: '16px',
        align: 'center',
        color: '#d7c3aa',
        lineSpacing: 8
      })
      .setOrigin(0.5);

    createButton(this, width / 2, 650, 'BACK TO MAP', () => {
      flowController.go(this, SceneKeys.IslandMap);
    });
  }
}
