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

const KEYFRAMES: KF[] = [
  { p: 0.0, pos: [0.0, 1.5, 13.5], tgt: [0.0, 0.6, 0.0] },
  { p: 0.12, pos: [0.0, 1.05, 7.6], tgt: [0.0, 0.4, -1.0] },
  { p: 0.22, pos: [-2.7, 1.15, 4.0], tgt: [-1.3, 0.25, -0.6] },
  { p: 0.33, pos: [0.4, 0.82, 1.7], tgt: [0.5, 0.15, -1.6] },
  { p: 0.42, pos: [2.1, 0.5, 0.15], tgt: [2.9, 0.12, -1.3] },
  { p: 0.52, pos: [-2.3, 0.55, 0.5], tgt: [-3.1, 0.18, -0.8] },
  { p: 0.66, pos: [0.0, 1.55, 1.7], tgt: [0.0, 0.0, -1.9] },
  { p: 0.8, pos: [0.0, 2.9, 5.6], tgt: [0.0, 0.35, -0.6] },
  { p: 0.92, pos: [0.0, 2.0, 8.6], tgt: [0.0, 0.45, 0.0] },
  { p: 1.0, pos: [0.0, 1.5, 13.2], tgt: [0.0, 0.6, 0.0] },
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
  const look = useRef(new THREE.Vector3(0, 0.6, 0))
  const pos = useRef(new THREE.Vector3())
  const tgt = useRef(new THREE.Vector3())

  useFrame(() => {
    const p = progress.current
    flight.p = p
    flight.morph = smootherstep(0.72, 0.93, p)
    flight.glow =
      0.4 +
      0.6 * flight.morph +
      0.4 * smoothstep(0.28, 0.42, p) * (1 - smoothstep(0.46, 0.58, p))

    sampleFlight(p, pos.current, tgt.current)
    camera.position.lerp(pos.current, 0.16)
    look.current.lerp(tgt.current, 0.16)
    camera.lookAt(look.current)
  })
  return null
}

function SceneFog() {
  const { scene } = useThree()
  const fog = useMemo(() => new THREE.FogExp2(0x17030a, 0.028), [])
  scene.fog = fog
  useFrame(() => {
    fog.density = 0.02 + flight.p * 0.05 - flight.morph * 0.028
  })
  return null
}

/* ── Procedural textures ──────────────────────────────────────────────── */

function usePcbTexture() {
  return useMemo(() => {
    const c = document.createElement('canvas')
    c.width = c.height = 1024
    const g = c.getContext('2d')!
    g.fillStyle = '#170610'
    g.fillRect(0, 0, 1024, 1024)
    for (let i = 0; i < 90; i++) {
      g.strokeStyle = Math.random() > 0.45 ? '#e0447c' : '#d8a24a'
      g.lineWidth = Math.random() * 2.4 + 0.8
      g.globalAlpha = Math.random() * 0.5 + 0.25
      let px = Math.random() * 1024
      let py = Math.random() * 1024
      g.beginPath()
      g.moveTo(px, py)
      const steps = 3 + ((Math.random() * 4) | 0)
      for (let s = 0; s < steps; s++) {
        if (Math.random() > 0.5) px += (Math.random() - 0.5) * 420
        else py += (Math.random() - 0.5) * 420
        g.lineTo(px, py)
      }
      g.stroke()
      g.globalAlpha = 0.85
      g.fillStyle = '#e6b96a'
      g.beginPath()
      g.arc(px, py, 3.4, 0, 7)
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
    grd.addColorStop(0.35, 'rgba(255,255,255,0.5)')
    grd.addColorStop(1, 'rgba(255,255,255,0)')
    g.fillStyle = grd
    g.fillRect(0, 0, 256, 256)
    return new THREE.CanvasTexture(c)
  }, [])
}

/* ── Hardware ─────────────────────────────────────────────────────────── */

function Board() {
  const tex = usePcbTexture()
  const mat = useRef<THREE.MeshStandardMaterial>(null)
  useFrame(() => {
    if (mat.current) mat.current.emissiveIntensity = flight.glow
  })
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2}>
        <planeGeometry args={[9, 6]} />
        <meshStandardMaterial
          ref={mat}
          map={tex}
          color="#2a0b16"
          roughness={0.82}
          metalness={0.12}
          emissiveMap={tex}
          emissive="#ff6fa6"
          emissiveIntensity={0.5}
        />
      </mesh>
      <mesh position-y={-0.07}>
        <boxGeometry args={[9.05, 0.14, 6.05]} />
        <meshStandardMaterial color="#0a0308" roughness={0.9} />
      </mesh>
    </group>
  )
}

