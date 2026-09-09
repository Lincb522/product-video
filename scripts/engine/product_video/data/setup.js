const form = document.querySelector('#setup');
const status = document.querySelector('#status');
const buttons = [...form.querySelectorAll('button')];
async function submit(cancel) {
  if (!cancel && !form.reportValidity()) return;
  buttons.forEach(b => b.disabled = true);
  status.className = 'status';
  status.textContent = cancel ? '正在取消…' : '正在保存…';
  const data = new URLSearchParams({csrf: form.elements.csrf.value});
  if (!cancel) data.set('key', form.elements.key.value);
  try {
    const response = await fetch(cancel ? '/cancel' : '/save', {method: 'POST', body: data, signal: AbortSignal.timeout(10000)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    form.elements.key.value = '';
    form.elements.key.disabled = true;
    status.textContent = result.message;
  } catch (error) {
    status.className = 'status error';
    status.textContent = error instanceof TypeError || error.name === 'TimeoutError'
      ? '本机配置页面已关闭或未响应。请重新运行任务后再配置。' : error.message;
    buttons.forEach(b => b.disabled = false);
  }
}
form.addEventListener('submit', event => {event.preventDefault(); submit(false);});
document.querySelector('#cancel').addEventListener('click', () => submit(true));
