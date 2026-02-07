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
  Austin:     { file: "Austin",     title: "AUSTIN",      subtitle: "CIRCUIT OF THE AMERICAS",             flag: "\u{1F1FA}\u{1F1F8}", length: "5.513 KM",  laps: 56, corners: 20, distance: "308.405 KM" },
  Catalunya:  { file: "Catalunya",  title: "BARCELONA",   subtitle: "CIRCUIT DE BARCELONA-CATALUNYA",      flag: "\u{1F1EA}\u{1F1F8}", length: "4.657 KM",  laps: 66, corners: 16, distance: "307.236 KM" },
  MexicoCity: { file: "MexicoCity", title: "MEXICO CITY", subtitle: "AUT\u00d3DROMO HERMANOS RODR\u00cdGUEZ", flag: "\u{1F1F2}\u{1F1FD}", length: "4.304 KM",  laps: 71, corners: 17, distance: "305.354 KM" },
  Montreal:   { file: "Montreal",   title: "MONTREAL",    subtitle: "CIRCUIT GILLES-VILLENEUVE",           flag: "\u{1F1E8}\u{1F1E6}", length: "4.361 KM",  laps: 70, corners: 14, distance: "305.270 KM" },
  Monza:      { file: "Monza",      title: "MONZA",       subtitle: "AUTODROMO NAZIONALE MONZA",           flag: "\u{1F1EE}\u{1F1F9}", length: "5.793 KM",  laps: 53, corners: 11, distance: "306.720 KM" },
  Sakhir:     { file: "Sakhir",     title: "SAKHIR",      subtitle: "BAHRAIN INTERNATIONAL CIRCUIT",       flag: "\u{1F1E7}\u{1F1ED}", length: "5.412 KM",  laps: 57, corners: 15, distance: "308.238 KM" },
  SaoPaulo:   { file: "SaoPaulo",   title: "S\u00c3O PAULO", subtitle: "AUT\u00d3DROMO JOS\u00c9 CARLOS PACE", flag: "\u{1F1E7}\u{1F1F7}", length: "4.309 KM",  laps: 71, corners: 15, distance: "305.879 KM" },
  Shanghai:   { file: "Shanghai",   title: "SHANGHAI",    subtitle: "SHANGHAI INTERNATIONAL CIRCUIT",      flag: "\u{1F1E8}\u{1F1F3}", length: "5.451 KM",  laps: 56, corners: 16, distance: "305.066 KM" },
  Silverstone:{ file: "Silverstone",title: "SILVERSTONE", subtitle: "SILVERSTONE CIRCUIT",                 flag: "\u{1F1EC}\u{1F1E7}", length: "5.891 KM",  laps: 52, corners: 18, distance: "306.198 KM" },
  Spa:        { file: "Spa",        title: "SPA",         subtitle: "CIRCUIT DE SPA-FRANCORCHAMPS",        flag: "\u{1F1E7}\u{1F1EA}", length: "7.004 KM",  laps: 44, corners: 19, distance: "308.052 KM" },
  Suzuka:     { file: "Suzuka",     title: "SUZUKA",      subtitle: "SUZUKA INTERNATIONAL RACING COURSE",  flag: "\u{1F1EF}\u{1F1F5}", length: "5.807 KM",  laps: 53, corners: 18, distance: "307.471 KM" },
  YasMarina:  { file: "YasMarina",  title: "YAS MARINA",  subtitle: "YAS MARINA CIRCUIT",                  flag: "\u{1F1E6}\u{1F1EA}", length: "5.281 KM",  laps: 58, corners: 16, distance: "306.183 KM" },
  Zandvoort:  { file: "Zandvoort",  title: "ZANDVOORT",   subtitle: "CIRCUIT ZANDVOORT",                   flag: "\u{1F1F3}\u{1F1F1}", length: "4.259 KM",  laps: 72, corners: 14, distance: "306.587 KM" },
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

    // ── Lighting ─────────────────────────────────────────────────
    scene.add(new THREE.AmbientLight(0xffffff, 0.2));

    const pointLight1 = new THREE.PointLight(0xff0000, 2, 80);
    pointLight1.position.set(0, 25, 0);
    scene.add(pointLight1);

    const pointLight2 = new THREE.PointLight(0xff0000, 1.2, 60);
    pointLight2.position.set(20, 15, 20);
    scene.add(pointLight2);

    const pointLight3 = new THREE.PointLight(0xffffff, 0.8, 50);
    pointLight3.position.set(-20, 12, -20);
    scene.add(pointLight3);

    // ── Build track geometry ─────────────────────────────────────
    const rawPoints = parseTrackData(csvData);
    const trackPoints = buildScaledPoints(rawPoints);

    const curve = new THREE.CatmullRomCurve3(trackPoints, true, 'catmullrom', 0.2);
    const numSamples = Math.min(trackPoints.length * 2, 1200);

    // Main track – bright red core
    const trackMesh = new THREE.Mesh(
      new THREE.TubeGeometry(curve, numSamples, 0.08, 12, true),
      new THREE.MeshPhongMaterial({
        color: 0xff0000, emissive: 0xff0000, emissiveIntensity: 1.0,
        shininess: 100, specular: 0xff3333,
      })
    );
    scene.add(trackMesh);

    // Glow layers
    const glow1Mat = new THREE.MeshBasicMaterial({ color: 0xff0000, transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending });
    scene.add(new THREE.Mesh(new THREE.TubeGeometry(curve, numSamples, 0.15, 12, true), glow1Mat));

    const glow2Mat = new THREE.MeshBasicMaterial({ color: 0xffaaaa, transparent: true, opacity: 0.4, blending: THREE.AdditiveBlending });
    scene.add(new THREE.Mesh(new THREE.TubeGeometry(curve, numSamples, 0.25, 12, true), glow2Mat));

    const glow3Mat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.15, blending: THREE.AdditiveBlending });
    scene.add(new THREE.Mesh(new THREE.TubeGeometry(curve, numSamples, 0.4, 12, true), glow3Mat));

    // Turn markers
    const markerGeo = new THREE.SphereGeometry(0.05, 16, 16);
    const markerMat = new THREE.MeshPhongMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 1.2, shininess: 100 });
    const step = Math.max(1, Math.floor(trackPoints.length / 14));
    for (let i = 0; i < trackPoints.length; i += step) {
      const marker = new THREE.Mesh(markerGeo, markerMat);
      marker.position.copy(trackPoints[i]);
      marker.position.y = 0.15;
      scene.add(marker);

      const glowSphere = new THREE.Mesh(
        new THREE.SphereGeometry(0.1, 16, 16),
        new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.3, blending: THREE.AdditiveBlending })
      );
      glowSphere.position.copy(marker.position);
      scene.add(glowSphere);
    }

    // Platform & grid
    const platform = new THREE.Mesh(
      new THREE.CircleGeometry(30, 64),
      new THREE.MeshBasicMaterial({ color: 0x0a0000, transparent: true, opacity: 0.3 })
    );
    platform.rotation.x = -Math.PI / 2;
    platform.position.y = -0.2;
    scene.add(platform);

    const grid = new THREE.GridHelper(60, 60, 0x330000, 0x110000);
    grid.position.y = -0.19;
    (grid.material as THREE.Material).opacity = 0.2;
    (grid.material as THREE.Material).transparent = true;
    scene.add(grid);

    // ── Camera & controls ────────────────────────────────────────
    const FIXED_PHI = Math.PI / 5;
    const autoRotateSpeed = 0.0015;
    const state = sceneStateRef.current;
    state.cameraAngleTheta = Math.PI / 4;
    state.cameraDistance = 30;
    state.autoRotate = true;

    function updateCamera() {
      camera.position.x = state.cameraDistance * Math.sin(FIXED_PHI) * Math.cos(state.cameraAngleTheta);
      camera.position.y = state.cameraDistance * Math.cos(FIXED_PHI);
      camera.position.z = state.cameraDistance * Math.sin(FIXED_PHI) * Math.sin(state.cameraAngleTheta);
      camera.lookAt(0, 0, 0);
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

    // ── Animation loop ───────────────────────────────────────────
    function animate() {
      animationRef.current = requestAnimationFrame(animate);
      if (state.autoRotate) state.cameraAngleTheta += autoRotateSpeed;
      updateCamera();

      const t = Date.now() * 0.001;
      pointLight1.intensity = 2 + Math.sin(t * 1.5) * 0.3;
      pointLight2.intensity = 1.2 + Math.sin(t * 2) * 0.2;
      glow1Mat.opacity = 0.6 + Math.sin(t * 3) * 0.1;
      glow2Mat.opacity = 0.4 + Math.sin(t * 2.5) * 0.08;

      renderer.render(scene, camera);
    }

    // Handle resize
    const onResize = () => {
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    };
    window.addEventListener('resize', onResize);

    // Hide loading
    setTimeout(() => setLoading(false), 400);

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
  const loadTrack = useCallback((trackKey: string) => {
    const meta = TRACKS[trackKey];
    if (!meta) return;

    setLoading(true);
    setTrackMeta(meta);
    teardownScene();

    // Fetch the CSV data from the JS file
    // The JS files call window.__onTrackData(csvString)
    (window as unknown as Record<string, unknown>).__onTrackData = (csvData: string) => {
      initTrackScene(csvData);
    };

    // Remove old script
    const oldScript = document.getElementById('track-data-script');
    if (oldScript) oldScript.remove();

    // Inject new script
    const script = document.createElement('script');
    script.id = 'track-data-script';
    script.src = `/circuit_3d/TrackCoordinateJS/${meta.file}.js`;
    script.onerror = () => {
      console.error('[F1] Failed to load track file:', meta.file);
      setLoading(false);
    };
    document.body.appendChild(script);
  }, [teardownScene, initTrackScene]);

  // Initial load
  useEffect(() => {
    loadTrack('Melbourne');
    return () => {
      teardownScene();
      const oldScript = document.getElementById('track-data-script');
      if (oldScript) oldScript.remove();
    };
  }, [loadTrack, teardownScene]);

  const handleTrackChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const key = e.target.value;
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
