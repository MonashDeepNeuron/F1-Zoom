import * as THREE from "three";
import {
  CIRCUIT_THEME,
  buildScaledPoints,
  getTrackLayout,
  hexToNumber,
  parseTrackData,
  projectRawPointToScene,
  type TrackLayout,
  type TrackPoint,
} from "./trackScene";

export interface BuiltCircuitScene {
  /** The Three.js scene with all track geometry, lights, and decoration added. */
  scene: THREE.Scene;
  /** Track layout used to scale + centre the geometry. */
  layout: TrackLayout;
  /** Raw CSV-space points (handy for drawing turn markers, etc.). */
  rawPoints: TrackPoint[];
  /** Y elevation of the track surface (use for camera lookAt). */
  trackElevation: number;
  /**
   * Per-frame animation tick. Drives light pulsing, glow opacity,
   * and emissive breathing on the track. `elapsedSec` is monotonically
   * increasing seconds (e.g. `performance.now() * 0.001`).
   */
  tick: (elapsedSec: number) => void;
  /** Project a raw CSV (x, y) point into scene space (x, z). */
  project: (raw: { x: number; y: number }) => { x: number; z: number };
  /** Dispose all geometries, materials, and textures owned by the scene. */
  dispose: () => void;
}

export interface BuildCircuitSceneArgs {
  /** Target scene to add geometry/lights to. A fresh `THREE.Scene` is
   * created if this is omitted. */
  scene?: THREE.Scene;
  /** Raw text of a TrackCoordinateJS file (or the underlying CSV). */
  csvText: string;
  /** Theme key matching `CIRCUIT_THEME`. Falls back to DEFAULT. */
  themeKey?: string | null;
  /** Track length in km (used to size the projection). */
  lengthKm?: number | null;
}

const TRACK_ELEVATION = 2.5;
const SHADOW_Y = TRACK_ELEVATION - 1.4;
const MARKER_Y = TRACK_ELEVATION + 2.4;

function makeTurnLabel(
  num: number,
  textColor: string,
): { sprite: THREE.Sprite; texture: THREE.CanvasTexture; material: THREE.SpriteMaterial } {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;

  ctx.beginPath();
  ctx.arc(size / 2, size / 2, 56, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(255, 34, 0, 0.12)";
  ctx.fill();

  ctx.beginPath();
  ctx.arc(size / 2, size / 2, 38, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(12, 0, 0, 0.92)";
  ctx.fill();
  ctx.strokeStyle = textColor;
  ctx.lineWidth = 4;
  ctx.stroke();

  const fontSize = num >= 10 ? 34 : 42;
  ctx.fillStyle = textColor;
  ctx.font = `bold ${fontSize}px Arial`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(String(num), size / 2, size / 2 + 2);

  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
  });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(2.0, 2.0, 1);
  return { sprite, texture, material };
}

/**
 * Build the canonical CircuitHero scene (track + walls + glow layers + turn
 * markers + grid + lights + breathing). Used by both `CircuitHero` and the
 * landing intro so they render identically.
 *
 * The caller owns the camera, animation loop, and renderer; this helper
 * only builds the scene contents and returns a per-frame `tick` for the
 * pulsing/breathing material updates.
 */
