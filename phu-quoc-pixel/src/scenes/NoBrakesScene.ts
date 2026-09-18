import Phaser from 'phaser';
import { SceneKeys } from '../app/scene-keys';
import { assetRegistry } from '../core/assets/AssetRegistry';
import { inputActions } from '../core/input/InputActions';
import { flowController } from '../core/navigation/FlowController';
import { progressStore } from '../core/progress/ProgressStore';
import { createButton } from '../ui/createButton';

const GROUND_Y = 806;
const PLAYER_X = 104;
const GAME_ID = 'no-brakes';

interface Difficulty {
  speed: number;
  gapMin: number;
  gapMax: number;
}

export class NoBrakesScene extends Phaser.Scene {
  private player!: Phaser.GameObjects.Image;
  private obstacle!: Phaser.GameObjects.Image;
  private coin!: Phaser.GameObjects.Image;
  private scoreText!: Phaser.GameObjects.Text;
  private joText!: Phaser.GameObjects.Text;
  private bestText!: Phaser.GameObjects.Text;
  private speedText!: Phaser.GameObjects.Text;
  private toastText!: Phaser.GameObjects.Text;
  private tutorialLayer!: Phaser.GameObjects.Container;
  private resultLayer!: Phaser.GameObjects.Container;
  private resultText!: Phaser.GameObjects.Text;
  private roadDashes: Phaser.GameObjects.Rectangle[] = [];

  private running = false;
  private ended = false;
  private onGround = true;
  private velocityY = 0;
  private score = 0;
  private runJo = 0;
  private best = 0;
  private rideFrame = 0;
  private rideClock = 0;
  private obstaclePassed = false;
  private obstacleTraining = true;
  private obstaclesSpawned = 0;
  private trainingRescueUntil = 0;
  private toastUntil = 0;

  constructor() {
    super(SceneKeys.NoBrakes);
  }

  preload(): void {
    assetRegistry.queueGroup(this, 'no-brakes');
  }

  create(): void {
    const { width, height } = this.scale;
    this.cameras.main.setBackgroundColor('#08344a');

    this.add
      .image(width / 2, height / 2, 'sunset-background')
      .setDisplaySize(width, height);

    for (let i = 0; i < 7; i += 1) {
      this.roadDashes.push(
        this.add.rectangle(i * 94 + 20, 854, 50, 5, 0xd7c2a3, 0.36).setOrigin(0, 0.5)
      );
    }

    this.player = this.add
      .image(PLAYER_X, GROUND_Y, 'no-brakes-ride-01')
      .setOrigin(0.5, 1)
      .setDisplaySize(112, 154);

    this.obstacle = this.add
      .image(width + 180, GROUND_Y + 2, 'no-brakes-planter')
      .setOrigin(0.5, 1)
      .setDisplaySize(69, 76);

    this.coin = this.add
      .image(width + 320, 675, 'jo-coin')
      .setDisplaySize(42, 58);

    this.scoreText = this.hudText(18, 20, 'SCORE 0').setOrigin(0, 0);
    this.joText = this.hudText(width / 2, 20, 'JO 0').setOrigin(0.5, 0);
    this.bestText = this.hudText(width - 18, 20, 'BEST 0').setOrigin(1, 0);

    this.add
      .text(width / 2, 78, 'SUNSET TOWN', {
        fontFamily: 'monospace',
        fontSize: '13px',
        fontStyle: 'bold',
        color: '#fcbd22'
      })
      .setOrigin(0.5);

    this.add
      .text(width / 2, 102, 'NO BRAKES', {
        fontFamily: 'monospace',
        fontSize: '31px',
        fontStyle: 'bold',
        color: '#ffffff',
        stroke: '#16222b',
        strokeThickness: 5
      })
      .setOrigin(0.5);

    this.add
      .text(width / 2, 145, 'TAP · CLICK · SPACE', {
        fontFamily: 'monospace',
        fontSize: '11px',
        color: '#ffffff'
      })
      .setOrigin(0.5);

    this.speedText = this.add
      .text(width / 2, height - 34, '', {
        fontFamily: 'monospace',
        fontSize: '10px',
        color: '#dce9ec'
      })
      .setOrigin(0.5);

    this.toastText = this.add
      .text(width / 2, 190, '', {
        fontFamily: 'monospace',
        fontSize: '21px',
        fontStyle: 'bold',
        color: '#fcbd22',
        stroke: '#122733',
        strokeThickness: 4
      })
      .setOrigin(0.5)
      .setVisible(false);

    this.tutorialLayer = this.buildTutorial();
    this.resultLayer = this.buildResult();

    inputActions.bindPrimary(this, () => {
      if (this.running) this.jump();
    });
    inputActions.bindBack(this, () => {
      if (!this.running) flowController.go(this, SceneKeys.IslandMap);
    });

    this.prepareIdleState();
  }

