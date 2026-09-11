import ts from 'typescript';
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
const root = path.resolve(import.meta.dirname, '../..');
const modified = [];
function walk(folder) {
  for (const e of readdirSync(folder, { withFileTypes: true })) {
    const file = path.join(folder, e.name);
    if (e.isDirectory()) { walk(file); continue; }
    if (!file.endsWith('.tsx')) continue;
    const source = readFileSync(file, 'utf8');
    if (source.includes('Product Video: segmented text')) continue;
    const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    let changed = false;
    const result = ts.transform(tree, [context => {
      const f = context.factory;
      const visit = node => {
        if (ts.isArrowFunction(node) || ts.isFunctionExpression(node) || ts.isFunctionDeclaration(node)) {
          if (!node.body) return node;
          let jsx = false, split = false;
          const inspect = child => {
            if (ts.isJsxElement(child) || ts.isJsxSelfClosingElement(child)) jsx = true;
            if (ts.isCallExpression(child) && ts.isPropertyAccessExpression(child.expression) && child.expression.name.text === 'split') split = true;
            ts.forEachChild(child, inspect);
          };
          inspect(node.body);
          if (jsx && split) {
            const replace = child => {
              child = ts.visitEachChild(child, replace, context);
              if (ts.isCallExpression(child) && ts.isPropertyAccessExpression(child.expression) && child.expression.name.text === 'split') {
                return f.updateCallExpression(child, f.updatePropertyAccessExpression(child.expression, f.createCallExpression(f.createIdentifier('pvCopy'), undefined, [child.expression.expression]), child.expression.name), child.typeArguments, child.arguments);
              }
              return child;
            };
            let body = ts.visitNode(node.body, replace);
            const declaration = f.createVariableStatement(undefined, f.createVariableDeclarationList([
              f.createVariableDeclaration('pvCopy', undefined, undefined, f.createCallExpression(f.createIdentifier('useMotionCopy'), undefined, []))
            ], ts.NodeFlags.Const));
            body = ts.isBlock(body) ? f.updateBlock(body, [declaration, ...body.statements]) : f.createBlock([declaration, f.createReturnStatement(body)], true);
            changed = true;
            if (ts.isArrowFunction(node)) return f.updateArrowFunction(node, node.modifiers, node.typeParameters, node.parameters, node.type, node.equalsGreaterThanToken, body);
            if (ts.isFunctionExpression(node)) return f.updateFunctionExpression(node, node.modifiers, node.asteriskToken, node.name, node.typeParameters, node.parameters, node.type, body);
            return f.updateFunctionDeclaration(node, node.modifiers, node.asteriskToken, node.name, node.typeParameters, node.parameters, node.type, body);
          }
        }
        return ts.visitEachChild(node, visit, context);
      };
      return node => ts.visitNode(node, visit);
    }]);
    if (changed) { writeFileSync(file, '// Product Video: segmented text adapts before glyph animation.\nimport { useMotionCopy } from "@pv/adaptation";\n'+ts.createPrinter().printFile(result.transformed[0])); modified.push(path.relative(root, file)); }
    result.dispose();
  }
}
walk(path.join(root, 'demos')); walk(path.join(root, 'assets/lib'));
console.log(JSON.stringify(modified, null, 2));
