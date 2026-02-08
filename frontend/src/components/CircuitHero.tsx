import { useRef, useEffect, useState, useCallback } from 'react';
import * as THREE from 'three';
import '../styles/CircuitHero.css';

// ─── Track Metadata ──────────────────────────────────────────────
interface TrackMeta {
  file: string;
  title: string;
  subtitle: string;
  flag: string;
  length: string;
  laps: number;
  corners: number;
  distance: string;
}

const TRACKS: Record<string, TrackMeta> = {
  Melbourne:  { file: "Melbourne",  title: "MELBOURNE",   subtitle: "ALBERT PARK CIRCUIT",                 flag: "\u{1F1E6}\u{1F1FA}", length: "5.278 KM",  laps: 58, corners: 16, distance: "306.124 KM" },
  Shanghai:   { file: "Shanghai",   title: "SHANGHAI",    subtitle: "SHANGHAI INTERNATIONAL CIRCUIT",      flag: "\u{1F1E8}\u{1F1F3}", length: "5.451 KM",  laps: 56, corners: 16, distance: "305.066 KM" },
  Suzuka:     { file: "Suzuka",     title: "SUZUKA",      subtitle: "SUZUKA INTERNATIONAL RACING COURSE",  flag: "\u{1F1EF}\u{1F1F5}", length: "5.807 KM",  laps: 53, corners: 18, distance: "307.471 KM" },
  Sakhir:     { file: "Sakhir",     title: "SAKHIR",      subtitle: "BAHRAIN INTERNATIONAL CIRCUIT",       flag: "\u{1F1E7}\u{1F1ED}", length: "5.412 KM",  laps: 57, corners: 15, distance: "308.238 KM" },
  Montreal:   { file: "Montreal",   title: "MONTREAL",    subtitle: "CIRCUIT GILLES-VILLENEUVE",           flag: "\u{1F1E8}\u{1F1E6}", length: "4.361 KM",  laps: 70, corners: 14, distance: "305.270 KM" },
  Catalunya:  { file: "Catalunya",  title: "BARCELONA",   subtitle: "CIRCUIT DE BARCELONA-CATALUNYA",      flag: "\u{1F1EA}\u{1F1F8}", length: "4.657 KM",  laps: 66, corners: 16, distance: "307.236 KM" },
  Silverstone:{ file: "Silverstone",title: "SILVERSTONE", subtitle: "SILVERSTONE CIRCUIT",                 flag: "\u{1F1EC}\u{1F1E7}", length: "5.891 KM",  laps: 52, corners: 18, distance: "306.198 KM" },
  Spa:        { file: "Spa",        title: "SPA",         subtitle: "CIRCUIT DE SPA-FRANCORCHAMPS",        flag: "\u{1F1E7}\u{1F1EA}", length: "7.004 KM",  laps: 44, corners: 19, distance: "308.052 KM" },
  Zandvoort:  { file: "Zandvoort",  title: "ZANDVOORT",   subtitle: "CIRCUIT ZANDVOORT",                   flag: "\u{1F1F3}\u{1F1F1}", length: "4.259 KM",  laps: 72, corners: 14, distance: "306.587 KM" },
  Monza:      { file: "Monza",      title: "MONZA",       subtitle: "AUTODROMO NAZIONALE MONZA",           flag: "\u{1F1EE}\u{1F1F9}", length: "5.793 KM",  laps: 53, corners: 11, distance: "306.720 KM" },
  Austin:     { file: "Austin",     title: "AUSTIN",      subtitle: "CIRCUIT OF THE AMERICAS",             flag: "\u{1F1FA}\u{1F1F8}", length: "5.513 KM",  laps: 56, corners: 20, distance: "308.405 KM" },
  MexicoCity: { file: "MexicoCity", title: "MEXICO CITY", subtitle: "AUT\u00d3DROMO HERMANOS RODR\u00cdGUEZ", flag: "\u{1F1F2}\u{1F1FD}", length: "4.304 KM",  laps: 71, corners: 17, distance: "305.354 KM" },
  SaoPaulo:   { file: "SaoPaulo",   title: "S\u00c3O PAULO", subtitle: "AUT\u00d3DROMO JOS\u00c9 CARLOS PACE", flag: "\u{1F1E7}\u{1F1F7}", length: "4.309 KM",  laps: 71, corners: 15, distance: "305.879 KM" },
  YasMarina:  { file: "YasMarina",  title: "YAS MARINA",  subtitle: "YAS MARINA CIRCUIT",                  flag: "\u{1F1E6}\u{1F1EA}", length: "5.281 KM",  laps: 58, corners: 16, distance: "306.183 KM" },
};