  update(time: number, delta: number): void {
    if (!this.running) return;

    const dt = Math.min(delta / 1000, 0.034);
    const difficulty = this.difficulty();
    const speed = difficulty.speed;

    this.rideClock += delta;
    if (this.rideClock >= 95) {
      this.rideClock = 0;
      this.rideFrame = 1 - this.rideFrame;
      this.player.setTexture(this.rideFrame === 0 ? 'no-brakes-ride-01' : 'no-brakes-ride-02');
      this.player.setDisplaySize(112, 154);
    }

    if (!this.onGround) {
      this.velocityY += 2300 * dt;
      this.player.y += this.velocityY * dt;
      if (this.player.y >= GROUND_Y) {
        this.player.y = GROUND_Y;
        this.velocityY = 0;
        this.onGround = true;
      }
    }

    this.obstacle.x -= speed * dt;
    this.coin.x -= speed * 0.96 * dt;

    for (const dash of this.roadDashes) {
      dash.x -= speed * 1.25 * dt;
      if (dash.x < -70) dash.x += 7 * 94;
    }

    if (!this.obstaclePassed && this.obstacle.x + 36 < PLAYER_X - 40) {
      this.obstaclePassed = true;
      this.score += 1;
      this.scoreText.setText(`SCORE ${this.score}`);
      if (this.score === 1) this.toast('THAT\'S IT.');
      if (this.score === 5) this.toast('NOW WE RIDE.');
      if (this.score === 25) this.toast('FASTER!');
      this.spawnObstacle();
    }

    if (this.coin.x < -50) this.spawnCoin();

    if (this.overlapPlayerObstacle()) {
      if (this.obstacleTraining) {
        if (time >= this.trainingRescueUntil) {
          this.trainingRescueUntil = time + 450;
          this.jump(true);
          this.obstacle.x += 130;
          this.toast('HOP EARLIER!', 720);
        }
      } else {
        this.endRun();
        return;
      }
    }

    if (this.overlapPlayerCoin()) {
      this.runJo += 1;
      this.joText.setText(`JO ${this.runJo}`);
      this.toast('+1 JO', 430);
      this.spawnCoin();
    }

    if (time > this.toastUntil && this.toastText.visible) this.toastText.setVisible(false);

    this.speedText.setText(
      `${Math.floor(speed)} PX/S · ${this.score < 2 ? 'TRAINING' : this.score < 5 ? 'FAST START' : 'NO BRAKES'}`
    );
  }

  private hudText(x: number, y: number, text: string): Phaser.GameObjects.Text {
    return this.add.text(x, y, text, {
      fontFamily: 'monospace',
      fontSize: '18px',
      fontStyle: 'bold',
      color: '#ffffff',
      stroke: '#122733',
      strokeThickness: 4
    });
  }

