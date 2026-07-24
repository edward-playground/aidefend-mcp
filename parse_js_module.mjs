// File: parse_js_module.mjs
// Purpose: Securely parse JavaScript ES modules using AST (NO CODE EXECUTION)
// Usage: node parse_js_module.mjs <path-to-js-file>
//
// SECURITY: Uses static AST parsing instead of dynamic import() to prevent RCE

import { readFile } from 'fs/promises';
// Vendored so the Python wheel/sdist works from any current working
// directory without a post-install npm operation. See vendor/ACORN-LICENSE.
import * as acorn from './vendor/acorn.mjs';
import path from 'path';

/**
 * Securely parse a JavaScript ES module and output its exported object as JSON
 * Uses AST parsing - NEVER executes the code
 */
async function parseJsModule(filePath) {
  try {
    // Convert to absolute path
    const absolutePath = path.resolve(filePath);

    // Read file content (NO EXECUTION)
    const fileContent = await readFile(absolutePath, 'utf-8');

    // Parse using acorn (STATIC ANALYSIS ONLY - no code execution)
    const ast = acorn.parse(fileContent, {
      ecmaVersion: 2022,
      sourceType: 'module',
      locations: false
    });

    // Traverse AST to find export declarations
    for (const node of ast.body) {
      let exported = null;

      // Handle: export const foo = { ... }
      if (node.type === 'ExportNamedDeclaration' && node.declaration) {
        const decl = node.declaration;

        if (decl.type === 'VariableDeclaration') {
          for (const declarator of decl.declarations) {
            if (declarator.init && declarator.init.type === 'ObjectExpression') {
              exported = extractObjectLiteral(declarator.init);
              break;
            }
          }
        }
      }

      // Handle: export default { ... }
      else if (node.type === 'ExportDefaultDeclaration') {
        if (node.declaration.type === 'ObjectExpression') {
          exported = extractObjectLiteral(node.declaration);
        }
      }

      // If found, output and exit
      if (exported !== null && typeof exported === 'object' && !Array.isArray(exported)) {
        process.stdout.write(JSON.stringify(exported));
        return;
      }
    }

    // No suitable export found
    throw new Error('No object export found in module');

  } catch (error) {
    // Write error to stderr
    process.stderr.write(`Node.js Parser Error: ${error.message}\n`);
    if (error.stack) {
      process.stderr.write(error.stack + '\n');
    }
    process.exit(1);
  }
}

/**
 * Extract plain JavaScript object from AST ObjectExpression node
 * Recursively handles nested objects and arrays
 */
function extractObjectLiteral(node) {
  if (!node) return null;

  switch (node.type) {
    case 'ObjectExpression':
      const obj = {};
      for (const prop of node.properties) {
        if (prop.type === 'Property') {
          // Get property key
          let key;
          if (prop.key.type === 'Identifier') {
            key = prop.key.name;
          } else if (prop.key.type === 'Literal') {
            key = prop.key.value;
          } else {
            continue; // Skip computed keys
          }

          // Get property value
          obj[key] = extractValue(prop.value);
        } else if (prop.type === 'SpreadElement') {
          // Handle spread properties - skip for safety
          continue;
        }
      }
      return obj;

    case 'ArrayExpression':
      return node.elements.map(el => extractValue(el));

    case 'Literal':
      return node.value;

    case 'TemplateLiteral':
      // Extract template literal as concatenated string
      return extractTemplateLiteral(node);

    case 'Identifier':
      // Identifiers without resolution - return string representation
      return `<Identifier:${node.name}>`;

    case 'UnaryExpression':
      // Handle simple unary expressions (e.g., -1, !true)
      if (node.operator === '-' && node.argument.type === 'Literal') {
        return -node.argument.value;
      }
      if (node.operator === '+' && node.argument.type === 'Literal') {
        return +node.argument.value;
      }
      if (node.operator === '!' && node.argument.type === 'Literal') {
        return !node.argument.value;
      }
      return null;

    case 'BinaryExpression':
      // Handle simple binary expressions (e.g., "a" + "b")
      const left = extractValue(node.left);
      const right = extractValue(node.right);
      if (node.operator === '+' && typeof left === 'string' && typeof right === 'string') {
        return left + right;
      }
      return null;

    default:
      // For unsupported types (functions, classes, etc.), return null
      return null;
  }
}

