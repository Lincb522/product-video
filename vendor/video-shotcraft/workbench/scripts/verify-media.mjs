import {spawnSync} from 'node:child_process';

export const decodeTimeout = duration => Math.max(120000, Math.ceil(duration * 3000));

export function verifyMedia(movie, composition) {
  const result = spawnSync('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', movie], {encoding:'utf8', timeout:30000});
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error('无法读取导出视频信息。'+result.stderr.slice(-1000));
  const data = JSON.parse(result.stdout), video = data.streams.find(s=>s.codec_type==='video'), audio = data.streams.find(s=>s.codec_type==='audio');
  const duration = composition.durationInFrames / composition.fps;
  if (!video || !audio || video.width !== composition.width || video.height !== composition.height || video.pix_fmt !== 'yuv420p' || Math.abs(Number(data.format.duration)-duration) > .12) throw new Error('导出文件的画面、音轨或时长未通过校验。');
  const decoded = spawnSync('ffmpeg', ['-v', 'error', '-xerror', '-i', movie, '-f', 'null', '-'], {encoding:'utf8', timeout:decodeTimeout(duration)});
  if (decoded.error) throw decoded.error;
  if (decoded.status !== 0) throw new Error('导出视频未通过完整解码。'+decoded.stderr.slice(-1000));
  return {full_decode:'passed',width:video.width,height:video.height,duration:Number(data.format.duration),audio_codec:audio.codec_name};
}
