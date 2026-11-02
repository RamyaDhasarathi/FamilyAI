// Which stone design the app draws: the core gem, the five satellites and
// the mini gems all go through here.
//
//   'v1' = the original approved design (crystalRender.ts + crystalGeometry.ts,
//          kept unchanged; also tagged in git as `ui-v1-approved`)
//   'v2' = the refreshed design (crystalRenderV2.ts + stoneGeometryV2.ts)
//
// To go back to the older version, change STONE_STYLE to 'v1'. Nothing else
// in the app depends on the choice.
import { coreMesh as coreMeshV1, satelliteMeshes as satelliteMeshesV1 } from './crystalGeometry';
import { drawCrystal as drawCrystalV1 } from './crystalRender';
import { drawCrystalV2 } from './crystalRenderV2';
import { coreMeshV2, satelliteMeshesV2 } from './stoneGeometryV2';

export type StoneStyle = 'v1' | 'v2';

export const STONE_STYLE = 'v2' as StoneStyle;

export const drawStone = STONE_STYLE === 'v1' ? drawCrystalV1 : drawCrystalV2;
export const stoneSatelliteMeshes = STONE_STYLE === 'v1' ? satelliteMeshesV1 : satelliteMeshesV2;
export const stoneCoreMesh = STONE_STYLE === 'v1' ? coreMeshV1 : coreMeshV2;