type ChipProps = { position: [number, number, number]; size?: [number, number, number] }

function Chip({ position, size = [0.72, 0.26, 0.72] }: ChipProps) {
  return (
    <group position={position}>
      <mesh>
        <boxGeometry args={size} />
        <meshStandardMaterial color="#0c0c11" roughness={0.48} metalness={0.25} />
      </mesh>
      <mesh position-y={-size[1] / 2 + 0.03}>
        <boxGeometry args={[size[0] * 1.05, 0.05, size[2] * 1.05]} />
        <meshStandardMaterial
          color="#d8a24a"
          metalness={0.9}
          roughness={0.32}
          emissive="#3d2610"
          emissiveIntensity={0.5}
        />
      </mesh>
      <mesh position-y={size[1] / 2 + 0.002} rotation-x={-Math.PI / 2}>
        <planeGeometry args={[size[0] * 0.78, size[2] * 0.78]} />
        <meshStandardMaterial color="#151019" roughness={0.6} />
      </mesh>
    </group>
  )
}

/* The NAND bank: six chips that glide from one layout to another through the
   morph — the signature "same parts, rearranged" beat. */
function NandBank() {
  const groups = useRef<(THREE.Group | null)[]>([])
  const layoutA: [number, number, number][] = [
    [1.4, 0.15, -1.4],
    [2.1, 0.15, -1.4],
    [2.8, 0.15, -1.4],
    [1.4, 0.15, -0.6],
    [2.1, 0.15, -0.6],
    [2.8, 0.15, -0.6],
  ]
  const layoutB: [number, number, number][] = [
    [1.2, 0.15, -1.6],
    [1.2, 0.15, -0.8],
    [1.2, 0.15, 0.0],
    [3.0, 0.15, -1.6],
    [3.0, 0.15, -0.8],
    [3.0, 0.15, 0.0],
  ]
  useFrame(() => {
    const m = flight.morph
    const hop = Math.sin(m * Math.PI) * 0.7
    for (let i = 0; i < groups.current.length; i++) {
      const gr = groups.current[i]
      if (!gr) continue
      gr.position.set(
        lerp(layoutA[i][0], layoutB[i][0], m),
        lerp(layoutA[i][1], layoutB[i][1], m) + hop * (0.4 + 0.15 * i),
        lerp(layoutA[i][2], layoutB[i][2], m),
      )
      gr.rotation.y = m * Math.PI * 0.5
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
          <Chip position={[0, 0, 0]} size={[0.6, 0.22, 0.9]} />
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
      spreader.current.color.setRGB(lerp(0.72, 0.8, m), lerp(0.74, 0.46, m), lerp(0.82, 0.3, m))
    }
  })
  return (
    <group position={[0.2, 0.16, -1.2]}>
      <mesh>
        <boxGeometry args={[1.5, 0.12, 1.5]} />
        <meshStandardMaterial color="#1c1416" roughness={0.6} />
      </mesh>
      <mesh position-y={0.02}>
        <boxGeometry args={[1.72, 0.05, 1.72]} />
        <meshStandardMaterial color="#d8a24a" metalness={0.9} roughness={0.36} />
      </mesh>
      <mesh position-y={0.17}>
        <boxGeometry args={[1.02, 0.24, 1.02]} />
        <meshStandardMaterial ref={spreader} color="#b9bdc9" metalness={0.95} roughness={0.22} />
      </mesh>
    </group>
  )
}

