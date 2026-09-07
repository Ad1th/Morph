/* This is a Three.js render loop, not an idiomatic React tree: per-frame
   mutation of material and transform objects inside useFrame is how
   react-three-fiber is meant to be driven, so the React purity/immutability
   lints do not apply here. */
/* oxlint-disable react/immutability */
/* oxlint-disable react/purity */
import { Suspense, useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Billboard, useTexture } from '@react-three/drei'
import * as THREE from 'three'
import { flight, lerp, smootherstep, smoothstep } from './flight'

/* ── Camera flight ─────────────────────────────────────────────────────── */

type KF = { p: number; pos: [number, number, number]; tgt: [number, number, number] }

/* A 3/4 aerial pass over the board — reads as a circuit far better than a
   table-level shot — dropping close for each annotation stop, then rising for
   the morph and settling back out in front of the second machine. */
const KEYFRAMES: KF[] = [
  { p: 0.0, pos: [0.0, 1.7, 15.5], tgt: [0.0, 1.6, 6.5] },
  { p: 0.12, pos: [0.0, 1.9, 8.6], tgt: [0.0, 0.9, -1.0] },
  { p: 0.22, pos: [-1.7, 2.7, 5.6], tgt: [0.5, 0.35, -0.6] },
  { p: 0.33, pos: [1.0, 2.1, 3.0], tgt: [0.3, 0.2, -1.4] },
  { p: 0.42, pos: [3.5, 1.9, 2.9], tgt: [2.1, 0.15, -1.3] },
  { p: 0.52, pos: [-1.4, 1.7, 2.4], tgt: [-3.1, 0.55, -0.4] },
  { p: 0.66, pos: [0.4, 2.3, 3.9], tgt: [-0.4, 0.15, -1.8] },
  { p: 0.8, pos: [0.0, 6.6, 8.2], tgt: [0.0, 0.3, -0.6] },
  { p: 0.9, pos: [0.0, 2.6, 13.6], tgt: [0.0, 1.5, 3.5] },
  { p: 1.0, pos: [0.0, 1.7, 16.0], tgt: [0.0, 1.6, 6.5] },
]

const _a = new THREE.Vector3()
const _b = new THREE.Vector3()

function sampleFlight(p: number, outPos: THREE.Vector3, outTgt: THREE.Vector3) {
  let i = 0
  while (i < KEYFRAMES.length - 2 && p > KEYFRAMES[i + 1].p) i++
  const k0 = KEYFRAMES[i]
  const k1 = KEYFRAMES[i + 1]
  const f = smootherstep(k0.p, k1.p, p)
  outPos.set(...k0.pos).lerp(_a.set(...k1.pos), f)
  outTgt.set(...k0.tgt).lerp(_b.set(...k1.tgt), f)
}

function Rig({ progress }: { progress: React.RefObject<number> }) {
  const { camera } = useThree()
  const look = useRef(new THREE.Vector3(0, 1.1, 2))
  const pos = useRef(new THREE.Vector3())
  const tgt = useRef(new THREE.Vector3())

  useFrame(() => {
    const p = progress.current
    flight.p = p
    flight.morph = smootherstep(0.72, 0.93, p)
    flight.glow =
      0.75 +
      0.8 * flight.morph +
      0.5 * smoothstep(0.28, 0.42, p) * (1 - smoothstep(0.46, 0.58, p))

    sampleFlight(p, pos.current, tgt.current)
    camera.position.lerp(pos.current, 0.16)
    look.current.lerp(tgt.current, 0.16)
    camera.lookAt(look.current)
  })
  return null
}

function SceneFog() {
  const { scene } = useThree()
  const fog = useMemo(() => new THREE.FogExp2(0x1a040d, 0.018), [])
  scene.fog = fog
  useFrame(() => {
    fog.density = 0.02 + flight.p * 0.026 - flight.morph * 0.018
  })
  return null
}

/* ── Procedural textures ──────────────────────────────────────────────── */

