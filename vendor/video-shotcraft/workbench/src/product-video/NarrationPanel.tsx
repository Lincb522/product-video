import { useEffect, useRef, useState } from 'react';
import { useStore } from '../store';
import type { ProjectData } from '../types';

type Chapter = { id: string; title: string; narration: string };
type Voice = { id: string; names: string[] };
export function NarrationPanel() {
  const [open, setOpen] = useState(false);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [speaker, setSpeaker] = useState('');
  const [voiceSearch, setVoiceSearch] = useState('');
  const [revision, setRevision] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const mounted = useRef(true);
  useEffect(() => { if (open) dialog.current?.querySelector<HTMLButtonElement>('button')?.focus(); }, [open]);
  const close = () => { setOpen(false); trigger.current?.focus(); };
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    let active = true; mounted.current = true;
    fetch('/api/product-video/').then(async response => {
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      if (!active) return;
      setRevision(data.revision); setChapters(data.chapters); setSpeaker(data.voice.speaker ?? 'zh_female_xiaohe_uranus_bigtts'); setVoices(data.voices); setReady(true);
      const current = useStore.getState().project;
      if (current.source !== data.project.source) useStore.getState().setProject(data.project);
    }).catch(error => { if (active) setStatus(error.message); });
    return () => { active = false; mounted.current = false; window.clearTimeout(timer.current); };
  }, []);
  const poll = async () => {
    try {
      const response = await fetch('/api/product-video/job');
      if (!response.ok) throw new Error('无法读取配音进度，请检查工作台服务。');
      const job = await response.json();
      if (!mounted.current) return;
      if (!job) { setBusy(false); setStatus('工作台服务已重启。已完成缓存保留，请重新生成。'); return; }
      setStatus(job.message);
      if (job.status === 'running') { timer.current = window.setTimeout(poll, 1500); return; }
      setBusy(false);
      if (job.revision) setRevision(job.revision);
      if (job.status === 'done') {
        const next = job.project as ProjectData;
        const previous = useStore.getState().project;
        const oldShots = previous.tracks.find(t => t.id === 'shots')?.clips ?? [];
        for (const shot of next.tracks.find(t => t.id === 'shots')?.clips ?? []) {
          const old = oldShots.find(c => c.id === shot.id && c.cardId === shot.cardId);
          if (old) Object.assign(shot, { props: old.props, scale: old.scale, opacity: old.opacity, x: old.x, y: old.y, transition: old.transition ?? shot.transition });
        }
        useStore.getState().setProject(next);
      }
    } catch (error) { setBusy(false); setStatus(String(error)); }
  };
  const generate = async () => {
    setBusy(true); setStatus('正在提交配音任务…');
    try {
      const response = await fetch('/api/product-video/voice', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ speaker, chapters, revision }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      await poll();
    } catch (error) { setBusy(false); setStatus(String(error)); }
  };
  return <>
    <button ref={trigger} className="btn" onClick={() => setOpen(true)}>旁白与字幕</button>
    {open && <div className="pv-dialog-backdrop" onKeyDown={e => {
      e.stopPropagation();
      if (e.key === 'Escape') close();
      if (e.key === 'Tab') {
        const nodes = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]') ?? []);
        const first = nodes[0], last = nodes[nodes.length-1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    }}>
      <section ref={dialog} className="pv-narration" role="dialog" aria-modal="true" aria-labelledby="pv-voice-title">
        <header><h2 id="pv-voice-title">旁白与字幕</h2><button className="btn" onClick={close}>关闭</button></header>
        <label>搜索音色<input value={voiceSearch} placeholder="输入角色名称" onChange={e => setVoiceSearch(e.target.value)} /></label>
        <label>配音角色<select value={speaker} disabled={busy || !ready} onChange={e => setSpeaker(e.target.value)}>
          {voices.filter(voice => voice.id === speaker || voice.names.join(' ').toLowerCase().includes(voiceSearch.toLowerCase())).map(voice => <option key={voice.id} value={voice.id}>{voice.names.join(' / ')}</option>)}
        </select></label>
        <div className="pv-chapters">{chapters.map((chapter, i) => <label key={chapter.id}>
          <span>{i+1}. {chapter.title}</span>
          <textarea value={chapter.narration} disabled={busy} maxLength={2000} onChange={e => setChapters(rows => rows.map((row, index) => index === i ? { ...row, narration: e.target.value } : row))} />
        </label>)}</div>
        <p>生成后按实际语音重新对齐字幕与镜头；未改动的配音会复用缓存。</p>
        <p>重新配音会使用已配置的语音服务额度。时间轴的更新可以撤销。</p>
        <div role="status" className="pv-status">{status}</div>
        <button className="btn primary" disabled={busy || !ready} onClick={generate}>{busy ? '正在生成…' : '生成配音并更新镜头'}</button>
      </section>
    </div>}
  </>;
}