/**
 * Extract value from any AST node type
 */
function extractValue(node) {
  if (!node) return null;

  switch (node.type) {
    case 'ObjectExpression':
      return extractObjectLiteral(node);

    case 'ArrayExpression':
      return node.elements.map(el => extractValue(el));

    case 'Literal':
      return node.value;

    case 'TemplateLiteral':
      return extractTemplateLiteral(node);

    case 'TaggedTemplateExpression':
      return extractSafeTaggedTemplate(node);

    case 'CallExpression':
      return extractSafeCallExpression(node);

    case 'Identifier':
      // Return identifier name as marker (can't resolve without execution)
      return `<Identifier:${node.name}>`;

    case 'UnaryExpression':
      if (node.operator === '-' && node.argument.type === 'Literal') {
        return -node.argument.value;
      }
      if (node.operator === '+' && node.argument.type === 'Literal') {
        return +node.argument.value;
      }
      if (node.operator === '!' && node.argument.type === 'Literal') {
        return !node.argument.value;
      }
      return null;

    case 'BinaryExpression':
      const left = extractValue(node.left);
      const right = extractValue(node.right);
      if (node.operator === '+') {
        if (typeof left === 'string' || typeof right === 'string') {
          return String(left) + String(right);
        }
        if (typeof left === 'number' && typeof right === 'number') {
          return left + right;
        }
      }
      return null;

    default:
      return null;
  }
}

/**
 * Resolve the one deterministic call shape authored by the framework for
 * large strings: ["literal", "literal"].join("").  No identifiers, computed
 * members, spreads, callbacks, or other calls are evaluated.
 */
function extractSafeCallExpression(node) {
  const callee = node.callee;
  if (
    callee?.type !== 'MemberExpression' ||
    callee.computed ||
    callee.property?.type !== 'Identifier' ||
    callee.property.name !== 'join' ||
    callee.object?.type !== 'ArrayExpression' ||
    node.arguments.length !== 1 ||
    node.arguments[0]?.type !== 'Literal' ||
    node.arguments[0].value !== ''
  ) {
    return null;
  }

  const parts = [];
  for (const element of callee.object.elements) {
    if (!element || element.type !== 'Literal' || typeof element.value !== 'string') {
      return null;
    }
    parts.push(element.value);
  }
  return parts.join(node.arguments[0].value);
}

/**
 * Resolve String.raw`...` only when it has no substitutions.  This preserves
 * backslashes exactly while refusing every user-defined tag or expression.
 */
function extractSafeTaggedTemplate(node) {
  const tag = node.tag;
  if (
    tag?.type !== 'MemberExpression' ||
    tag.computed ||
    tag.object?.type !== 'Identifier' ||
    tag.object.name !== 'String' ||
    tag.property?.type !== 'Identifier' ||
    tag.property.name !== 'raw' ||
    node.quasi?.type !== 'TemplateLiteral' ||
    node.quasi.expressions.length !== 0
  ) {
    return null;
  }
  return node.quasi.quasis.map(part => part.value.raw).join('');
}

/**
 * Extract template literal as string
 * Example: `Hello ${name}` -> "Hello <Identifier:name>"
 */
function extractTemplateLiteral(node) {
  let result = '';

  // Interleave quasis (string parts) and expressions
  for (let i = 0; i < node.quasis.length; i++) {
    result += node.quasis[i].value.cooked || node.quasis[i].value.raw;

    if (i < node.expressions.length) {
      const expr = node.expressions[i];
      if (expr.type === 'Literal') {
        result += String(expr.value);
      } else if (expr.type === 'Identifier') {
        result += `<Identifier:${expr.name}>`;
      } else {
        result += '<Expression>';
      }
    }
  }

  return result;
}

// Get file path from command line arguments
const filePath = process.argv[2];

if (!filePath) {
  process.stderr.write('Usage: node parse_js_module.mjs <file-path>\n');
  process.exit(1);
}

parseJsModule(filePath);