  private buildTutorial(): Phaser.GameObjects.Container {
    const { width, height } = this.scale;
    const layer = this.add.container(0, 0);
    const shade = this.add.rectangle(width / 2, height / 2, width, height, 0x031721, 0.7);
    const panel = this.add.rectangle(width / 2, 480, 430, 390, 0x072f42, 0.97).setStrokeStyle(2, 0xfcbd22, 0.85);
    const eyebrow = this.add
      .text(width / 2, 348, 'FAST START · FRIENDLY FIRST', {
        fontFamily: 'monospace',
        fontSize: '12px',
        fontStyle: 'bold',
        color: '#8ff3a6'
      })
      .setOrigin(0.5);
    const title = this.add
      .text(width / 2, 395, 'NO BRAKES', {
        fontFamily: 'monospace',
        fontSize: '38px',
        fontStyle: 'bold',
        color: '#ffffff'
      })
      .setOrigin(0.5);
    const copy = this.add
      .text(width / 2, 474, 'THE SCOOTER MOVES FAST.\nTAP ONCE TO HOP.\n\nFIRST 2 OBSTACLES TEACH THE RHYTHM.\nTHEY CANNOT END YOUR RUN.', {
        fontFamily: 'monospace',
        fontSize: '13px',
        align: 'center',
        color: '#d7e7eb',
        lineSpacing: 7
      })
      .setOrigin(0.5);
    const start = createButton(this, width / 2, 610, 'START RIDE', () => this.startRun(), { width: 300, fontSize: 18 });
    const back = createButton(this, width / 2, 675, 'BACK TO MAP', () => flowController.go(this, SceneKeys.IslandMap), {
      width: 260,
      fontSize: 13,
      backgroundColor: '#164b61',
      color: '#ffffff'
    });
    layer.add([shade, panel, eyebrow, title, copy, start, back]);
    return layer;
  }

  private buildResult(): Phaser.GameObjects.Container {
    const { width, height } = this.scale;
    const layer = this.add.container(0, 0).setVisible(false);
    const shade = this.add.rectangle(width / 2, height / 2, width, height, 0x031721, 0.74);
    const panel = this.add.rectangle(width / 2, 480, 420, 360, 0x072f42, 0.98).setStrokeStyle(2, 0xfcbd22, 0.85);
    const eyebrow = this.add
      .text(width / 2, 355, 'SUNSET TOWN', {
        fontFamily: 'monospace',
        fontSize: '12px',
        fontStyle: 'bold',
        color: '#fcbd22'
      })
      .setOrigin(0.5);
    const title = this.add
      .text(width / 2, 400, 'GAME OVER', {
        fontFamily: 'monospace',
        fontSize: '36px',
        fontStyle: 'bold',
        color: '#ffffff'
      })
      .setOrigin(0.5);
    this.resultText = this.add
      .text(width / 2, 485, '', {
        fontFamily: 'monospace',
        fontSize: '15px',
        align: 'center',
        color: '#d7e7eb',
        lineSpacing: 8
      })
      .setOrigin(0.5);
    const retry = createButton(this, width / 2, 590, 'RETRY', () => this.startRun(), { width: 250, fontSize: 18 });
    const back = createButton(this, width / 2, 655, 'BACK TO MAP', () => flowController.go(this, SceneKeys.IslandMap), {
      width: 250,
      fontSize: 13,
      backgroundColor: '#164b61',
      color: '#ffffff'
    });
    layer.add([shade, panel, eyebrow, title, this.resultText, retry, back]);
    return layer;
  }

  private prepareIdleState(): void {
    this.best = progressStore.getProgress().bestScores[GAME_ID] ?? 0;
    this.bestText.setText(`BEST ${this.best}`);
    this.scoreText.setText('SCORE 0');
    this.joText.setText('JO 0');
    this.speedText.setText('READY');
    this.obstacle.setVisible(true);
    this.coin.setVisible(true);
    this.spawnObstacle(true);
    this.spawnCoin(true);
  }

