import { verifyMedia } from './verify-media.mjs';
import { bundle } from '@remotion/bundler';
import { getCompositions, renderMedia, renderStill, openBrowser } from '@remotion/renderer';
import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const [action, requestFile] = process.argv.slice(2);
const request = JSON.parse(readFileSync(requestFile, 'utf8'));
const inputProps = request.project ? { project: request.project, renderExact: true } : {};
const publicDir = path.resolve(request.publicDir);
mkdirSync(publicDir, { recursive: true });
const copies = [
  ['../demos/_textures', 'textures/live'],
  ['../assets/clips', 'clips'],
  ['../assets/audio/sfx', 'sfxlib'],
  ['../assets/audio/bgm', 'bgmlib'],
];
for (const [from, to] of copies) {
  const dest = path.join(publicDir, to);
  if (!existsSync(dest)) cpSync(path.join(root, from), dest, { recursive: true, dereference: true });
}
const serveUrl = await bundle({
  entryPoint: path.join(root, 'src/remotion/index.ts'),
  publicDir,
  webpackOverride: config => ({ ...config, resolve: { ...config.resolve, symlinks: false,
    modules: [path.join(root, 'node_modules'), 'node_modules'],
    alias: { '@pv': path.join(root, 'src/product-video'), '@shotcraft-lib': path.join(root, '../assets/lib'), ...config.resolve?.alias, '@demos': path.join(root, 'demosrc'), '@proj': path.join(root, 'proj-stub') },
  } }),
  onProgress: p => { if (p === 100) console.log('Motion bundle ready.'); },
});
const chromiumOptions = { gl: process.platform === 'darwin' ? 'angle' : 'swangle' };
const browser = await openBrowser('chrome', { browserExecutable: request.browserExecutable ?? null, chromiumOptions });
try {
  const options = { serveUrl, inputProps, puppeteerInstance: browser, chromiumOptions, timeoutInMilliseconds: 90000 };
  const compositions = await getCompositions(serveUrl, options);
  if (action === 'catalog') {
    writeFileSync(request.output, JSON.stringify(compositions.map(({ id, width, height, fps, durationInFrames }) => ({ id, width, height, fps, durationInFrames })), null, 2));
  } else if (action === 'smoke') {
    mkdirSync(request.output, { recursive: true });
    const coverageFile = path.join(request.output, 'coverage.json');
    const old = request.resume && existsSync(coverageFile) ? JSON.parse(readFileSync(coverageFile, 'utf8')) : [];
    const results = old.filter(x => x.status === 'passed' && request.compositions.includes(x.id) && !(request.recheck ?? []).includes(x.id));
    const pending = request.compositions.filter(id => !results.some(x => x.id === id));
    const worker = async () => {
      for (;;) {
        const id = pending.shift();
        if (!id) return;
        const composition = compositions.find(c => c.id === id);
        try {
          if (!composition) throw new Error(`Composition missing: ${id}`);
          for (const [phase, frame] of [['start', 0], ['middle', Math.floor(composition.durationInFrames * .5)], ['end', composition.durationInFrames - 1]]) {
            await renderStill({ ...options, composition, frame, scale: request.scale ?? .5, output: path.join(request.output, `${id}-${phase}.png`) });
          }
          results.push({ id, status: 'passed', frames: composition.durationInFrames });
        } catch (error) { results.push({ id, status: 'failed', error: String(error) }); }
        writeFileSync(coverageFile, JSON.stringify(results, null, 2));
        console.log(`Motion review ${results.length}/${request.compositions.length}: ${id} ${results.at(-1).status}`);
      }
    };
    await Promise.all(Array.from({length: Math.max(1, Math.min(4, request.workers ?? 1))}, worker));
    if (results.some(x => x.status !== 'passed')) process.exitCode = 1;
  } else {
    const composition = compositions.find(c => c.id === (request.composition ?? 'Main'));
    if (!composition) throw new Error('Requested composition is unavailable');
    if (action === 'still') {
      for (const item of request.frames) await renderStill({ ...options, composition, frame: item.frame, output: item.output });
    } else if (action === 'render') {
      let previous = -1;
      await renderMedia({ ...options, composition, frameRange: request.frameRange, outputLocation: request.output, codec: 'h264', audioCodec: 'aac', enforceAudioTrack: true,
        crf: 18, pixelFormat: 'yuv420p', colorSpace: 'bt709', imageFormat: 'jpeg', jpegQuality: 95, concurrency: Math.max(1, Math.min(4, request.concurrency ?? 2)),
        onProgress: ({ progress }) => { const percent = Math.floor(progress * 100); if (percent >= previous + 5) { previous = percent; console.log(`Remotion render ${percent}%`); } },
      });
      if (request.verifyOutput) {
        writeFileSync(request.output+'.verify.json', JSON.stringify(verifyMedia(request.output, composition), null, 2));
      }
    } else throw new Error(`Unknown operation: ${action}`);
  }
} finally { await browser.close({ silent: true }); }