function usePcbTexture() {
  return useMemo(() => {
    const c = document.createElement('canvas')
    c.width = c.height = 1024
    const g = c.getContext('2d')!
    let seed = 20260907
    const rnd = () => {
      seed = (seed * 1664525 + 1013904223) & 0x7fffffff
      return seed / 0x7fffffff
    }
    g.fillStyle = '#1f0714'
    g.fillRect(0, 0, 1024, 1024)
    for (let i = 0; i < 120; i++) {
      g.strokeStyle = rnd() > 0.42 ? '#ef5a8e' : '#e6b05a'
      g.lineWidth = rnd() * 2.6 + 0.9
      g.globalAlpha = rnd() * 0.55 + 0.35
      let px = rnd() * 1024
      let py = rnd() * 1024
      g.beginPath()
      g.moveTo(px, py)
      const steps = 3 + ((rnd() * 4) | 0)
      for (let s = 0; s < steps; s++) {
        if (rnd() > 0.5) px += (rnd() - 0.5) * 440
        else py += (rnd() - 0.5) * 440
        g.lineTo(px, py)
      }
      g.stroke()
      g.globalAlpha = 0.95
      g.fillStyle = '#f0c274'
      g.beginPath()
      g.arc(px, py, 3.6, 0, 7)
      g.fill()
    }
    const t = new THREE.CanvasTexture(c)
    t.colorSpace = THREE.SRGBColorSpace
    return t
  }, [])
}

function useGlowTexture() {
  return useMemo(() => {
    const c = document.createElement('canvas')
    c.width = c.height = 256
    const g = c.getContext('2d')!
    const grd = g.createRadialGradient(128, 128, 0, 128, 128, 128)
    grd.addColorStop(0, 'rgba(255,255,255,1)')
    grd.addColorStop(0.4, 'rgba(255,255,255,0.42)')
    grd.addColorStop(1, 'rgba(255,255,255,0)')
    g.fillStyle = grd
    g.fillRect(0, 0, 256, 256)
    return new THREE.CanvasTexture(c)
  }, [])
}

/* ── Hardware ─────────────────────────────────────────────────────────── */

function Backdrop() {
  const tex = useGlowTexture()
  return (
    <mesh position={[0, 3.5, -11]}>
      <planeGeometry args={[52, 30]} />
      <meshBasicMaterial map={tex} color="#5a1330" transparent opacity={0.9} toneMapped={false} />
    </mesh>
  )
}

function Case() {
  const tex = usePcbTexture()
  const wallTex = useMemo(() => {
    const t = tex.clone()
    t.needsUpdate = true
    t.wrapS = t.wrapT = THREE.RepeatWrapping
    t.repeat.set(2.5, 1.6)
    return t
  }, [tex])
  return (
    <group>
      {/* floor the board sits on */}
      <mesh rotation-x={-Math.PI / 2} position={[0, -0.22, 0]}>
        <planeGeometry args={[40, 30]} />
        <meshStandardMaterial color="#1a0610" roughness={0.95} />
      </mesh>
      {/* back wall + left wall — faint traces so the enclosure never reads as
          flat void, at a fraction of the board's brightness */}
      <mesh position={[0, 6, -9]}>
        <planeGeometry args={[40, 24]} />
        <meshStandardMaterial
          color="#170613"
          roughness={0.92}
          map={wallTex}
          emissiveMap={wallTex}
          emissive="#ff88b4"
          emissiveIntensity={0.16}
        />
      </mesh>
      <mesh rotation-y={Math.PI / 2} position={[-11, 6, 0]}>
        <planeGeometry args={[30, 24]} />
        <meshStandardMaterial
          color="#150512"
          roughness={0.92}
          map={wallTex}
          emissiveMap={wallTex}
          emissive="#ff88b4"
          emissiveIntensity={0.12}
        />
      </mesh>
    </group>
  )
}