  private startRun(): void {
    this.score = 0;
    this.runJo = 0;
    this.ended = false;
    this.onGround = true;
    this.velocityY = 0;
    this.player.y = GROUND_Y;
    this.rideFrame = 0;
    this.rideClock = 0;
    this.player.setTexture('no-brakes-ride-01').setDisplaySize(112, 154);
    this.obstaclesSpawned = 0;
    this.obstaclePassed = false;
    this.trainingRescueUntil = 0;
    this.best = progressStore.getProgress().bestScores[GAME_ID] ?? 0;
    this.scoreText.setText('SCORE 0');
    this.joText.setText('JO 0');
    this.bestText.setText(`BEST ${this.best}`);
    this.tutorialLayer.setVisible(false);
    this.resultLayer.setVisible(false);
    this.spawnObstacle(true);
    this.spawnCoin(true);
    this.running = true;
  }

  private endRun(): void {
    if (!this.running || this.ended) return;
    this.running = false;
    this.ended = true;
    if (this.runJo > 0) progressStore.addJo(this.runJo);
    this.best = progressStore.setBestScore(GAME_ID, this.score);
    this.bestText.setText(`BEST ${this.best}`);
    this.resultText.setText(`SCORE ${this.score} · JO +${this.runJo}\nBEST ${this.best}\n\n${this.score < 5 ? 'FAST GAME. TRY THE RHYTHM AGAIN.' : 'NICE RUN.'}`);
    this.resultLayer.setVisible(true);
  }

  private jump(auto = false): void {
    if (!this.running || !this.onGround) return;
    this.velocityY = -720;
    this.onGround = false;
    if (auto) this.player.setAngle(-4);
    this.time.delayedCall(130, () => this.player.setAngle(0));
  }

  private spawnObstacle(initial = false): void {
    const difficulty = this.difficulty();
    const gap = initial
      ? 190
      : Phaser.Math.Between(Math.floor(difficulty.gapMin), Math.floor(difficulty.gapMax));
    this.obstacle.x = this.scale.width + gap;
    this.obstacle.y = GROUND_Y + 2;
    this.obstaclePassed = false;
    this.obstacleTraining = this.obstaclesSpawned < 2;
    this.obstaclesSpawned += 1;
  }

  private spawnCoin(initial = false): void {
    this.coin.x = this.scale.width + (initial ? 360 : Phaser.Math.Between(260, 480));
    this.coin.y = Phaser.Math.Between(625, 700);
  }

  private overlapPlayerObstacle(): boolean {
    const p = this.player.getBounds();
    const o = this.obstacle.getBounds();
    const playerHit = new Phaser.Geom.Rectangle(p.x + 25, p.y + 20, Math.max(8, p.width - 45), Math.max(8, p.height - 25));
    const obstacleHit = new Phaser.Geom.Rectangle(o.x + 14, o.y + 12, Math.max(8, o.width - 28), Math.max(8, o.height - 14));
    return Phaser.Geom.Intersects.RectangleToRectangle(playerHit, obstacleHit);
  }

  private overlapPlayerCoin(): boolean {
    const p = this.player.getBounds();
    const c = this.coin.getBounds();
    const playerHit = new Phaser.Geom.Rectangle(p.x + 16, p.y + 8, Math.max(8, p.width - 32), Math.max(8, p.height - 16));
    return Phaser.Geom.Intersects.RectangleToRectangle(playerHit, c);
  }

  private difficulty(): Difficulty {
    if (this.score < 5) return { speed: 300, gapMin: 350, gapMax: 420 };
    if (this.score < 15) return { speed: 335, gapMin: 320, gapMax: 385 };
    if (this.score < 35) return { speed: 375, gapMin: 285, gapMax: 345 };
    if (this.score < 60) return { speed: 415, gapMin: 255, gapMax: 315 };
    return {
      speed: 455 + Math.min(65, (this.score - 60) * 1.4),
      gapMin: 225,
      gapMax: 285
    };
  }

  private toast(message: string, duration = 650): void {
    this.toastText.setText(message).setVisible(true);
    this.toastUntil = this.time.now + duration;
  }
}