function RamStick({ x }: { x: number }) {
  const chips = useRef<THREE.MeshStandardMaterial>(null)
  useFrame(() => {
    if (chips.current) {
      const m = flight.morph
      chips.current.color.setRGB(lerp(0.05, 0.09, m), lerp(0.05, 0.03, m), lerp(0.07, 0.09, m))
      chips.current.emissiveIntensity = 0.15 + 0.5 * flight.morph
    }
  })
  return (
    <group position={[x, 0.62, -0.4]} rotation-y={Math.PI / 2}>
      <mesh>
        <boxGeometry args={[2.4, 1.0, 0.06]} />
        <meshStandardMaterial color="#12060d" roughness={0.7} />
      </mesh>
      {[-0.8, -0.3, 0.2, 0.7].map((z) => (
        <mesh key={z} position={[z, 0.12, 0.06]}>
          <boxGeometry args={[0.4, 0.5, 0.06]} />
          <meshStandardMaterial
            ref={chips}
            color="#0c0c12"
            roughness={0.5}
            emissive="#e0447c"
            emissiveIntensity={0.15}
          />
        </mesh>
      ))}
      <mesh position={[0, -0.56, 0]}>
        <boxGeometry args={[2.2, 0.12, 0.08]} />
        <meshStandardMaterial color="#d8a24a" metalness={0.9} roughness={0.3} />
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
    if (platter.current) platter.current.rotation.y += dt * 1.6 * (1 - m)
  })
  return (
    <group position={[-3.0, 0.26, 1.7]}>
      <mesh>
        <boxGeometry args={[1.8, 0.48, 2.6]} />
        <meshStandardMaterial
          ref={hdd}
          color="#8b909b"
          metalness={0.86}
          roughness={0.3}
          transparent
          depthWrite={false}
        />
      </mesh>
      <mesh ref={platter} position-y={0.26}>
        <cylinderGeometry args={[0.7, 0.7, 0.04, 32]} />
        <meshStandardMaterial color="#c9ccd2" metalness={0.95} roughness={0.12} transparent depthWrite={false} />
      </mesh>
      <mesh position-y={-0.02}>
        <boxGeometry args={[1.62, 0.16, 2.42]} />
        <meshStandardMaterial
          ref={ssd}
          color="#160a12"
          metalness={0.2}
          roughness={0.62}
          transparent
          opacity={0}
          depthWrite={false}
        />
      </mesh>
    </group>
  )
}

function BoardChip({ position, tag }: { position: [number, number, number]; tag: string }) {
  void tag
  return <Chip position={position} size={[0.85, 0.2, 0.85]} />
}

function Monitor({ os1, os2 }: { os1: string; os2: string }) {
  const [t1, t2] = useTexture([os1, os2])
  const m1 = useRef<THREE.MeshBasicMaterial>(null)
  const m2 = useRef<THREE.MeshBasicMaterial>(null)
  useFrame(() => {
    const p = flight.p
    if (m1.current) m1.current.opacity = 1 - smoothstep(0.07, 0.15, p)
    if (m2.current) m2.current.opacity = smoothstep(0.9, 0.985, p)
  })
  return (
    <group position={[0, 1.5, 8.4]}>
      <mesh position-z={-0.12}>
        <boxGeometry args={[6.4, 4.2, 0.22]} />
        <meshStandardMaterial color="#0c0409" roughness={0.7} />
      </mesh>
      <mesh position={[0, -2.5, 0.2]}>
        <boxGeometry args={[2.2, 0.9, 1.4]} />
        <meshStandardMaterial color="#0c0409" roughness={0.7} />
      </mesh>
      <mesh>
        <planeGeometry args={[5.7, 3.5]} />
        <meshBasicMaterial ref={m1} map={t1} transparent toneMapped={false} />
      </mesh>
      <mesh position-z={0.01}>
        <planeGeometry args={[5.7, 3.5]} />
        <meshBasicMaterial ref={m2} map={t2} transparent opacity={0} toneMapped={false} />
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

      <ambientLight intensity={0.4} color="#5a1226" />
      <directionalLight position={[5, 7, 4]} intensity={1.15} color="#f0c078" />
      <pointLight position={[-3.5, 2, -4]} intensity={26} distance={16} color="#e0447c" />
      <pointLight position={[2.5, 1.5, 3]} intensity={10} distance={12} color="#f79cbc" />

      <Board />
      <Cpu />
      <NandBank />
      <RamStick x={-2.6} />
      <RamStick x={-3.0} />
      <Storage />
      <BoardChip position={[-1.6, 0.12, 1.4]} tag="locale" />
      <BoardChip position={[1.7, 0.12, 1.6]} tag="rlimit" />

      <GlowSprite
        position={[0.2, 0.6, -1.2]}
        size={5}
        color="#e0447c"
        drive={() => 0.15 + 0.55 * smoothstep(0.26, 0.4, flight.p) * (1 - smoothstep(0.5, 0.62, flight.p))}
      />
      <GlowSprite
        position={[0, 0.8, -0.5]}
        size={14}
        color="#f79cbc"
        drive={() => 0.7 * Math.sin(Math.min(1, flight.morph) * Math.PI)}
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
      camera={{ position: [0, 1.5, 13.5], fov: 42, near: 0.1, far: 60 }}
    >
      <Suspense fallback={null}>
        <World progress={progress} />
      </Suspense>
    </Canvas>
  )
}
