import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import path from 'node:path';
import {decodeTimeout, verifyMedia} from './verify-media.mjs';
import { build } from 'esbuild';
try {
  await build({entryPoints:['src/product-video/Transition.tsx','src/product-video/adaptation.tsx'],bundle:true,platform:'node',format:'esm',packages:'external',outdir:'.product-video-test',jsx:'automatic'});
  const catalog=JSON.parse(readFileSync('../motion-catalog.json','utf8'));
  const frameCount=name=>catalog.motions.find(m=>m.component===name).frames;
  assert.equal(frameCount('LetterspaceMaterialize'),110);
  assert.equal(frameCount('TitleDemoteToLabel'),196);
  assert.equal(frameCount('PillSlotCycle'),175);
  const { TRANSITIONS, transitionStyles } = await import('../.product-video-test/Transition.js');
  const { parseMap, replaceText } = await import('../.product-video-test/adaptation.js');
  for (const kind of TRANSITIONS) {
    assert.deepEqual(transitionStyles(kind,1,1920,1080),[{opacity:0},{}]);
    if (kind !== 'cut') assert.deepEqual(transitionStyles(kind,0,1920,1080),[{}, {opacity:0}]);
    const middle=transitionStyles(kind,.5,1920,1080);
    assert(!JSON.stringify(middle).includes('NaN'));
  }
  const [left]=transitionStyles('slide-left',.5,1920,1080);
  const [right]=transitionStyles('slide-right',.5,1920,1080);
  assert.equal(left.transform,'translateX(-960px)'); assert.equal(right.transform,'translateX(960px)');
  assert.notDeepEqual(transitionStyles('iris',.5,1920,1080),transitionStyles('fade',.5,1920,1080));
  assert.equal(replaceText('  Original  ',{Original:'产品视频'}),'  产品视频  ');
  assert.equal(replaceText('Original version',{Original:'产品视频'}),'Original version');
  assert.deepEqual(parseMap('{"Title":"产品视频"}','copy'),{Title:'产品视频'});
  assert.throws(()=>parseMap('{"Title":7}','copy'));
  assert.throws(()=>parseMap('[]','copy'));
  const timeout=decodeTimeout(330.9);
  assert(Number.isInteger(timeout));
  assert.equal(spawnSync(process.execPath,['-e','process.exit(0)'],{timeout}).status,0);
  const temp=mkdtempSync(path.join(tmpdir(),'product-video-export-'));
  try {
    const movie=path.join(temp,'long.mp4');
    const encoded=spawnSync('ffmpeg',['-v','error','-f','lavfi','-i','color=size=160x90:rate=30','-f','lavfi','-i','anullsrc=r=8000:cl=mono','-t','330.9','-c:v','libx264','-preset','ultrafast','-c:a','aac',movie],{encoding:'utf8',timeout:120000});
    assert.equal(encoded.status,0,encoded.stderr);
    const composition={width:160,height:90,fps:30,durationInFrames:9927};
    assert.equal(verifyMedia(movie,composition).full_decode,'passed');
    assert.throws(()=>verifyMedia(movie,{...composition,width:320}),/未通过校验/);
  } finally {rmSync(temp,{recursive:true,force:true});}
  console.log('15 transition endpoints, direction, content scope and malformed mapping checks passed.');
  console.log('330.9-second export verification passed with an integer process timeout.');
} finally {
  const { rmSync } = await import('node:fs'); rmSync(new URL('../.product-video-test',import.meta.url),{recursive:true,force:true});
}
