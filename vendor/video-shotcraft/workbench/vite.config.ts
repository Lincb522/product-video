// Product Video integration: modified from video-shotcraft 5e71af3; see MODIFICATIONS.md.
import { existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { productVideoPlugin } from './src/product-video/server';

// @proj = 外部成片工程源码（本机经 workbench/proj 符号链接接入，不进库；scripts/open.mjs 负责链接）。
// 未链接时自动落到 proj-stub 降级实现：工程可构建可运行，素材 tab 显示接入提示。
// @demos resolves to the complete motion sources through the setup-generated demosrc link.
// preserveSymlinks 让两者按虚拟路径解析，其 'react'/'remotion' 裸导入
// 落到本工程 node_modules（避免双实例）；src/proj.d.ts 让 tsc 不检查外部源码。
const root = fileURLToPath(new URL(".", import.meta.url));
const publicDir = process.env.PRODUCT_VIDEO_STUDIO ? path.join(process.env.PRODUCT_VIDEO_STUDIO, 'public') : path.join(root, 'public');
// 工程链接了但没写 src/workbench.ts 清单时也回退到 stub（工作台只 import @proj/workbench 这一个模块）
const proj = existsSync(path.join(root, "proj", "workbench.ts")) ? "proj" : "proj-stub";

/** Export through the shared Product Video Remotion renderer.
 *  前端 POST /api/export 提交工程 JSON，轮询 GET /api/export/:id 取进度。 */
type ExportJob = {
  status: "running" | "done" | "error";
  progress: number; // 0..1
  output: string; // Absolute path to the exported MP4.
  lastLine: string;
  logTail: string[];
};

const renderExportPlugin = (): Plugin => {
  const jobs = new Map<string, ExportJob>();
  const stripAnsi = (s: string) => s.replace(/\x1b\[[0-9;]*[A-Za-z]/g, "");

  return {
    name: "wb-render-export",
    configureServer(server) {
      // 每个任务结束（成功/失败/同步失败）都即时删除 props 文件；启动时清掉历史残留
      const exportsDir = path.join(process.env.PRODUCT_VIDEO_STUDIO ?? root, "exports");
      if (existsSync(exportsDir)) {
        for (const f of readdirSync(exportsDir)) {
          if (/^\.props-[a-z0-9]+\.json$/.test(f)) rmSync(path.join(exportsDir, f), { force: true });
        }
      }
      server.middlewares.use("/api/export", (req, res) => {
        const send = (code: number, body: unknown) => {
          res.statusCode = code;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify(body));
        };
        const sub = (req.url ?? "/").split("?")[0];

        // POST /api/export —— 提交渲染
        if (req.method === "POST" && (sub === "/" || sub === "")) {
          if ([...jobs.values()].some((j) => j.status === "running")) {
            send(409, { error: "已有渲染在进行中" });
            return;
          }
          let raw = "";
          req.on("data", c => { raw += c; if (raw.length > 5_000_000) req.destroy(); });
          req.on("end", () => {
            if ([...jobs.values()].some(job => job.status === "running")) { send(409, { error: "已有渲染在进行中" }); return; }
            let project: { name?: string };
            try {
              project = JSON.parse(raw).project;
              if (!project) throw new Error("no project");
            } catch {
              send(400, { error: "缺少工程 JSON" });
              return;
            }
            const id = Date.now().toString(36);
            const outDir = exportsDir;
            mkdirSync(outDir, { recursive: true });
            const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
            const safeName =
              (project.name ?? "工程").replace(/[^\w一-龥·-]+/g, "_").slice(0, 40) || "工程";
            const output = path.join(outDir, `${safeName}-${stamp}.mp4`);
            const propsFile = path.join(outDir, `.props-${id}.json`);
            writeFileSync(propsFile, JSON.stringify({ project, publicDir, output, verifyOutput: true }));
            const dropProps = () => rmSync(propsFile, { force: true });

            const job: ExportJob = {
              status: "running",
              progress: 0,
              output,
              lastLine: "同步素材…",
              logTail: [],
            };
            jobs.set(id, job);

            const onChunk = (buf: Buffer) => {
              const lines = stripAnsi(buf.toString()).split(/[\r\n]+/).filter((l) => l.trim());
              for (const line of lines) {
                job.lastLine = line.trim();
                job.logTail = [...job.logTail, line.trim()].slice(-40);
                // Remotion CLI 进度形如 "Rendered 123/5544"，取最后一处 a/b
                const m = [...line.matchAll(/(\d+)\/(\d+)/g)].pop();
                if (m && Number(m[2]) > 0) job.progress = Number(m[1]) / Number(m[2]);
                const percent = /Remotion render (\d+)%/.exec(line);
                if (percent) job.progress = Number(percent[1])/100;
              }
            };

            const child = spawn(process.execPath, ['scripts/product-video.mjs', 'render', propsFile], { cwd: root });
            let stopped = false;
            const timeout = setTimeout(() => { stopped = true; job.lastLine = '导出超过两小时，任务已停止；请缩短工程后重试。'; child.kill('SIGTERM'); setTimeout(() => { if (child.exitCode === null) child.kill('SIGKILL'); }, 10000).unref(); }, 7_200_000);
            const shutdown = () => child.kill('SIGTERM');
            server.httpServer?.once('close', shutdown);
            child.stdout.on('data', onChunk); child.stderr.on('data', onChunk);
            child.on('error', error => { clearTimeout(timeout); dropProps(); job.status = 'error'; job.lastLine = error.message; });
            child.on('close', code => {
              clearTimeout(timeout); server.httpServer?.removeListener('close', shutdown); dropProps();
              job.status = code === 0 && !stopped ? 'done' : 'error';
              if (job.status === 'done') job.progress = 1;
              else if (!stopped) job.lastLine = job.logTail.find(line => line.includes('Error')) ?? job.lastLine;
            });
            send(200, { id });
          });
          return;
        }

        // GET /api/export/:id —— 查进度
        const m = sub.match(/^\/([a-z0-9]+)(\/reveal)?$/);
        const job = m ? jobs.get(m[1]) : undefined;
        if (!job) {
          send(404, { error: "任务不存在" });
          return;
        }
        // POST /api/export/:id/reveal —— Finder 里显示成片
        if (req.method === "POST" && m![2]) {
          if (process.platform === "darwin") spawn("open", ["-R", job.output]);
          send(200, { ok: true });
          return;
        }
        send(200, job);
      });
    },
  };
};

export default defineConfig({
  plugins: [react(), productVideoPlugin(), renderExportPlugin()],
  publicDir,
  // 5198：与 video-talkcraft 的工作台（5199）错开，两边可同时开
  server: { port: 5198, strictPort: true },
  resolve: {
    dedupe: ['react', 'react-dom', 'remotion', '@remotion/motion-blur'],
    preserveSymlinks: true,
    alias: { "@pv": path.join(root, "src/product-video"), "@shotcraft-lib": path.join(root, "../assets/lib"), "@proj": path.join(root, proj), "@demos": path.join(root, "demosrc") },
  },
  // 外部工程 / demo 源码经符号链接进来，依赖预构建要认得它们的裸导入
  optimizeDeps: { include: ["react", "react-dom", "remotion", "@remotion/motion-blur"] },
});
