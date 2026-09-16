import Phaser from 'phaser';
import { SceneKeys } from '../app/scene-keys';
import { flowController } from '../core/navigation/FlowController';
import { progressStore } from '../core/progress/ProgressStore';
import { ISLAND_LOCATIONS } from '../world/locations';
import { createButton } from '../ui/createButton';

export class IslandMapScene extends Phaser.Scene {
  constructor() {
    super(SceneKeys.IslandMap);
  }

  create(): void {
    const { width, height } = this.scale;
    this.cameras.main.setBackgroundColor('#0d6d89');

    const profile = progressStore.getProfile();
    const progress = progressStore.getProgress();

    this.add
      .text(width / 2, 55, `WELCOME, ${profile.displayName.toUpperCase()}`, {
        fontFamily: 'monospace',
        fontSize: '18px',
        color: '#fcbd22'
      })
      .setOrigin(0.5);

    this.add
      .text(width / 2, 95, 'PHU QUOC ISLAND MAP', {
        fontFamily: 'monospace',
        fontSize: '27px',
        fontStyle: 'bold',
        color: '#ffffff'
      })
      .setOrigin(0.5);

    this.add
      .text(width / 2, 137, `JO ${progress.totalJo} · CHARACTER ${profile.characterId.toUpperCase()}`, {
        fontFamily: 'monospace',
        fontSize: '12px',
        color: '#d5eef5'
      })
      .setOrigin(0.5);

    this.add.ellipse(width / 2, 480, 270, 560, 0x6f934f).setStrokeStyle(8, 0xf3dfaa, 0.7);

    const mapLeft = width / 2 - 135;
    const mapTop = 200;
    const mapWidth = 270;
    const mapHeight = 560;

    let notice: Phaser.GameObjects.Text | undefined;

    ISLAND_LOCATIONS.forEach((location) => {
      const x = mapLeft + location.mapPosition.x * mapWidth;
      const y = mapTop + location.mapPosition.y * mapHeight;
      const available = location.status === 'available';

      const pin = this.add.circle(x, y, available ? 15 : 10, available ? 0xfcbd22 : 0x31565d);
      const label = this.add
        .text(x, y + 20, location.label, {
          fontFamily: 'monospace',
          fontSize: available ? '12px' : '9px',
          fontStyle: 'bold',
          color: available ? '#ffffff' : '#b8ced3',
          backgroundColor: '#06394bcc',
          padding: { x: 4, y: 3 }
        })
        .setOrigin(0.5, 0);

      if (available) {
        pin.setInteractive({ useHandCursor: true });
        label.setInteractive({ useHandCursor: true });
        const open = (): void => {
          if (notice) notice.destroy();
          notice = this.add
            .text(width / 2, 805, 'SUNSET TOWN · NO BRAKES', {
              fontFamily: 'monospace',
              fontSize: '17px',
              fontStyle: 'bold',
              color: '#05263a',
              backgroundColor: '#fcbd22',
              padding: { x: 15, y: 10 }
            })
            .setOrigin(0.5);

          this.time.delayedCall(260, () => flowController.go(this, SceneKeys.NoBrakes));
        };
        pin.on('pointerdown', open);
        label.on('pointerdown', open);
      }
    });

    createButton(
      this,
      105,
      height - 45,
      'CHARACTER',
      () => flowController.go(this, SceneKeys.Character),
      { width: 165, fontSize: 13, backgroundColor: '#164b61', color: '#ffffff' }
    );
  }
}
