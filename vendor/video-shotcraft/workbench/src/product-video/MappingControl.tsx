import { useId, useState } from 'react';
import type { PropField } from '../cards/types';
import { parseMap } from './adaptation';
import { MEDIA_ITEMS } from '../mediaManifest';

export function MappingControl({ field, value, onChange, onBegin }: { field: Extract<PropField, { type: 'mapping' }>; value: unknown; onChange: (value: unknown) => void; onBegin: () => void }) {
  const id = useId();
  const [source, setSource] = useState('');
  const map = parseMap(value, field.label);
  const update = (key: string, next: string) => { onBegin(); onChange({ ...map, [key]: next }); };
  return <div className="pv-mapping">
    {Object.entries(map).map(([key, current]) => <div className="pv-mapping-entry" key={key}>
      <label><span className="pv-source" title={key}>{key}</span>
        {field.kind === 'text' ? <textarea aria-label={`替换 ${key}`} rows={2} value={current} onChange={e => update(key, e.target.value)} /> :
          <input aria-label={`替换 ${key}`} type="text" list={field.kind === 'media' ? `${id}-media` : undefined} value={current} onChange={e => update(key, e.target.value)} />}
      </label>
      <button className="mini" aria-label={`移除替换 ${key}`} onClick={() => { onBegin(); const next = { ...map }; delete next[key]; onChange(next); }}>移除</button>
    </div>)}
    <div className="pv-add-mapping"><input aria-label={`${field.label}原值`} list={`${id}-sources`} placeholder={field.kind === 'text' ? '选择或输入要替换的原文' : field.kind === 'media' ? '选择原素材' : '选择原色值'} value={source} onChange={e => setSource(e.target.value)} />
      <button className="btn" disabled={!source.trim() || Object.prototype.hasOwnProperty.call(map, source.trim())} onClick={() => { update(source.trim(), source.trim()); setSource(''); }}>添加</button>
    </div>
    <datalist id={`${id}-sources`}>{field.suggestions?.map(item => <option key={item} value={item} />)}</datalist>
    <datalist id={`${id}-media`}>{MEDIA_ITEMS.filter(item => item.kind === 'image' || item.kind === 'video').map(item => <option key={item.file} value={item.file} />)}</datalist>
  </div>;
}