// ─── Helpers ─────────────────────────────────────────────────────
function parseTrackData(csv: string): { x: number; y: number }[] {
  const lines = csv.trim().split('\n');
  const points: { x: number; y: number }[] = [];
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.length === 0) continue;
    const parts = line.split(',');
    if (parts.length >= 2) {
      const x = parseFloat(parts[0]);
      const y = parseFloat(parts[1]);
      if (!isNaN(x) && !isNaN(y)) points.push({ x, y });
    }
  }
  return points;
}

function buildScaledPoints(rawPoints: { x: number; y: number }[]): THREE.Vector3[] {
  let minX = Infinity, maxX = -Infinity;
  let minY = Infinity, maxY = -Infinity;
  rawPoints.forEach(p => {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  });
  const rangeX = maxX - minX;
  const rangeY = maxY - minY;
  const maxRange = Math.max(rangeX, rangeY);
  const targetSize = 25;
  const scale = targetSize / maxRange;
  const centreX = (minX + maxX) / 2;
  const centreY = (minY + maxY) / 2;
  return rawPoints.map(p =>
    new THREE.Vector3((p.x - centreX) * scale, 0, (p.y - centreY) * scale)
  );
}

// ─── Component ───────────────────────────────────────────────────
export default function CircuitHero() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const animationRef = useRef<number | null>(null);
  const scrollRafRef = useRef<number | null>(null);
  const loadIdRef = useRef(0);
  const sceneStateRef = useRef<{
    isDragging: boolean;
    autoRotate: boolean;
    prevX: number;
    cameraAngleTheta: number;
    cameraDistance: number;
  }>({
    isDragging: false,
    autoRotate: true,
    prevX: 0,
    cameraAngleTheta: Math.PI / 4,
    cameraDistance: 30,
  });

  const [selectedTrack, setSelectedTrack] = useState('Melbourne');
  const [trackMeta, setTrackMeta] = useState<TrackMeta>(TRACKS['Melbourne']);
  const [loading, setLoading] = useState(true);
  const [scrollProgress, setScrollProgress] = useState(0);

  // ── Scroll-driven parallax: fade/scale the hero as user scrolls past ──
  useEffect(() => {
    const handleScroll = () => {
      if (scrollRafRef.current) return;
      scrollRafRef.current = requestAnimationFrame(() => {
        const section = sectionRef.current;
        if (!section) { scrollRafRef.current = null; return; }
        const rect = section.getBoundingClientRect();
        const vh = window.innerHeight;
        // progress: 0 when hero fully visible, 1 when hero top reaches viewport top and beyond
        const progress = Math.max(0, Math.min(1, -rect.top / (vh * 0.6)));
        setScrollProgress(progress);
        scrollRafRef.current = null;
      });
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', handleScroll);
      if (scrollRafRef.current) cancelAnimationFrame(scrollRafRef.current);
    };
  }, []);

  const teardownScene = useCallback(() => {
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    const container = containerRef.current;
    if (container) {
      // Remove only the canvas, not the overlay UI
      const canvas = container.querySelector('canvas');
      if (canvas) container.removeChild(canvas);
    }
    if (rendererRef.current) {
      rendererRef.current.dispose();
      rendererRef.current = null;
    }
  }, []);

  const initTrackScene = useCallback((csvData: string) => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000);
    scene.fog = new THREE.Fog(0x000000, 30, 100);

    const camera = new THREE.PerspectiveCamera(
      50,
      container.clientWidth / container.clientHeight,
      0.1,
      1000
    );

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // ── Lighting (subtle — most colour comes from emissive materials) ──
    scene.add(new THREE.AmbientLight(0xffffff, 0.08));

    // Overhead key light
    const pointLight1 = new THREE.PointLight(0xff2200, 1.2, 60);
    pointLight1.position.set(0, 25, 0);
    scene.add(pointLight1);

    // Accent fills for subtle depth
    const pointLight2 = new THREE.PointLight(0xff3300, 0.6, 50);
    pointLight2.position.set(20, 15, 20);
    scene.add(pointLight2);

    const pointLight3 = new THREE.PointLight(0xff4400, 0.4, 40);
    pointLight3.position.set(-20, 12, -20);
    scene.add(pointLight3);

    // Gentle side lights
    const sideLight1 = new THREE.PointLight(0xff1100, 0.5, 50);
    sideLight1.position.set(25, 10, 0);
    scene.add(sideLight1);

    const sideLight2 = new THREE.PointLight(0xff1100, 0.5, 50);
    sideLight2.position.set(-25, 10, 0);
    scene.add(sideLight2);

    // ── Build track geometry ─────────────────────────────────────
    const rawPoints = parseTrackData(csvData);
    const trackPoints = buildScaledPoints(rawPoints);

    const TRACK_ELEVATION = 2.5;

    // Elevated curve for main track (raised above ground for 3D depth)
    const elevatedPoints = trackPoints.map(p =>
      new THREE.Vector3(p.x, TRACK_ELEVATION, p.z)
    );
    const curve = new THREE.CatmullRomCurve3(elevatedPoints, true, 'catmullrom', 0.2);

    // Shadow/bottom edge sits just below the main track
    const SHADOW_Y = TRACK_ELEVATION - 1.4;

    const shadowPoints = trackPoints.map(p =>
      new THREE.Vector3(p.x, SHADOW_Y, p.z)
    );
    const shadowCurve = new THREE.CatmullRomCurve3(shadowPoints, true, 'catmullrom', 0.2);

    const numSamples = Math.min(trackPoints.length * 2, 1200);
    const shadowSamples = Math.min(trackPoints.length, 600);

    // ── Connecting wall (ribbon between top track and bottom edge) ──
    const wallSegments = 500;
    const wallPositions: number[] = [];
    const wallUvs: number[] = [];
    const wallIndices: number[] = [];

    for (let i = 0; i <= wallSegments; i++) {
      const t = i / wallSegments;
      const topPt = curve.getPointAt(t);
      const u = t;

      // Top vertex (at main track level)
      wallPositions.push(topPt.x, topPt.y, topPt.z);
      wallUvs.push(u, 1);

      // Bottom vertex (at shadow level)
      wallPositions.push(topPt.x, SHADOW_Y, topPt.z);
      wallUvs.push(u, 0);
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
    wallGeo.setAttribute('position', new THREE.Float32BufferAttribute(wallPositions, 3));
    wallGeo.setAttribute('uv', new THREE.Float32BufferAttribute(wallUvs, 2));
    wallGeo.setIndex(wallIndices);
    wallGeo.computeVertexNormals();

    // Dark semi-transparent wall
    const wallMat = new THREE.MeshBasicMaterial({
      color: 0x330500, transparent: true, opacity: 0.22,
      side: THREE.DoubleSide, depthWrite: false,
    });
    scene.add(new THREE.Mesh(wallGeo, wallMat));

    // Slightly brighter inner wall for depth
    const wallGlowMat = new THREE.MeshBasicMaterial({
      color: 0x441000, transparent: true, opacity: 0.10,
      side: THREE.DoubleSide, depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    scene.add(new THREE.Mesh(wallGeo, wallGlowMat));

    // ── Shadow / bottom edge track ───────────────────────────────
    // Bottom edge core — mirrors the main track shape
    const shadowCoreMat = new THREE.MeshBasicMaterial({
      color: 0x661100, transparent: true, opacity: 0.4,
      blending: THREE.AdditiveBlending
    });
    scene.add(new THREE.Mesh(
      new THREE.TubeGeometry(shadowCurve, shadowSamples, 0.12, 8, true), shadowCoreMat
    ));

    // Soft glow around bottom edge
    const shadowMidMat = new THREE.MeshBasicMaterial({
      color: 0x330500, transparent: true, opacity: 0.15,
      blending: THREE.AdditiveBlending
    });
    scene.add(new THREE.Mesh(
      new THREE.TubeGeometry(shadowCurve, shadowSamples, 0.35, 8, true), shadowMidMat
    ));

    // Faint outer glow on bottom edge
    const shadowOuterMat = new THREE.MeshBasicMaterial({
      color: 0x220300, transparent: true, opacity: 0.06,
      blending: THREE.AdditiveBlending
    });
    scene.add(new THREE.Mesh(
      new THREE.TubeGeometry(shadowCurve, shadowSamples, 0.7, 6, true), shadowOuterMat
    ));

    // ── Main track (elevated top edge) ───────────────────────────
    // Solid track body
    const trackMesh = new THREE.Mesh(
      new THREE.TubeGeometry(curve, numSamples, 0.15, 12, true),
      new THREE.MeshPhongMaterial({
        color: 0xff2200,
        emissive: 0xff3300,
        emissiveIntensity: 1.8,
        shininess: 150,
        specular: 0xff8844,
      })
    );
    scene.add(trackMesh);

    // Bright inner core — thin hot centre
    const coreMat = new THREE.MeshBasicMaterial({
      color: 0xffcc88,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending
    });
    scene.add(new THREE.Mesh(new THREE.TubeGeometry(curve, numSamples, 0.06, 8, true), coreMat));

    // Tight glow layer 1 — close halo
    const glow1Mat = new THREE.MeshBasicMaterial({
      color: 0xff3300, transparent: true, opacity: 0.35,
      blending: THREE.AdditiveBlending
    });
    scene.add(new THREE.Mesh(new THREE.TubeGeometry(curve, numSamples, 0.28, 10, true), glow1Mat));

    // Glow layer 2 — soft spread
    const glow2Mat = new THREE.MeshBasicMaterial({
      color: 0xff1100, transparent: true, opacity: 0.15,
      blending: THREE.AdditiveBlending
    });
    scene.add(new THREE.Mesh(new THREE.TubeGeometry(curve, numSamples, 0.5, 8, true), glow2Mat));

    // Glow layer 3 — faint outer aura
    const glow3Mat = new THREE.MeshBasicMaterial({
      color: 0xff0000, transparent: true, opacity: 0.06,
      blending: THREE.AdditiveBlending
    });
    scene.add(new THREE.Mesh(new THREE.TubeGeometry(curve, numSamples, 0.85, 8, true), glow3Mat));

    // ── Turn markers with drop lines ─────────────────────────────
    const markerGeo = new THREE.SphereGeometry(0.05, 16, 16);
    const markerMat = new THREE.MeshPhongMaterial({
      color: 0xffffff,
      emissive: 0xffeeaa,
      emissiveIntensity: 1.2,
      shininess: 120
    });
    const markers: THREE.Mesh[] = [];
    const markerGlows: THREE.Mesh[] = [];

    const step = Math.max(1, Math.floor(trackPoints.length / 14));
    for (let i = 0; i < trackPoints.length; i += step) {
      const p = trackPoints[i];

      // Marker dot on top track
      const marker = new THREE.Mesh(markerGeo, markerMat);
      marker.position.set(p.x, TRACK_ELEVATION + 0.12, p.z);
      scene.add(marker);
      markers.push(marker);

      // Small tight halo
      const glowSphere = new THREE.Mesh(
        new THREE.SphereGeometry(0.09, 10, 10),
        new THREE.MeshBasicMaterial({
          color: 0xff6633, transparent: true, opacity: 0.2,
          blending: THREE.AdditiveBlending
        })
      );
      glowSphere.position.copy(marker.position);
      scene.add(glowSphere);
      markerGlows.push(glowSphere);

      // Drop line from marker down past bottom edge
      const dropLineGeo = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(p.x, TRACK_ELEVATION + 0.12, p.z),
        new THREE.Vector3(p.x, SHADOW_Y - 0.6, p.z)
      ]);
      const dropLine = new THREE.Line(dropLineGeo, new THREE.LineBasicMaterial({
        color: 0xff2200, transparent: true, opacity: 0.15
      }));
      scene.add(dropLine);

      // Small glow dot at the bottom of drop line
      const shadowDot = new THREE.Mesh(
        new THREE.SphereGeometry(0.05, 8, 8),
        new THREE.MeshBasicMaterial({
          color: 0x661100, transparent: true, opacity: 0.25,
          blending: THREE.AdditiveBlending
        })
      );
      shadowDot.position.set(p.x, SHADOW_Y - 0.6, p.z);
      scene.add(shadowDot);
    }

    // Platform & grid (below shadow level — very subtle)
    const platform = new THREE.Mesh(
      new THREE.CircleGeometry(30, 64),
      new THREE.MeshBasicMaterial({ color: 0x050000, transparent: true, opacity: 0.12 })
    );
    platform.rotation.x = -Math.PI / 2;
    platform.position.y = SHADOW_Y - 1.0;
    scene.add(platform);

    const grid = new THREE.GridHelper(60, 60, 0x220000, 0x0a0000);
    grid.position.y = SHADOW_Y - 0.99;
    (grid.material as THREE.Material).opacity = 0.10;
    (grid.material as THREE.Material).transparent = true;
    scene.add(grid);

    // ── Camera & controls ────────────────────────────────────────
    const FIXED_PHI = Math.PI / 3;         // Much lower angle for side-on view (try values: /8 = very low, /10 = low, /12 = moderate, /15 = higher)
    const autoRotateSpeed = 0.002;
    const state = sceneStateRef.current;
    state.cameraAngleTheta = Math.PI / 4;
    state.cameraDistance = 32;
    state.autoRotate = true;

    function updateCamera() {
      camera.position.x = state.cameraDistance * Math.sin(FIXED_PHI) * Math.cos(state.cameraAngleTheta);
      camera.position.y = state.cameraDistance * Math.cos(FIXED_PHI);
      camera.position.z = state.cameraDistance * Math.sin(FIXED_PHI) * Math.sin(state.cameraAngleTheta);
      camera.lookAt(0, 1.8, 0);
    }
    updateCamera();

    // Mouse events
    const onMouseDown = (e: MouseEvent) => {
      state.isDragging = true;
      state.autoRotate = false;
      state.prevX = e.clientX;
    };
    const onMouseMove = (e: MouseEvent) => {
      if (!state.isDragging) return;
      state.cameraAngleTheta -= (e.clientX - state.prevX) * 0.01;
      state.prevX = e.clientX;
    };
    const onMouseUp = () => {
      state.isDragging = false;
      setTimeout(() => { state.autoRotate = true; }, 2000);
    };
    const MAX_ZOOM_OUT = 50;
    const onWheel = (e: WheelEvent) => {
      // If scrolling down and already at max zoom-out, let the page scroll through
      if (e.deltaY > 0 && state.cameraDistance >= MAX_ZOOM_OUT) {
        return; // don't preventDefault — allow native scroll
      }
      e.preventDefault();
      state.cameraDistance += e.deltaY * 0.05;
      state.cameraDistance = Math.max(15, Math.min(MAX_ZOOM_OUT, state.cameraDistance));
    };

    // Touch events
    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length === 1) {
        state.isDragging = true;
        state.autoRotate = false;
        state.prevX = e.touches[0].clientX;
      }
    };
    const onTouchMove = (e: TouchEvent) => {
      if (!state.isDragging || e.touches.length !== 1) return;
      state.cameraAngleTheta -= (e.touches[0].clientX - state.prevX) * 0.01;
      state.prevX = e.touches[0].clientX;
    };
    const onTouchEnd = () => {
      state.isDragging = false;
      setTimeout(() => { state.autoRotate = true; }, 2000);
    };

    renderer.domElement.addEventListener('mousedown', onMouseDown);
    renderer.domElement.addEventListener('mousemove', onMouseMove);
    renderer.domElement.addEventListener('mouseup', onMouseUp);
    renderer.domElement.addEventListener('wheel', onWheel, { passive: false });
    renderer.domElement.addEventListener('touchstart', onTouchStart);
    renderer.domElement.addEventListener('touchmove', onTouchMove);
    renderer.domElement.addEventListener('touchend', onTouchEnd);

    // ── Animation loop with enhanced dynamics ────────────────────
    function animate() {
      animationRef.current = requestAnimationFrame(animate);
      if (state.autoRotate) state.cameraAngleTheta += autoRotateSpeed;
      updateCamera();

      const t = Date.now() * 0.001;
      
      // Subtle light pulsing
      pointLight1.intensity = 1.2 + Math.sin(t * 1.8) * 0.15;
      pointLight2.intensity = 0.6 + Math.sin(t * 2.3) * 0.08;
      pointLight3.intensity = 0.4 + Math.sin(t * 1.6) * 0.06;
      sideLight1.intensity = 0.5 + Math.sin(t * 2.7) * 0.08;
      sideLight2.intensity = 0.5 + Math.cos(t * 2.7) * 0.08;
      
      // Pulsing track core
      coreMat.opacity = 0.8 + Math.sin(t * 3) * 0.1;
      
      // Animated glow layers
      glow1Mat.opacity = 0.35 + Math.sin(t * 2.5) * 0.06;
      glow2Mat.opacity = 0.15 + Math.sin(t * 2.0) * 0.04;
      glow3Mat.opacity = 0.06 + Math.sin(t * 1.5) * 0.02;

      // Animate shadow reflection layers
      shadowCoreMat.opacity = 0.35 + Math.sin(t * 1.8) * 0.05;
      shadowMidMat.opacity = 0.18 + Math.sin(t * 1.5) * 0.03;
      shadowOuterMat.opacity = 0.08 + Math.sin(t * 1.2) * 0.02;
      
      // Breathing effect on main track
      trackMesh.material.emissiveIntensity = 1.8 + Math.sin(t * 2.5) * 0.2;
      
      // Subtle marker animation
      markers.forEach((marker, i) => {
        const offset = i * 0.5;
        marker.scale.setScalar(1.0 + Math.sin(t * 2 + offset) * 0.08);
        (marker.material as THREE.MeshPhongMaterial).emissiveIntensity = 
          1.2 + Math.sin(t * 2 + offset) * 0.2;
      });
      
      markerGlows.forEach((glow, i) => {
        const offset = i * 0.5;
        glow.scale.setScalar(1.0 + Math.sin(t * 2 + offset) * 0.1);
        (glow.material as THREE.MeshBasicMaterial).opacity = 
          0.25 + Math.sin(t * 2 + offset) * 0.08;
      });

      renderer.render(scene, camera);
    }

    // Handle resize
    const onResize = () => {
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    };
    window.addEventListener('resize', onResize);

    animate();

    // Cleanup function for this specific scene instance
    return () => {
      window.removeEventListener('resize', onResize);
      renderer.domElement.removeEventListener('mousedown', onMouseDown);
      renderer.domElement.removeEventListener('mousemove', onMouseMove);
      renderer.domElement.removeEventListener('mouseup', onMouseUp);
      renderer.domElement.removeEventListener('wheel', onWheel);
      renderer.domElement.removeEventListener('touchstart', onTouchStart);
      renderer.domElement.removeEventListener('touchmove', onTouchMove);
      renderer.domElement.removeEventListener('touchend', onTouchEnd);
    };
  }, []);

  // Load track data
  const loadTrack = useCallback(async (trackKey: string) => {
    const meta = TRACKS[trackKey];
    if (!meta) return;

    setLoading(true);
    teardownScene();
    const currentLoadId = ++loadIdRef.current;

    try {
      const response = await fetch(`/circuit_3d/TrackCoordinateCSVs/${meta.file}.csv`, {
        cache: 'no-store',
      });
      if (!response.ok) {
        throw new Error(`Failed to load track CSV: ${meta.file}`);
      }
      const csvData = await response.text();
      if (currentLoadId !== loadIdRef.current) return;
      initTrackScene(csvData);
      requestAnimationFrame(() => {
        if (currentLoadId !== loadIdRef.current) return;
        setTrackMeta(meta);
        setLoading(false);
      });
    } catch (error) {
      console.error('[F1] Failed to load track file:', meta.file, error);
      setLoading(false);
    }
  }, [teardownScene, initTrackScene]);

  // Initial load
  useEffect(() => {
    loadTrack('Melbourne');
    return () => {
      teardownScene();
    };
  }, [loadTrack, teardownScene]);

  const trackKeys = Object.keys(TRACKS);

  const handleTrackChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const key = e.target.value;
    setSelectedTrack(key);
    loadTrack(key);
  };

  const handlePrevTrack = () => {
    const idx = trackKeys.indexOf(selectedTrack);
    const prevIdx = (idx - 1 + trackKeys.length) % trackKeys.length;
    const key = trackKeys[prevIdx];
    setSelectedTrack(key);
    loadTrack(key);
  };

  const handleNextTrack = () => {
    const idx = trackKeys.indexOf(selectedTrack);
    const nextIdx = (idx + 1) % trackKeys.length;
    const key = trackKeys[nextIdx];
    setSelectedTrack(key);
    loadTrack(key);
  };

  const handleScrollDown = () => {
    const heroEl = containerRef.current?.closest('.circuit-hero-section');
    if (heroEl) {
      const nextSection = heroEl.nextElementSibling;
      if (nextSection) {
        nextSection.scrollIntoView({ behavior: 'smooth' });
      }
    }
  };

  // Parallax style computed from scroll progress
  const heroParallaxStyle: React.CSSProperties = {
    opacity: 1 - scrollProgress * 0.85,
    transform: `scale(${1 - scrollProgress * 0.08}) translateY(${scrollProgress * 30}px)`,
    transition: 'none',
  };

  const overlayOpacity = scrollProgress * 0.9;

  return (
    <section className="circuit-hero-section" ref={sectionRef}>
      <div className="circuit-hero-container" ref={containerRef} style={heroParallaxStyle}>
        {/* Loading indicator */}
        {loading && (
          <div className="circuit-loading">LOADING CIRCUIT...</div>
        )}

        {/* Info panel */}
        {!loading && (
          <div className="circuit-info-panel">
            <h1 className="circuit-title">{trackMeta.title}</h1>
            <div className="circuit-subtitle">{trackMeta.subtitle}</div>
            <div className="circuit-stats">
              <div className="circuit-stat-item">
                <span className="circuit-stat-label">Length</span>
                <span className="circuit-stat-value">{trackMeta.length}</span>
              </div>
              <div className="circuit-stat-item">
                <span className="circuit-stat-label">Laps</span>
                <span className="circuit-stat-value">{trackMeta.laps}</span>
              </div>
              <div className="circuit-stat-item">
                <span className="circuit-stat-label">Corners</span>
                <span className="circuit-stat-value">{trackMeta.corners}</span>
              </div>
              <div className="circuit-stat-item">
                <span className="circuit-stat-label">Distance</span>
                <span className="circuit-stat-value">{trackMeta.distance}</span>
              </div>
            </div>
          </div>
        )}

        {/* Country flag */}
        {!loading && (
          <div className="circuit-country-flag">{trackMeta.flag}</div>
        )}

        {/* Prev / Next circuit nav arrows */}
        <button className="circuit-nav-arrow circuit-nav-prev" onClick={handlePrevTrack} aria-label="Previous circuit">
          <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <button className="circuit-nav-arrow circuit-nav-next" onClick={handleNextTrack} aria-label="Next circuit">
          <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 6 15 12 9 18" />
          </svg>
        </button>

        {/* Controls hint */}
        <div className="circuit-controls-hint">
          <span>CLICK + DRAG TO ROTATE</span>
          <span>SCROLL TO ZOOM</span>
        </div>

        {/* Track selector */}
        <div className="circuit-track-selector">
          <label>Select Circuit</label>
          <select value={selectedTrack} onChange={handleTrackChange}>
            {Object.entries(TRACKS).map(([key, meta]) => (
              <option key={key} value={key}>{meta.title}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Bottom gradient overlay for seamless bleed into dashboard */}
      <div
        className="circuit-hero-gradient-overlay"
        style={{ opacity: overlayOpacity }}
      />

      {/* Scroll down indicator — fade out as user scrolls */}
      <button
        className="scroll-down-indicator"
        onClick={handleScrollDown}
        aria-label="Scroll down"
        style={{ opacity: Math.max(0, 1 - scrollProgress * 3) }}
      >
        <div className="scroll-arrow" />
        <span className="scroll-text">EXPLORE</span>
      </button>
    </section>
  );
}