function Board() {
  const tex = usePcbTexture()
  const mat = useRef<THREE.MeshStandardMaterial>(null)
  useFrame(() => {
    if (mat.current) mat.current.emissiveIntensity = flight.glow
  })
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2}>
        <planeGeometry args={[9.5, 6.4]} />
        <meshStandardMaterial
          ref={mat}
          map={tex}
          color="#3a1020"
          roughness={0.7}
          metalness={0.2}
          emissiveMap={tex}
          emissive="#ff88b4"
          emissiveIntensity={0.6}
        />
      </mesh>
      <mesh position-y={-0.08}>
        <boxGeometry args={[9.55, 0.16, 6.45]} />
        <meshStandardMaterial color="#0c0308" roughness={0.9} />
      </mesh>
    </group>
  )
}

type ChipProps = {
  position: [number, number, number]
  size?: [number, number, number]
}

function Chip({ position, size = [0.72, 0.26, 0.72] }: ChipProps) {
  return (
    <group position={position}>
      <mesh>
        <boxGeometry args={size} />
        <meshStandardMaterial color="#1d1724" roughness={0.44} metalness={0.32} />
      </mesh>
      {/* gold pad skirt at the base */}
      <mesh position-y={-size[1] / 2 + 0.028}>
        <boxGeometry args={[size[0] * 1.1, 0.055, size[2] * 1.1]} />
        <meshStandardMaterial
          color="#e6b05a"
          metalness={0.95}
          roughness={0.3}
          emissive="#5a3a14"
          emissiveIntensity={0.8}
        />
      </mesh>
      {/* matte lid, flush with the body top */}
      <mesh position-y={size[1] / 2 + 0.001} rotation-x={-Math.PI / 2}>
        <planeGeometry args={[size[0] * 0.97, size[2] * 0.97]} />
        <meshStandardMaterial color="#2f2739" roughness={0.55} metalness={0.35} />
      </mesh>
    </group>
  )
}

/* Six NAND chips that glide from one layout to another through the morph — the
   signature "same parts, rearranged" beat. */
function NandBank() {
  const groups = useRef<(THREE.Group | null)[]>([])
  const layoutA: [number, number, number][] = [
    [1.4, 0.17, -1.5],
    [2.15, 0.17, -1.5],
    [2.9, 0.17, -1.5],
    [1.4, 0.17, -0.7],
    [2.15, 0.17, -0.7],
    [2.9, 0.17, -0.7],
  ]
  const layoutB: [number, number, number][] = [
    [1.2, 0.17, -1.7],
    [1.2, 0.17, -0.85],
    [1.2, 0.17, 0.0],
    [3.05, 0.17, -1.7],
    [3.05, 0.17, -0.85],
    [3.05, 0.17, 0.0],
  ]
  useFrame(() => {
    const m = flight.morph
    const hop = Math.sin(m * Math.PI) * 0.8
    for (let i = 0; i < groups.current.length; i++) {
      const gr = groups.current[i]
      if (!gr) continue
      gr.position.set(
        lerp(layoutA[i][0], layoutB[i][0], m),
        lerp(layoutA[i][1], layoutB[i][1], m) + hop * (0.35 + 0.12 * i),
        lerp(layoutA[i][2], layoutB[i][2], m),
      )
      gr.rotation.y = m * Math.PI * 0.22
    }
  })
  return (
    <>
      {layoutA.map((_, i) => (
        <group
          key={i}
          ref={(el) => {
            groups.current[i] = el
          }}
        >
          <Chip position={[0, 0, 0]} size={[0.58, 0.22, 0.82]} />
        </group>
      ))}
    </>
  )
}

