#!/usr/bin/env python3
"""Package the complete skill without runtimes, credentials or local projects."""
from pathlib import Path
import argparse
import json
import stat
import zipfile

SKIP_PARTS = {'.git', 'node_modules', '.venv', '__pycache__', '.pytest_cache', 'dist', 'build', '.cache', 'exports', '.render-public', '.parity', '.captures', 'output'}
SKIP_SUFFIX = ('.pyc', '.tsbuildinfo', '.egg-info', '.before-voice', '.log', '.pending', '.lock')
LOCAL_FILES = {'src/mediaManifest.ts', 'src/projMeta.ts', 'src/cards/demo-index.ts', 'src/cards/demoMeta.ts'}


def package(root, destination):
    root, destination = root.resolve(), destination.resolve()
    if destination.is_relative_to(root):
        raise ValueError('Write the archive outside the skill source directory.')
    entries = []
    for file in sorted(root.rglob('*')):
        rel = file.relative_to(root)
        if any(p in SKIP_PARTS or p.startswith('.env') or p.endswith('.egg-info') for p in rel.parts):
            continue
        credential_artifact = file.name.startswith('credentials') and file.suffix != '.py'
        if file.name == '.DS_Store' or credential_artifact or file.name.endswith(SKIP_SUFFIX) or file.suffix in ('.key', '.pem'):
            continue
        wb = 'vendor/video-shotcraft/workbench/'
        if str(rel).startswith(wb):
            inside = str(rel)[len(wb):]
            if inside in ('proj', 'demosrc') or inside.startswith('public/') or inside in LOCAL_FILES or inside.startswith('.dev') or inside.startswith('.product-video'):
                continue
        if file.is_symlink():
            target = file.readlink()
            if target.is_absolute() or not file.resolve().is_relative_to(root):
                raise ValueError(f'External symlink cannot be distributed: {rel}')
            entries.append((file, rel, str(target).encode(), True))
        elif file.is_file():
            entries.append((file, rel, None, False))
    required = {'SKILL.md', 'scripts/engine/product_video/shotcraft.py', 'scripts/engine/product_video/credentials.py', 'scripts/engine/product_video/presentation.py', 'scripts/engine/product_video/editorial.py', 'scripts/engine/product_video/review.py', 'vendor/video-shotcraft/motion-catalog.json', 'vendor/video-shotcraft/workbench/package-lock.json', 'vendor/video-shotcraft/LICENSE'}
    if not required.issubset({str(rel) for _, rel, _, _ in entries}):
        raise ValueError('The skill source is incomplete.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file, rel, content, link in entries:
            info = zipfile.ZipInfo('product-video/' + str(rel), (2026, 9, 11, 0, 0, 0))
            info.create_system = 3
            mode = (stat.S_IFLNK | 0o777) if link else (stat.S_IFREG | (0o755 if file.stat().st_mode & 0o111 else 0o644))
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content if link else file.read_bytes())
    print(json.dumps({'archive': str(destination), 'files': len(entries), 'bytes': destination.stat().st_size}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    package(Path(__file__).resolve().parents[1], args.destination)
