# ASSET INVENTORY - CURRENT PROTOTYPE

Source reviewed: `/game-rebuild/asset-bridge.js` plus `/preview/asset-*.js`.

Purpose: identify what is real reusable artwork, what is embedded prototype data, and what is only a generated placeholder before migration into the new AssetRegistry.

## Current reusable embedded asset groups

The old prototype exposes these assets through `window.A` and bridges them into `PQ_ASSETS`:

| New logical group | Current key | Current source | Migration status |
|---|---|---|---|
| world-map | `island` | `A.map` from `preview/asset-map.js` | inspect and migrate |
| location-sunset-town | `sunset-bg` | `A.bg` from `preview/asset-bg.js` | inspect and migrate |
| minigame-no-brakes | `ride1` | `A.ride1` from `preview/asset-rides.js` | inspect and migrate |
| minigame-no-brakes | `ride2` | `A.ride2` from `preview/asset-rides.js` | inspect and migrate |
| minigame-no-brakes | `ride3` | `A.ride3` from `preview/asset-rides.js` | inspect and migrate |
| minigame-no-brakes | `ride4` | `A.ride4` from `preview/asset-rides.js` | inspect and migrate |
| minigame-no-brakes | `planter` | `A.planter` from `preview/asset-props.js` | inspect and migrate |
| minigame-no-brakes | `chair` | `A.chair` from `preview/asset-props.js` | inspect and migrate |
| minigame-no-brakes | `table` | `A.table` from `preview/asset-props.js` | inspect and migrate |
| minigame-no-brakes | `menu` | `A.menu` from `preview/asset-props.js` | inspect and migrate |
| minigame-no-brakes | `tripod` | `A.tripod` from `preview/asset-props.js` | inspect and migrate |
| minigame-no-brakes | `suitcase` | `A.suitcase` from `preview/asset-props.js` | inspect and migrate |
| minigame-no-brakes | `coin` | `A.coin` from `preview/asset-props.js` | inspect and migrate |

Current prototype container sizes:

- `preview/asset-bg.js`: about 17 KB
- `preview/asset-map.js`: about 8 KB
- `preview/asset-props.js`: about 7 KB
- `preview/asset-rides.js`: about 14 KB

These are JavaScript wrappers containing embedded image data. The clean rebuild must extract actual image files into `public/assets/...` rather than keep base64 assets inside JavaScript modules.

## Current generated placeholders - do not treat as approved art

The current `asset-bridge.js` generates SVG placeholders at runtime for:

- Traveler
- Explorer
- Uncle
- Grandma
- Kid
- Old Fisherman
- Phu Quoc Ridgeback
- Pepper
- Ken
- airplane
- airport scene

These are implementation placeholders, not evidence that approved final artwork exists.

Migration rule:

1. If an approved original asset exists elsewhere, migrate the original.
2. If no approved original exists, keep the new scene visually neutral and mark the asset `placeholder: true`.
3. Never silently convert a generated placeholder into a final production asset.

## AssetRegistry target shape

Each migrated asset must have metadata similar to:

```ts
{
  key: 'sunset-town.background.main',
  type: 'image',
  src: './assets/locations/sunset-town/background-main.webp',
  group: 'location-sunset-town',
  width: 540,
  height: 960,
  approved: true
}
```

Dimensions above are illustrative until the original image is inspected.

## Loading policy

- `core-ui`: boot only
- `location-airport`: background load after landing is usable
- `characters`: background load during airport scene
- `world-map`: load before Island Map
- `location-sunset-town`: load after map is available or on location intent
- `minigame-no-brakes`: load only when Sunset Town is selected

No file from a future location is loaded during the first vertical slice.

## Next migration gate

Before artwork enters the clean rebuild:

- extract actual files from embedded wrappers
- measure real dimensions and byte size
- visually compare against the approved reference
- assign stable keys
- place in a named asset group
- verify nearest-neighbor rendering where required
- ensure no aspect-ratio distortion
