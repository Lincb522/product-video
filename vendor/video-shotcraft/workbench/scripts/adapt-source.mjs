import ts from 'typescript';
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const wb = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const bridge = path.join(wb, 'src/product-video/adaptation');
const marker = '// Product Video adaptation: scoped copy, media and theme; upstream motion preserved.\n';
let modified = 0;
function walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) { walk(file); continue; }
    if (!entry.name.endsWith('.tsx')) continue;
    const source = readFileSync(file, 'utf8');
    if (source.startsWith(marker)) continue;
    let changed = false, videoConfig = false;
    const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const result = ts.transform(sf, [context => {
      const f = context.factory;
      const visit = node => {
        node = ts.visitEachChild(node, visit, context);
        if (ts.isImportDeclaration(node) && node.moduleSpecifier.text === 'remotion') {
          const bindings = node.importClause?.namedBindings;
          if (bindings && ts.isNamedImports(bindings)) {
            const specifiers = bindings.elements.filter(e => {
              if ((e.propertyName ?? e.name).text === 'useVideoConfig') { videoConfig = true; return false; }
              return true;
            });
            if (specifiers.length !== bindings.elements.length) {
              return f.updateImportDeclaration(node, node.modifiers,
                f.updateImportClause(node.importClause, false, node.importClause.name, f.updateNamedImports(bindings, specifiers)), node.moduleSpecifier, node.attributes);
            }
          }
        }
        const eligible = tag => ts.isIdentifier(tag) && (/^[a-z]/.test(tag.text) || ['Img', 'Video', 'OffthreadVideo', 'AbsoluteFill'].includes(tag.text));
        if (ts.isJsxSelfClosingElement(node) && eligible(node.tagName)) {
          changed = true;
          const attr = f.createJsxAttribute(f.createIdentifier('as'), f.createJsxExpression(undefined, /^[a-z]/.test(node.tagName.text) ? f.createStringLiteral(node.tagName.text) : node.tagName));
          return f.updateJsxSelfClosingElement(node, f.createIdentifier('PvElement'), node.typeArguments, f.updateJsxAttributes(node.attributes, [attr, ...node.attributes.properties]));
        }
        if (ts.isJsxElement(node) && eligible(node.openingElement.tagName)) {
          changed = true;
          const tag = node.openingElement.tagName;
          const attr = f.createJsxAttribute(f.createIdentifier('as'), f.createJsxExpression(undefined, /^[a-z]/.test(tag.text) ? f.createStringLiteral(tag.text) : tag));
          const opening = f.updateJsxOpeningElement(node.openingElement, f.createIdentifier('PvElement'), node.openingElement.typeArguments, f.updateJsxAttributes(node.openingElement.attributes, [attr, ...node.openingElement.attributes.properties]));
          return f.updateJsxElement(node, opening, node.children, f.updateJsxClosingElement(node.closingElement, f.createIdentifier('PvElement')));
        }
        return node;
      };
      return node => ts.visitNode(node, visit);
    }]);
    if (changed || videoConfig) {
      let relative = path.relative(path.dirname(file), bridge).replaceAll(path.sep, '/');
      if (!relative.startsWith('.')) relative = './' + relative;
      const bindings = [changed ? 'PvElement' : '', videoConfig ? 'useShotcraftVideoConfig as useVideoConfig' : ''].filter(Boolean).join(', ');
      writeFileSync(file, marker + `import { ${bindings} } from ${JSON.stringify('@pv/adaptation')};\n` + ts.createPrinter().printFile(result.transformed[0]));
      modified++;
    }
    result.dispose();
  }
}
walk(path.join(wb, '../demos'));
walk(path.join(wb, '../assets/lib'));
console.log(`Adapted ${modified} upstream modules.`);
