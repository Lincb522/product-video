import {getInstalledBrowsers} from '@puppeteer/browsers';
import {readFileSync, existsSync} from 'node:fs';
import {homedir} from 'node:os';
import {join} from 'node:path';

const config = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8'));
const override = process.env.HYPERFRAMES_BROWSER_PATH;
const browsers = override ? [] : await getInstalledBrowsers({cacheDir: join(homedir(), '.cache/hyperframes/chrome')});
const path = override || browsers.find(item => item.buildId === config.productVideo.browserVersion)?.executablePath;
if (!path || !existsSync(path)) {
  console.error('Hyperframes 浏览器未就绪，请运行 scripts/setup-hyperframes.sh；自定义浏览器可用 HYPERFRAMES_BROWSER_PATH 指定。');
  process.exit(1);
}
process.stdout.write(path);
