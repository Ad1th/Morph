import { chromium } from 'playwright'

const OUT = process.env.SHOT_DIR || '/tmp/morph-shots'
const positions = process.argv.slice(2).map(Number)
const vhs = positions.length ? positions : [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
const W = Number(process.env.SHOT_W || 1440)
const H = Number(process.env.SHOT_H || 900)

const { mkdirSync } = await import('node:fs')
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch({
  headless: true,
  channel: 'chromium',
  args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'],
})
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 })
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))
page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()) })

await page.goto('http://localhost:5174/?static', { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)

for (const vh of vhs) {
  const y = Math.round((vh / 100) * H)
  await page.evaluate((yy) => window.scrollTo(0, yy), y)
  await page.waitForTimeout(1600)
  const path = `${OUT}/s_${String(vh).padStart(4, '0')}vh.png`
  await page.screenshot({ path })
  console.log('wrote', path)
}

if (errors.length) {
  console.log('\n--- page errors ---')
  for (const e of [...new Set(errors)].slice(0, 20)) console.log(e)
}
await browser.close()
