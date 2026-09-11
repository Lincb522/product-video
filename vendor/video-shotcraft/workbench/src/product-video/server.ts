import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { cpSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import type { Plugin } from 'vite';

type Job = { status: 'running' | 'done' | 'error'; message: string; project?: unknown; revision?: string };
export function productVideoPlugin(): Plugin {
  const revisionOf = (value: string) => createHash('sha256').update(value).digest('hex');
  let job: Job | null = null;
  let serial = 0;
  return { name: 'product-video-voice', configureServer(server) {
    const source = process.env.PRODUCT_VIDEO_PROJECT;
    const studio = process.env.PRODUCT_VIDEO_STUDIO;
    const python = process.env.PRODUCT_VIDEO_PYTHON;
    server.middlewares.use('/api/product-video', (req, res) => {
      const send = (status: number, body: unknown) => { res.statusCode = status; res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(body)); };
      if (!source || !studio || !python) { send(409, { error: '请通过 product-video studio 打开一个配音项目。' }); return; }
      const endpoint = (req.url ?? '/').split('?')[0];
      if (req.method === 'GET' && endpoint === '/job') { send(200, job); return; }
      if (req.method === 'GET' && endpoint === '/') {
        try {
          const sourceText = readFileSync(source, 'utf8');
          const config = JSON.parse(sourceText);
          const voices = JSON.parse(readFileSync(path.resolve('../../../scripts/engine/product_video/data/voices.json'), 'utf8')).voices.map((v: { id: string; names: string[] }) => ({ id: v.id, names: v.names }));
          send(200, { revision: revisionOf(sourceText), name: config.product.name, voice: config.voice ?? {}, voices, chapters: config.chapters.map((c: { id: string; title: string; narration: string }) => ({ id: c.id, title: c.title, narration: c.narration })), project: JSON.parse(readFileSync(path.join(studio, 'project.json'), 'utf8')) });
        } catch { send(500, { error: '无法读取当前配音项目。' }); }
        return;
      }
      if (req.method !== 'POST' || endpoint !== '/voice') { send(404, { error: '接口不存在。' }); return; }
      if (job?.status === 'running') { send(409, { error: '配音任务正在运行。' }); return; }
      let raw = '', oversized = false;
      req.on('data', chunk => { raw += chunk; if (raw.length > 1_000_000) { oversized = true; req.destroy(); } });
      req.on('end', () => {
        if (oversized) return;
        if (job?.status === 'running') { send(409, { error: '配音任务正在运行。' }); return; }
        try {
          const update = JSON.parse(raw);
          const sourceText = readFileSync(source, 'utf8');
          const config = JSON.parse(sourceText);
          const originalConfig = JSON.stringify(config);
          if (update.revision !== revisionOf(sourceText)) { send(409, { error: '项目已在其他位置修改，请刷新工作台后再生成。' }); return; }
          if (typeof update.speaker !== 'string' || !update.speaker.trim() || !Array.isArray(update.chapters) || update.chapters.length !== config.chapters.length) throw new Error('请填写音色和每章旁白。');
          config.chapters = config.chapters.map((chapter: { id: string; narration: string; captions?: unknown }, i: number) => {
            const next = update.chapters[i];
            if (next.id !== chapter.id || typeof next.narration !== 'string' || !next.narration.trim() || next.narration.length > 2000) throw new Error('章节不匹配，或旁白超过 2000 字。');
            if (next.narration !== chapter.narration) delete chapter.captions;
            return { ...chapter, narration: next.narration };
          });
          const changedVoice = config.voice?.speaker !== update.speaker.trim();
          config.voice = { ...config.voice, speaker: update.speaker.trim() };
          // Resolve model/transport with the existing voice selector before generation.
          if (changedVoice) { delete config.voice.resource_id; delete config.voice.transport; }
          config.schema_version = 2;
          config.video = { ...config.video, renderer: 'remotion' };
          const pending = `${source}.pending-${process.pid}-${++serial}`;
          if (JSON.stringify(config) !== originalConfig) { writeFileSync(pending, JSON.stringify(config, null, 2)); renameSync(pending, source); }
          job = { status: 'running', message: '正在生成缺失的配音并对齐镜头…', revision: revisionOf(readFileSync(source, 'utf8')) };
          const current = job;
          const child = spawn(python, ['-m', 'product_video', 'prepare-motion', source, '--generate-voice'], { cwd: path.dirname(source) });
          let tail = '';
          const record = (data: Buffer) => { tail = (tail + data.toString()).slice(-3000); const lines = tail.trim().split('\n'); current.message = lines[lines.length - 1] || current.message; };
          child.stdout.on('data', record); child.stderr.on('data', record);
          const shutdown = () => child.kill('SIGINT');
          server.httpServer?.once('close', shutdown);
          const timer = setTimeout(() => { current.message = '配音任务超时，已停止；已完成缓存保留。'; child.kill('SIGTERM'); setTimeout(() => { if (child.exitCode === null) child.kill('SIGKILL'); }, 10000).unref(); }, 3_600_000);
          child.on('error', error => { clearTimeout(timer); current.status = 'error'; current.message = error.message; });
          child.on('close', code => {
            clearTimeout(timer); server.httpServer?.removeListener('close', shutdown);
            if (code !== 0) { current.status = 'error'; return; }
            try {
              const output = path.resolve(path.dirname(source), config.output ?? 'output');
              const generated = JSON.parse(readFileSync(path.join(output, 'studio.json'), 'utf8'));
              if (path.resolve(generated.directory) !== path.resolve(studio)) cpSync(path.join(generated.directory, 'public'), path.join(studio, 'public'), { recursive: true });
              const project = JSON.parse(readFileSync(generated.project, 'utf8'));
              writeFileSync(path.join(studio, 'project.json'), JSON.stringify(project, null, 2));
              current.revision = revisionOf(readFileSync(source, 'utf8')); current.project = project; current.status = 'done'; current.message = '旁白、字幕和镜头时间轴已更新。';
            } catch (error) { current.status = 'error'; current.message = `配音已完成，时间轴加载失败：${String(error)}`; }
          });
          send(202, { status: 'running' });
        } catch (error) { send(400, { error: String(error) }); }
      });
    });
  } };
}