function Cpu() {
  const spreader = useRef<THREE.MeshStandardMaterial>(null)
  useFrame(() => {
    if (spreader.current) {
      const m = flight.morph
      spreader.current.color.setRGB(lerp(0.78, 0.86, m), lerp(0.8, 0.5, m), lerp(0.86, 0.32, m))
    }
  })
  return (
    <group position={[0.2, 0.17, -1.2]}>
      <mesh>
        <boxGeometry args={[1.6, 0.14, 1.6]} />
        <meshStandardMaterial color="#2a1e26" roughness={0.5} metalness={0.4} />
      </mesh>
      <mesh position-y={0.03}>
        <boxGeometry args={[1.82, 0.06, 1.82]} />
        <meshStandardMaterial color="#e6b05a" metalness={0.95} roughness={0.3} emissive="#5a3a14" emissiveIntensity={0.8} />
      </mesh>
      <mesh position-y={0.2}>
        <boxGeometry args={[1.08, 0.26, 1.08]} />
        <meshStandardMaterial ref={spreader} color="#b4aeba" metalness={0.82} roughness={0.3} />
      </mesh>
    </group>
  )
}

function RamStick({ x }: { x: number }) {
  const chips = useRef<THREE.MeshStandardMaterial>(null)
  useFrame(() => {
    if (chips.current) chips.current.emissiveIntensity = 0.12 + 0.45 * flight.morph
  })
  return (
    <group position={[x, 0.62, -0.2]} rotation-y={Math.PI / 2}>
      <mesh>
        <boxGeometry args={[2.0, 0.9, 0.06]} />
        <meshStandardMaterial color="#341024" roughness={0.6} metalness={0.2} />
      </mesh>
      {[-0.62, -0.2, 0.22, 0.64].map((z) => (
        <mesh key={z} position={[z, 0.08, 0.07]}>
          <boxGeometry args={[0.34, 0.44, 0.07]} />
          <meshStandardMaterial
            ref={chips}
            color="#221826"
            roughness={0.42}
            metalness={0.42}
            emissive="#e0447c"
            emissiveIntensity={0.12}
          />
        </mesh>
      ))}
      <mesh position={[0, -0.5, 0]}>
        <boxGeometry args={[1.9, 0.14, 0.09]} />
        <meshStandardMaterial color="#e6b05a" metalness={0.95} roughness={0.26} emissive="#5a3a14" emissiveIntensity={0.7} />
      </mesh>
    </group>
  )
}

function Storage() {
  const hdd = useRef<THREE.MeshStandardMaterial>(null)
  const ssd = useRef<THREE.MeshStandardMaterial>(null)
  const platter = useRef<THREE.Mesh>(null)
  useFrame((_, dt) => {
    const m = flight.morph
    if (hdd.current) hdd.current.opacity = 1 - m
    if (ssd.current) ssd.current.opacity = m
    if (platter.current) {
      platter.current.rotation.y += dt * 1.4 * (1 - m)
      ;(platter.current.material as THREE.Material).opacity = 1 - m
    }
  })
  return (
    <group position={[-3.1, 0.28, 1.9]}>
      <mesh>
        <boxGeometry args={[1.9, 0.5, 2.7]} />
        <meshStandardMaterial ref={hdd} color="#9aa0ab" metalness={0.9} roughness={0.26} transparent depthWrite={false} />
      </mesh>
      <mesh ref={platter} position-y={0.27}>
        <cylinderGeometry args={[0.72, 0.72, 0.04, 40]} />
        <meshStandardMaterial color="#d2d5db" metalness={0.97} roughness={0.1} transparent depthWrite={false} />
      </mesh>
      <mesh position-y={-0.04}>
        <boxGeometry args={[1.7, 0.18, 2.5]} />
        <meshStandardMaterial ref={ssd} color="#1c0c16" metalness={0.3} roughness={0.55} transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  )
}

