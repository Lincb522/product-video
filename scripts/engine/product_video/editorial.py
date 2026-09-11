"""Content-led layouts using real product images on the Remotion timeline."""
from .common import VideoError

LAYOUTS = ('overview', 'portal', 'fan', 'full', 'side', 'pair')
MOTIONS = ('none', 'panel-assemble', 'row-embed', 'camera-tour', 'focus-pull',
           'orbit-level', 'mask-reveal', 'panel-unfold', 'content-lift',
           'pull-back', 'paired-slide', 'filmstrip', 'card-flip', 'comparison-wipe')


def validate_editorial(spec, asset, font_path):
    from .config import known, number, text
    known(spec, ('layout', 'headline', 'eyebrow', 'notes', 'items', 'motion',
                 'focus_at', 'slices'), 'editorial')
    layout = spec.get('layout')
    if layout not in LAYOUTS:
        raise VideoError('editorial.layout 需为 ' + '、'.join(LAYOUTS) + '。')
    text(spec.get('headline'), '内容镜头标题', 32)
    if 'eyebrow' in spec:
        text(spec['eyebrow'], '内容镜头短标签', 36)
    notes = spec.get('notes', [])
    if not isinstance(notes, list) or len(notes) > 3:
        raise VideoError('editorial.notes 最多三条短说明。')
    for note in notes:
        text(note, '内容镜头说明', 24)
    from .text_scenes import font, wrap_text
    side = layout in ('side', 'fan')
    width, size = (455, 54) if side else (1744, 50)
    height = len(wrap_text(spec['headline'], font(font_path, size), width)) * size * 1.22
    if side:
        if spec.get('eyebrow'):
            height += len(wrap_text(spec['eyebrow'], font(font_path, 22), width)) * 22 * 1.4 + 22
        if notes:
            height += 22 + sum(len(wrap_text(note, font(font_path, 25), width)) * 35 + 18 for note in notes)
    elif notes:
        row_width, rows = 0, 1
        for note in notes:
            length = font(font_path, 23).getlength(note)
            if row_width and row_width + 32 + length > width:
                rows += 1
                row_width = 0
            row_width += length + (32 if row_width else 0)
        height += 22 + rows * 23 * 1.4
    if height > (700 if side else 129):
        raise VideoError('内容镜头正文超出安全区，请缩短说明、减少换行或拆分镜头。')
    motion = spec.get('motion', 'none')
    if motion not in MOTIONS:
        raise VideoError('editorial.motion 不存在，请查看内容镜头说明。')
    items = spec.get('items')
    count_range = (2, 6) if layout in ('overview', 'portal') or motion == 'filmstrip' else (2, 3) if layout == 'fan' else (2, 2) if layout == 'pair' or motion == 'card-flip' else (1, 1)
    if not isinstance(items, list) or not count_range[0] <= len(items) <= count_range[1]:
        raise VideoError(f'{layout} / {motion} 需要 {count_range[0]}–{count_range[1]} 张真实图片。')
    if layout in ('overview', 'portal', 'fan') and 'motion' in spec:
        raise VideoError('overview、portal 和 fan 使用自身运动，不叠加 motion。')
    if layout == 'pair' and motion not in ('none', 'paired-slide', 'comparison-wipe'):
        raise VideoError('pair 使用 none、paired-slide 或 comparison-wipe。')
    if motion == 'comparison-wipe' and layout != 'pair':
        raise VideoError('comparison-wipe 需要 pair 版式和两张对应截图。')
    for item in items:
        known(item, ('source', 'label'), 'editorial.items')
        item['source'] = asset(item.get('source'))
        if layout in ('overview', 'portal') or 'label' in item:
            text(item.get('label'), '内容镜头图片标签', 20)
    if motion == 'comparison-wipe':
        from PIL import Image, ImageOps
        ratios = []
        for item in items:
            with Image.open(item['source']) as source:
                width, height = ImageOps.exif_transpose(source).size
                ratios.append(width / height)
        if abs(ratios[0] / ratios[1] - 1) > .01:
            raise VideoError('comparison-wipe 的两张截图需使用相同比例；不同页面请用 pair 并排展示。')
    if 'focus_at' in spec:
        points = spec['focus_at']
        if layout != 'overview' or not isinstance(points, list) or len(points) != len(items):
            raise VideoError('focus_at 仅用于 overview，数量需与图片一致。')
        previous = -1
        for point in points:
            number(point, 0, .9, 'focus_at')
            if point <= previous:
                raise VideoError('focus_at 必须严格递增。')
            previous = point
    if 'slices' in spec:
        cuts = spec['slices']
        if motion not in ('row-embed', 'panel-assemble') or not isinstance(cuts, list) or not 3 <= len(cuts) <= 9:
            raise VideoError('slices 用于逐行或分栏展开，需包含 0、1 和中间边界。')
        for point in cuts:
            number(point, 0, 1, 'slices')
        if cuts[0] != 0 or cuts[-1] != 1 or any(a >= b for a, b in zip(cuts, cuts[1:])):
            raise VideoError('slices 必须从 0 严格递增到 1。')


def review_offsets(duration, spec, fps):
    """Include motion phases and each overview focus, not only settled stills."""
    times = [0, .5 * fps, 4 / 3 * fps, 2.5 * fps, duration / 2, duration - 1]
    if spec['layout'] == 'overview':
        points = spec.get('focus_at', [.08 + i * .72 / len(spec['items']) for i in range(len(spec['items']))])
        times.extend(point * duration + 1.6 * fps for point in points)
    return sorted({min(duration - 1, max(0, round(t))) for t in times})
