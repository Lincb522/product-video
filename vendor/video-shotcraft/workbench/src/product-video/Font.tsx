import { useEffect, useState } from 'react';
import { cancelRender, continueRender, delayRender, staticFile } from 'remotion';

export function ProductFont({ file }: { file: string }) {
  const [handle] = useState(() => delayRender('Loading product font'));
  useEffect(() => {
    const face = new FontFace('ProductVideoFont', `url(${JSON.stringify(staticFile(file))})`);
    let active = true;
    face.load().then(font => { document.fonts.add(font); if (active) continueRender(handle); })
      .catch(error => { if (active) cancelRender(error); });
    return () => { active = false; continueRender(handle); };
  }, [file, handle]);
  return null;
}
