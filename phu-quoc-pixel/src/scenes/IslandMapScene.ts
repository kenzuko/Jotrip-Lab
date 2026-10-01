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
      .text(width / 2, 48, `WELCOME, ${profile.displayName.toUpperCase()}`, {
        fontFamily: 'monospace',
        fontSize: '17px',
        color: '#fcbd22'
      })
      .setOrigin(0.5);

    this.add
      .text(width / 2, 88, 'PHU QUOC ISLAND MAP', {
        fontFamily: 'monospace',
        fontSize: '27px',
        fontStyle: 'bold',
        color: '#ffffff'
      })
      .setOrigin(0.5);

    this.add
      .text(width / 2, 130, `JO ${progress.totalJo} · CHARACTER ${profile.characterId.toUpperCase()}`, {
        fontFamily: 'monospace',
        fontSize: '12px',
        color: '#d5eef5'
      })
      .setOrigin(0.5);

    const mapWidth = 360;
    const mapHeight = mapWidth * (293 / 240);
    const mapLeft = width / 2 - mapWidth / 2;
    const mapTop = 180;

    this.add
      .rectangle(width / 2, mapTop + mapHeight / 2, mapWidth + 24, mapHeight + 24, 0x06394b, 0.78)
      .setStrokeStyle(2, 0xf3dfaa, 0.35);

    this.add
      .image(width / 2, mapTop + mapHeight / 2, 'island-map')
      .setDisplaySize(mapWidth, mapHeight);

    let notice: Phaser.GameObjects.Text | undefined;

    ISLAND_LOCATIONS.forEach((location) => {
      const x = mapLeft + location.mapPosition.x * mapWidth;
      const y = mapTop + location.mapPosition.y * mapHeight;
      const available = location.status === 'available';

      const pin = this.add.circle(x, y, available ? 14 : 9, available ? 0xfcbd22 : 0x31565d);
      pin.setStrokeStyle(2, available ? 0xffffff : 0x78949b, 0.9);

      const label = this.add
        .text(x, y + 17, location.label, {
          fontFamily: 'monospace',
          fontSize: available ? '11px' : '8px',
          fontStyle: 'bold',
          color: available ? '#ffffff' : '#c4d7da',
          backgroundColor: '#06394bd9',
          padding: { x: 4, y: 3 }
        })
        .setOrigin(0.5, 0);

      if (available) {
        pin.setInteractive({ useHandCursor: true });
        label.setInteractive({ useHandCursor: true });
        const open = (): void => {
          if (notice) notice.destroy();
          notice = this.add
            .text(width / 2, 690, 'SUNSET TOWN · NO BRAKES', {
              fontFamily: 'monospace',
              fontSize: '16px',
              fontStyle: 'bold',
              color: '#05263a',
              backgroundColor: '#fcbd22',
              padding: { x: 15, y: 10 }
            })
            .setOrigin(0.5);

          this.time.delayedCall(220, () => flowController.go(this, SceneKeys.NoBrakes));
        };
        pin.on('pointerdown', open);
        label.on('pointerdown', open);
      }
    });

    this.add
      .text(width / 2, 742, 'ONE LOCATION OPEN · MORE ISLAND STORIES LATER', {
        fontFamily: 'monospace',
        fontSize: '10px',
        color: '#bfe0e7'
      })
      .setOrigin(0.5);

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