export function buildCircuitScene({
  scene: passedScene,
  csvText,
  themeKey,
  lengthKm,
}: BuildCircuitSceneArgs): BuiltCircuitScene {
  const scene = passedScene ?? new THREE.Scene();
  if (!passedScene) {
    scene.background = new THREE.Color(0x000000);
    scene.fog = new THREE.Fog(0x000000, 30, 100);
  }

  const theme = CIRCUIT_THEME[themeKey ?? ""] ?? CIRCUIT_THEME.DEFAULT;
  const accentColor = theme.text;

  // Collect everything we own so callers get a clean dispose().
  const geometries: THREE.BufferGeometry[] = [];
  const materials: THREE.Material[] = [];
  const textures: THREE.Texture[] = [];

  // ── Lighting (subtle — most colour comes from emissive materials) ──
  scene.add(new THREE.AmbientLight(0xffffff, 0.08));

  const pointLight1 = new THREE.PointLight(hexToNumber(theme.primary), 1.2, 60);
  pointLight1.position.set(0, 25, 0);
  scene.add(pointLight1);

  const pointLight2 = new THREE.PointLight(hexToNumber(theme.glow), 0.6, 50);
  pointLight2.position.set(20, 15, 20);
  scene.add(pointLight2);

  const pointLight3 = new THREE.PointLight(0xff4400, 0.4, 40);
  pointLight3.position.set(-20, 12, -20);
  scene.add(pointLight3);

  const sideLight1 = new THREE.PointLight(0xff1100, 0.5, 50);
  sideLight1.position.set(25, 10, 0);
  scene.add(sideLight1);

  const sideLight2 = new THREE.PointLight(0xff1100, 0.5, 50);
  sideLight2.position.set(-25, 10, 0);
  scene.add(sideLight2);

  // ── Track geometry ────────────────────────────────────────────────
  const rawPoints = parseTrackData(csvText);
  const layout = getTrackLayout(rawPoints, lengthKm);
  const trackPoints = buildScaledPoints(rawPoints, lengthKm);

  const elevatedPoints = trackPoints.map(
    (p) => new THREE.Vector3(p.x, TRACK_ELEVATION, p.z),
  );
  const curve = new THREE.CatmullRomCurve3(
    elevatedPoints,
    true,
    "catmullrom",
    0.2,
  );

  const shadowPoints = trackPoints.map(
    (p) => new THREE.Vector3(p.x, SHADOW_Y, p.z),
  );
  const shadowCurve = new THREE.CatmullRomCurve3(
    shadowPoints,
    true,
    "catmullrom",
    0.2,
  );

  const numSamples = Math.min(trackPoints.length * 2, 1200);
  const shadowSamples = Math.min(trackPoints.length, 600);

  // ── Connecting wall (ribbon between top track and bottom edge) ────
  const wallSegments = 500;
  const wallPositions: number[] = [];
  const wallUvs: number[] = [];
  const wallIndices: number[] = [];
  for (let i = 0; i <= wallSegments; i++) {
    const t = i / wallSegments;
    const topPt = curve.getPointAt(t);
    wallPositions.push(topPt.x, topPt.y, topPt.z);
    wallUvs.push(t, 1);
    wallPositions.push(topPt.x, SHADOW_Y, topPt.z);
    wallUvs.push(t, 0);
  }
  for (let i = 0; i < wallSegments; i++) {
    const tl = i * 2;
    const bl = i * 2 + 1;
    const tr = (i + 1) * 2;
    const br = (i + 1) * 2 + 1;
    wallIndices.push(tl, bl, tr);
    wallIndices.push(tr, bl, br);
  }
  const wallGeo = new THREE.BufferGeometry();
  wallGeo.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(wallPositions, 3),
  );
  wallGeo.setAttribute("uv", new THREE.Float32BufferAttribute(wallUvs, 2));
  wallGeo.setIndex(wallIndices);
  wallGeo.computeVertexNormals();
  geometries.push(wallGeo);

  const wallMat = new THREE.MeshBasicMaterial({
    color: 0x330500,
    transparent: true,
    opacity: 0.22,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  materials.push(wallMat);
  scene.add(new THREE.Mesh(wallGeo, wallMat));

  const wallGlowMat = new THREE.MeshBasicMaterial({
    color: 0x441000,
    transparent: true,
    opacity: 0.1,
    side: THREE.DoubleSide,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  materials.push(wallGlowMat);
  scene.add(new THREE.Mesh(wallGeo, wallGlowMat));

  // ── Shadow / bottom edge track ────────────────────────────────────
  const shadowCoreGeo = new THREE.TubeGeometry(
    shadowCurve,
    shadowSamples,
    0.12,
    8,
    true,
  );
  geometries.push(shadowCoreGeo);
  const shadowCoreMat = new THREE.MeshBasicMaterial({
    color: hexToNumber(theme.glow),
    transparent: true,
    opacity: 0.4,
    blending: THREE.AdditiveBlending,
    depthTest: false,
    depthWrite: false,
  });
  materials.push(shadowCoreMat);
  scene.add(new THREE.Mesh(shadowCoreGeo, shadowCoreMat));

  const shadowMidGeo = new THREE.TubeGeometry(
    shadowCurve,
    shadowSamples,
    0.35,
    8,
    true,
  );
  geometries.push(shadowMidGeo);
  const shadowMidMat = new THREE.MeshBasicMaterial({
    color: 0x330500,
    transparent: true,
    opacity: 0.15,
    blending: THREE.AdditiveBlending,
    depthTest: false,
    depthWrite: false,
  });
  materials.push(shadowMidMat);
  scene.add(new THREE.Mesh(shadowMidGeo, shadowMidMat));

  const shadowOuterGeo = new THREE.TubeGeometry(
    shadowCurve,
    shadowSamples,
    0.7,
    6,
    true,
  );
  geometries.push(shadowOuterGeo);
  const shadowOuterMat = new THREE.MeshBasicMaterial({
    color: 0x220300,
    transparent: true,
    opacity: 0.06,
    blending: THREE.AdditiveBlending,
    depthTest: false,
    depthWrite: false,
  });
  materials.push(shadowOuterMat);
  scene.add(new THREE.Mesh(shadowOuterGeo, shadowOuterMat));

  // ── Main track (elevated top edge) ────────────────────────────────
  const trackGeo = new THREE.TubeGeometry(curve, numSamples, 0.15, 12, true);
  geometries.push(trackGeo);
  const trackMat = new THREE.MeshPhongMaterial({
    color: hexToNumber(theme.primary),
    emissive: hexToNumber(theme.primary),
    emissiveIntensity: 0.6,
    shininess: 150,
    specular: 0xff8844,
  });
  materials.push(trackMat);
  const trackMesh = new THREE.Mesh(trackGeo, trackMat);
  scene.add(trackMesh);

  const coreGeo = new THREE.TubeGeometry(curve, numSamples, 0.06, 8, true);
  geometries.push(coreGeo);
  const coreMat = new THREE.MeshBasicMaterial({
    color: theme.core,
    transparent: true,
    opacity: 0.85,
    blending: THREE.AdditiveBlending,
    depthTest: false,
    depthWrite: false,
  });
  materials.push(coreMat);
  scene.add(new THREE.Mesh(coreGeo, coreMat));

  const glow1Geo = new THREE.TubeGeometry(curve, numSamples, 0.28, 10, true);
  geometries.push(glow1Geo);
  const glow1Mat = new THREE.MeshBasicMaterial({
    color: hexToNumber(theme.glow),
    transparent: true,
    opacity: 0.35,
    blending: THREE.AdditiveBlending,
    depthTest: false,
    depthWrite: false,
  });
  materials.push(glow1Mat);
  scene.add(new THREE.Mesh(glow1Geo, glow1Mat));

  const glow2Geo = new THREE.TubeGeometry(curve, numSamples, 0.5, 8, true);
  geometries.push(glow2Geo);
  const glow2Mat = new THREE.MeshBasicMaterial({
    color: hexToNumber(theme.primary),
    transparent: true,
    opacity: 0.15,
    blending: THREE.AdditiveBlending,
    depthTest: false,
    depthWrite: false,
  });
  materials.push(glow2Mat);
  scene.add(new THREE.Mesh(glow2Geo, glow2Mat));

  const glow3Geo = new THREE.TubeGeometry(curve, numSamples, 0.85, 8, true);
  geometries.push(glow3Geo);
  const glow3Mat = new THREE.MeshBasicMaterial({
    color: hexToNumber(theme.primary),
    transparent: true,
    opacity: 0.06,
    blending: THREE.AdditiveBlending,
    depthTest: false,
    depthWrite: false,
  });
  materials.push(glow3Mat);
  scene.add(new THREE.Mesh(glow3Geo, glow3Mat));

  // ── Turn markers ──────────────────────────────────────────────────
  let turnNum = 0;
  for (let i = 0; i < rawPoints.length; i++) {
    const curr = rawPoints[i];
    const prev = i > 0 ? rawPoints[i - 1] : null;
    if (curr.isCorner && (!prev || !prev.isCorner)) {
      turnNum++;
      const sx = (curr.x - layout.centreX) * layout.scale;
      const sz = (curr.y - layout.centreY) * layout.scale;

      const dotGeo = new THREE.SphereGeometry(0.22, 8, 8);
      geometries.push(dotGeo);
      const dotMat = new THREE.MeshBasicMaterial({
        color: 0xffaa00,
        transparent: true,
        opacity: 0.9,
        blending: THREE.AdditiveBlending,
        depthTest: false,
        depthWrite: false,
      });
      materials.push(dotMat);
      const dot = new THREE.Mesh(dotGeo, dotMat);
      dot.position.set(sx, TRACK_ELEVATION + 0.35, sz);
      scene.add(dot);

      const { sprite, texture, material } = makeTurnLabel(turnNum, accentColor);
      textures.push(texture);
      materials.push(material);
      sprite.position.set(sx, MARKER_Y, sz);
      scene.add(sprite);
    }
  }

  // ── Platform & grid (below shadow level — very subtle) ────────────
  const platformGeo = new THREE.CircleGeometry(30, 64);
  geometries.push(platformGeo);
  const platformMat = new THREE.MeshBasicMaterial({
    color: 0x050000,
    transparent: true,
    opacity: 0.12,
  });
  materials.push(platformMat);
  const platform = new THREE.Mesh(platformGeo, platformMat);
  platform.rotation.x = -Math.PI / 2;
  platform.position.y = SHADOW_Y - 1.0;
  scene.add(platform);

  const grid = new THREE.GridHelper(60, 60, 0x220000, 0x0a0000);
  grid.position.y = SHADOW_Y - 0.99;
  const gridMat = grid.material as THREE.Material;
  gridMat.transparent = true;
  gridMat.opacity = 0.1;
  geometries.push(grid.geometry);
  materials.push(gridMat);
  scene.add(grid);

  // ── Per-frame breathing / pulsing tick ────────────────────────────
  const tick = (t: number) => {
    pointLight1.intensity = 1.2 + Math.sin(t * 1.8) * 0.15;
    pointLight2.intensity = 0.6 + Math.sin(t * 2.3) * 0.08;
    pointLight3.intensity = 0.4 + Math.sin(t * 1.6) * 0.06;
    sideLight1.intensity = 0.5 + Math.sin(t * 2.7) * 0.08;
    sideLight2.intensity = 0.5 + Math.cos(t * 2.7) * 0.08;

    coreMat.opacity = 0.8 + Math.sin(t * 3) * 0.1;
    glow1Mat.opacity = 0.35 + Math.sin(t * 2.5) * 0.06;
    glow2Mat.opacity = 0.15 + Math.sin(t * 2.0) * 0.04;
    glow3Mat.opacity = 0.06 + Math.sin(t * 1.5) * 0.02;

    shadowCoreMat.opacity = 0.35 + Math.sin(t * 1.8) * 0.05;
    shadowMidMat.opacity = 0.18 + Math.sin(t * 1.5) * 0.03;
    shadowOuterMat.opacity = 0.08 + Math.sin(t * 1.2) * 0.02;

    trackMat.emissiveIntensity = 1.8 + Math.sin(t * 2.5) * 0.2;
  };

  const dispose = () => {
    geometries.forEach((g) => {
      try {
        g.dispose();
      } catch {
        // ignore
      }
    });
    materials.forEach((m) => {
      try {
        m.dispose();
      } catch {
        // ignore
      }
    });
    textures.forEach((t) => {
      try {
        t.dispose();
      } catch {
        // ignore
      }
    });
  };

  return {
    scene,
    layout,
    rawPoints,
    trackElevation: TRACK_ELEVATION,
    tick,
    project: (raw) => projectRawPointToScene(raw, layout),
    dispose,
  };
}