function Monitor({ os1, os2 }: { os1: string; os2: string }) {
  const [t1, t2] = useTexture([os1, os2])
  const m1 = useRef<THREE.MeshBasicMaterial>(null)
  const m2 = useRef<THREE.MeshBasicMaterial>(null)
  useFrame(() => {
    const p = flight.p
    if (m1.current) m1.current.opacity = 1 - smoothstep(0.08, 0.16, p)
    if (m2.current) m2.current.opacity = smoothstep(0.86, 0.97, p)
  })
  return (
    <group position={[0, 1.7, 8.6]}>
      <mesh position-z={-0.14}>
        <boxGeometry args={[7.0, 4.6, 0.24]} />
        <meshStandardMaterial color="#12060c" roughness={0.6} metalness={0.3} />
      </mesh>
      <mesh position={[0, -2.75, 0.2]}>
        <boxGeometry args={[2.4, 1.0, 1.5]} />
        <meshStandardMaterial color="#12060c" roughness={0.6} metalness={0.3} />
      </mesh>
      {/* screens are colour-graded toward wine so the OS shot reads as a
          powered display, not an imported palette */}
      <mesh>
        <planeGeometry args={[6.3, 3.9]} />
        <meshBasicMaterial ref={m1} map={t1} color="#8f4a63" transparent toneMapped={false} />
      </mesh>
      <mesh position-z={0.01}>
        <planeGeometry args={[6.3, 3.9]} />
        <meshBasicMaterial ref={m2} map={t2} color="#9a5540" transparent opacity={0} toneMapped={false} />
      </mesh>
    </group>
  )
}

function GlowSprite({
  position,
  size,
  color,
  drive,
}: {
  position: [number, number, number]
  size: number
  color: string
  drive: () => number
}) {
  const tex = useGlowTexture()
  const mat = useRef<THREE.MeshBasicMaterial>(null)
  useFrame(() => {
    if (mat.current) mat.current.opacity = drive()
  })
  return (
    <Billboard position={position}>
      <mesh scale={size}>
        <planeGeometry />
        <meshBasicMaterial
          ref={mat}
          map={tex}
          color={color}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>
    </Billboard>
  )
}

function World({ progress }: { progress: React.RefObject<number> }) {
  return (
    <>
      <Rig progress={progress} />
      <SceneFog />

      <ambientLight intensity={0.7} color="#6a1a30" />
      <hemisphereLight args={['#e0447c', '#1a0308', 0.6]} />
      <directionalLight position={[6, 9, 3]} intensity={2.4} color="#f2b76a" />
      <pointLight position={[-2, 5, 3]} intensity={70} distance={26} decay={2} color="#e0447c" />
      <pointLight position={[3.5, 2, 4]} intensity={26} distance={20} decay={2} color="#f79cbc" />
      <pointLight position={[0, 3.5, -6]} intensity={34} distance={22} decay={2} color="#ff5c8a" />

      <Backdrop />
      <Case />
      <Board />
      <Cpu />
      <NandBank />
      <RamStick x={-2.7} />
      <RamStick x={-3.15} />
      <Storage />
      <Chip position={[-1.7, 0.13, 1.5]} size={[0.9, 0.22, 0.9]} />
      <Chip position={[1.8, 0.13, 1.7]} size={[0.9, 0.22, 0.9]} />

      <GlowSprite
        position={[0.2, 0.7, -1.2]}
        size={6}
        color="#e0447c"
        drive={() => 0.18 + 0.6 * smoothstep(0.26, 0.4, flight.p) * (1 - smoothstep(0.5, 0.62, flight.p))}
      />
      <GlowSprite
        position={[0, 1.0, -0.5]}
        size={13}
        color="#f79cbc"
        drive={() => 0.32 * Math.sin(Math.min(1, flight.morph) * Math.PI)}
      />

      <Monitor os1="/wallpapers/macos.jpg" os2="/wallpapers/windows.jpg" />
    </>
  )
}

export function Journey3D({ progress }: { progress: React.RefObject<number> }) {
  const dpr =
    typeof window !== 'undefined' && window.innerWidth < 900
      ? ([1, 1.3] as [number, number])
      : ([1, 1.8] as [number, number])
  return (
    <Canvas
      className="journey-canvas"
      dpr={dpr}
      gl={{ antialias: true, powerPreference: 'high-performance' }}
      camera={{ position: [0, 1.7, 15.5], fov: 42, near: 0.1, far: 80 }}
    >
      <Suspense fallback={null}>
        <World progress={progress} />
      </Suspense>
    </Canvas>
  )
}
