// File: parse_js_module.mjs
// Purpose: Securely parse JavaScript ES modules using AST (NO CODE EXECUTION)
// Usage: node parse_js_module.mjs <path-to-js-file>
//
// SECURITY: Uses static AST parsing instead of dynamic import() to prevent RCE.

import { readFile } from 'fs/promises';
// Vendored so the Python wheel/sdist works from any current working
// directory without a post-install npm operation. See vendor/ACORN-LICENSE.
import * as acorn from './vendor/acorn.mjs';
import path from 'path';

const STATIC_LIMITS = Object.freeze({
  maxTokens: 150_000,
  maxSyntaxNestingDepth: 256,
  maxAstNodes: 100_000,
  maxAstDepth: 2_048,
  maxEvaluationDepth: 2_048,
  maxCallChainDepth: 16,
  maxOperations: 50_000,
  maxCharacterWork: 134_217_728,
  maxArrayElements: 4_096,
  maxStringLength: 1_048_576,
  maxOutputLength: 16_777_216,
});

function fail(location, message) {
  throw new Error(`Static evaluation rejected ${location}: ${message}`);
}

function jsonStringLength(value, remaining, location) {
  let length = 2; // Opening and closing quotes.
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    let increment = 1;
    if (code === 0x22 || code === 0x5c || code === 0x08 || code === 0x09 ||
        code === 0x0a || code === 0x0c || code === 0x0d) {
      increment = 2;
    } else if (code <= 0x1f) {
      increment = 6;
    } else if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        increment = 2;
        index += 1;
      } else {
        increment = 6;
      }
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      increment = 6;
    }
    length += increment;
    if (length > remaining) {
      fail(location, `serialized output exceeds ${STATIC_LIMITS.maxOutputLength} characters`);
    }
  }
  return length;
}

function assertSerializedOutputWithinLimit(value) {
  let total = 0;
  const pending = [['$export', value]];
  const add = (amount, location) => {
    total += amount;
    if (total > STATIC_LIMITS.maxOutputLength) {
      fail(location, `serialized output exceeds ${STATIC_LIMITS.maxOutputLength} characters`);
    }
  };

  while (pending.length > 0) {
    const [location, item] = pending.pop();
    if (item === null) {
      add(4, location);
    } else if (typeof item === 'string') {
      // Raw string length is a lower bound. Check it before scanning escapes so
      // repeated references cannot force unbounded preflight work.
      if (total + item.length + 2 > STATIC_LIMITS.maxOutputLength) {
        fail(location, `serialized output exceeds ${STATIC_LIMITS.maxOutputLength} characters`);
      }
      add(
        jsonStringLength(item, STATIC_LIMITS.maxOutputLength - total, location),
        location
      );
    } else if (typeof item === 'number') {
      add(JSON.stringify(item).length, location);
    } else if (typeof item === 'boolean') {
      add(item ? 4 : 5, location);
    } else if (Array.isArray(item)) {
      add(2 + Math.max(0, item.length - 1), location);
      for (let index = 0; index < item.length; index += 1) {
        pending.push([`${location}[${index}]`, item[index]]);
      }
    } else if (item && typeof item === 'object') {
      const keys = Object.keys(item);
      add(2 + Math.max(0, keys.length - 1), location);
      for (const key of keys) {
        add(
          jsonStringLength(
            key,
            STATIC_LIMITS.maxOutputLength - total,
            `${location}.${key}`
          ) + 1,
          `${location}.${key}`
        );
        pending.push([`${location}.${key}`, item[key]]);
      }
    } else {
      fail(location, 'internal evaluator produced a non-JSON value');
    }
  }
}

function assertAstWithinLimits(ast) {
  let nodeCount = 0;
  const pending = [[ast, 1]];

  while (pending.length > 0) {
    const [value, depth] = pending.pop();
    if (!value || typeof value !== 'object') continue;

    if (typeof value.type === 'string') {
      nodeCount += 1;
      if (nodeCount > STATIC_LIMITS.maxAstNodes) {
        throw new Error(
          `JavaScript AST exceeds ${STATIC_LIMITS.maxAstNodes} nodes`
        );
      }
      if (depth > STATIC_LIMITS.maxAstDepth) {
        throw new Error(
          `JavaScript AST exceeds depth ${STATIC_LIMITS.maxAstDepth}`
        );
      }
    }

    for (const [key, child] of Object.entries(value)) {
      if (key === 'start' || key === 'end' || key === 'loc') continue;
      if (Array.isArray(child)) {
        for (const item of child) {
          if (item && typeof item === 'object') {
            pending.push([item, depth + 1]);
          }
        }
      } else if (child && typeof child === 'object') {
        pending.push([child, depth + 1]);
      }
    }
  }
}

function propertyKey(property, location) {
  if (
    property.type !== 'Property' ||
    property.kind !== 'init' ||
    property.method ||
    property.computed ||
    property.shorthand
  ) {
    fail(location, 'spread, computed, shorthand, getter, setter, or method properties are unsupported');
  }

  let key;
  if (property.key?.type === 'Identifier') {
    key = property.key.name;
  } else if (
    property.key?.type === 'Literal' &&
    (typeof property.key.value === 'string' ||
      typeof property.key.value === 'number')
  ) {
    key = String(property.key.value);
  } else {
    fail(location, 'object property key must be a static identifier or literal');
  }
  // In a JavaScript object literal this spelling invokes the special prototype
  // setter instead of defining an ordinary own property. Refuse the ambiguous
  // form rather than materializing JSON with different semantics.
  if (key === '__proto__') {
    fail(location, "object literal key '__proto__' is unsupported");
  }
  return key;
}

function assertLiteralValue(node, location) {
  const value = node.value;
  if (
    node.regex ||
    typeof value === 'bigint' ||
    !(
      value === null ||
      typeof value === 'string' ||
      typeof value === 'boolean' ||
      (typeof value === 'number' && Number.isFinite(value))
    )
  ) {
    fail(location, 'literal must be a finite JSON scalar');
  }
}

function assertLiteralString(node, location) {
  if (node?.type !== 'Literal' || typeof node.value !== 'string' || node.regex) {
    fail(location, 'argument must be a literal string');
  }
}

function memberMethod(node, location) {
  if (
    node?.type !== 'MemberExpression' ||
    node.computed ||
    node.optional ||
    node.property?.type !== 'Identifier'
  ) {
    fail(location, 'method must be an uncomputed, non-optional member');
  }
  return node.property.name;
}

function assertMapCallback(callback, location) {
  if (
    callback?.type !== 'ArrowFunctionExpression' ||
    callback.async ||
    callback.generator ||
    callback.expression === false ||
    callback.body?.type === 'BlockStatement' ||
    callback.params.length < 1 ||
    callback.params.length > 2 ||
    callback.params.some((parameter) => parameter.type !== 'Identifier')
  ) {
    fail(
      location,
      'map callback must be a synchronous one- or two-parameter arrow expression'
    );
  }
  const names = callback.params.map((parameter) => parameter.name);
  if (new Set(names).size !== names.length) {
    fail(location, 'map callback parameter names must be unique');
  }
  if (names.includes('String')) {
    fail(location, "map callback parameter name 'String' is unsupported");
  }
  return names;
}

function assertStaticConditionAst(node, location, bindings, depth, callDepth) {
  if (
    node?.type !== 'BinaryExpression' ||
    !['===', '!=='].includes(node.operator)
  ) {
    fail(location, 'condition must use strict literal equality or inequality');
  }
  assertStaticValueAst(
    node.left,
    `${location}.left`,
    bindings,
    depth + 1,
    callDepth
  );
  assertStaticValueAst(
    node.right,
    `${location}.right`,
    bindings,
    depth + 1,
    callDepth
  );
}

function assertStaticCallAst(node, location, bindings, depth, callDepth) {
  if (node.optional) {
    fail(location, 'optional calls are unsupported');
  }
  const nextCallDepth = callDepth + 1;
  if (nextCallDepth > STATIC_LIMITS.maxCallChainDepth) {
    fail(
      location,
      `call chain exceeds ${STATIC_LIMITS.maxCallChainDepth} operations`
    );
  }

  const method = memberMethod(node.callee, `${location}.callee`);
  if (method === 'join') {
    if (node.arguments.length !== 1) {
      fail(location, 'join requires exactly one literal string separator');
    }
    assertLiteralString(node.arguments[0], `${location}.separator`);
    assertStaticValueAst(
      node.callee.object,
      `${location}.source`,
      bindings,
      depth + 1,
      nextCallDepth
    );
    return;
  }

  if (method === 'replace') {
    if (node.arguments.length !== 2) {
      fail(location, 'replace requires literal search and replacement strings');
    }
    assertLiteralString(node.arguments[0], `${location}.search`);
    assertLiteralString(node.arguments[1], `${location}.replacement`);
    if (/\$(?:\$|&|`|')/.test(node.arguments[1].value)) {
      fail(
        `${location}.replacement`,
        'replace substitution tokens are unsupported'
      );
    }
    assertStaticValueAst(
      node.callee.object,
      `${location}.source`,
      bindings,
      depth + 1,
      nextCallDepth
    );
    return;
  }

  if (method === 'map') {
    if (node.arguments.length !== 1) {
      fail(location, 'map requires exactly one arrow-expression callback');
    }
    const callback = node.arguments[0];
    const parameterNames = assertMapCallback(callback, `${location}.callback`);
    assertStaticValueAst(
      node.callee.object,
      `${location}.source`,
      bindings,
      depth + 1,
      nextCallDepth
    );
    // Deliberately do not inherit outer bindings: callbacks cannot close over
    // free variables. Only the section and optional index parameters exist.
    assertStaticValueAst(
      callback.body,
      `${location}.callback.body`,
      new Set(parameterNames),
      depth + 1,
      nextCallDepth
    );
    return;
  }

  fail(location, `unsupported method call '${method}'`);
}

function assertStaticValueAst(
  node,
  location = '$export',
  bindings = new Set(),
  depth = 0,
  callDepth = 0
) {
  if (!node) {
    fail(location, 'missing AST value or array hole');
  }
  if (depth > STATIC_LIMITS.maxEvaluationDepth) {
    fail(
      location,
      `evaluation depth exceeds ${STATIC_LIMITS.maxEvaluationDepth}`
    );
  }

  switch (node.type) {
    case 'ObjectExpression':
      for (let index = 0; index < node.properties.length; index += 1) {
        const property = node.properties[index];
        const key = propertyKey(property, `${location}.properties[${index}]`);
        assertStaticValueAst(
          property.value,
          `${location}.${key}`,
          bindings,
          depth + 1,
          callDepth
        );
      }
      return;

    case 'ArrayExpression':
      if (node.elements.length > STATIC_LIMITS.maxArrayElements) {
        fail(
          location,
          `array exceeds ${STATIC_LIMITS.maxArrayElements} elements`
        );
      }
      for (let index = 0; index < node.elements.length; index += 1) {
        assertStaticValueAst(
          node.elements[index],
          `${location}[${index}]`,
          bindings,
          depth + 1,
          callDepth
        );
      }
      return;

    case 'Literal':
      assertLiteralValue(node, location);
      return;

    case 'TemplateLiteral':
      if (node.expressions.length !== 0) {
        fail(location, 'template interpolation is unsupported');
      }
      return;

    case 'TaggedTemplateExpression': {
      const tag = node.tag;
      const isStringRaw =
        tag?.type === 'MemberExpression' &&
        !tag.computed &&
        !tag.optional &&
        tag.object?.type === 'Identifier' &&
        tag.object.name === 'String' &&
        tag.property?.type === 'Identifier' &&
        tag.property.name === 'raw';
      if (
        !isStringRaw ||
        bindings.has('String') ||
        node.quasi?.expressions.length !== 0
      ) {
        fail(location, 'only substitution-free String.raw templates are supported');
      }
      return;
    }

    case 'Identifier':
      if (!bindings.has(node.name)) {
        fail(location, `free identifier '${node.name}' is unsupported`);
      }
      return;

    case 'UnaryExpression':
      if (
        !['-', '+', '!'].includes(node.operator) ||
        node.prefix !== true ||
        node.argument?.type !== 'Literal'
      ) {
        fail(location, 'unsupported unary expression');
      }
      assertLiteralValue(node.argument, `${location}.argument`);
      return;

    case 'BinaryExpression':
      if (node.operator !== '+') {
        fail(location, `unsupported binary operator '${node.operator}'`);
      }
      assertStaticValueAst(
        node.left,
        `${location}.left`,
        bindings,
        depth + 1,
        callDepth
      );
      assertStaticValueAst(
        node.right,
        `${location}.right`,
        bindings,
        depth + 1,
        callDepth
      );
      return;

    case 'ConditionalExpression':
      if (bindings.size === 0) {
        fail(location, 'conditional expressions are only supported in map callbacks');
      }
      assertStaticConditionAst(
        node.test,
        `${location}.test`,
        bindings,
        depth + 1,
        callDepth
      );
      assertStaticValueAst(
        node.consequent,
        `${location}.consequent`,
        bindings,
        depth + 1,
        callDepth
      );
      assertStaticValueAst(
        node.alternate,
        `${location}.alternate`,
        bindings,
        depth + 1,
        callDepth
      );
      return;

    case 'CallExpression':
      assertStaticCallAst(node, location, bindings, depth, callDepth);
      return;

    default:
      fail(location, `unsupported AST node '${node.type}'`);
  }
}

class StaticEvaluator {
  constructor() {
    this.operations = 0;
    this.characterWork = 0;
  }

  consume(location, amount = 1) {
    this.operations += amount;
    if (this.operations > STATIC_LIMITS.maxOperations) {
      fail(
        location,
        `operation count exceeds ${STATIC_LIMITS.maxOperations}`
      );
    }
  }

  boundedString(value, location) {
    if (value.length > STATIC_LIMITS.maxStringLength) {
      fail(
        location,
        `string result exceeds ${STATIC_LIMITS.maxStringLength} characters`
      );
    }
    return value;
  }

  consumeCharacters(location, amount) {
    this.characterWork += amount;
    if (this.characterWork > STATIC_LIMITS.maxCharacterWork) {
      fail(
        location,
        `character work exceeds ${STATIC_LIMITS.maxCharacterWork}`
      );
    }
  }

  joinedString(parts, separator, location) {
    let resultLength = 0;
    for (let index = 0; index < parts.length; index += 1) {
      resultLength += parts[index].length;
      if (index > 0) resultLength += separator.length;
      if (resultLength > STATIC_LIMITS.maxStringLength) {
        fail(
          location,
          `string result exceeds ${STATIC_LIMITS.maxStringLength} characters`
        );
      }
    }
    this.consumeCharacters(location, resultLength);
    return parts.join(separator);
  }

  replacedString(source, search, replacement, location) {
    const matchIndex = source.indexOf(search);
    if (matchIndex < 0) {
      this.consumeCharacters(location, source.length);
      return source;
    }
    const suffixLength = source.length - matchIndex - search.length;
    const resultLength = matchIndex + replacement.length + suffixLength;
    if (resultLength > STATIC_LIMITS.maxStringLength) {
      fail(
        location,
        `string result exceeds ${STATIC_LIMITS.maxStringLength} characters`
      );
    }
    this.consumeCharacters(location, source.length + resultLength);
    return source.replace(search, replacement);
  }

  evaluateCondition(node, location, bindings, depth, callDepth) {
    const left = this.evaluate(
      node.left,
      bindings,
      depth + 1,
      callDepth,
      `${location}.left`
    );
    const right = this.evaluate(
      node.right,
      bindings,
      depth + 1,
      callDepth,
      `${location}.right`
    );
    const isScalar = (value) =>
      value === null ||
      typeof value === 'string' ||
      typeof value === 'number' ||
      typeof value === 'boolean';
    if (!isScalar(left) || !isScalar(right)) {
      fail(location, 'condition operands must be static scalar values');
    }
    return node.operator === '===' ? left === right : left !== right;
  }

  evaluateCall(node, location, bindings, depth, callDepth) {
    const nextCallDepth = callDepth + 1;
    if (nextCallDepth > STATIC_LIMITS.maxCallChainDepth) {
      fail(
        location,
        `call chain exceeds ${STATIC_LIMITS.maxCallChainDepth} operations`
      );
    }
    const method = memberMethod(node.callee, `${location}.callee`);

    if (method === 'join') {
      const source = this.evaluate(
        node.callee.object,
        bindings,
        depth + 1,
        nextCallDepth,
        `${location}.source`
      );
      if (!Array.isArray(source) || source.some((part) => typeof part !== 'string')) {
        fail(location, 'join source must be a static array of strings');
      }
      this.consume(location, source.length);
      return this.joinedString(source, node.arguments[0].value, location);
    }

    if (method === 'replace') {
      const source = this.evaluate(
        node.callee.object,
        bindings,
        depth + 1,
        nextCallDepth,
        `${location}.source`
      );
      if (typeof source !== 'string') {
        fail(location, 'replace source must be a static string');
      }
      this.consume(location);
      return this.replacedString(
        source,
        node.arguments[0].value,
        node.arguments[1].value,
        location
      );
    }

    if (method === 'map') {
      const source = this.evaluate(
        node.callee.object,
        bindings,
        depth + 1,
        nextCallDepth,
        `${location}.source`
      );
      if (!Array.isArray(source) || source.some((part) => typeof part !== 'string')) {
        fail(location, 'map source must be a static array of strings');
      }
      const callback = node.arguments[0];
      const parameterNames = callback.params.map((parameter) => parameter.name);
      const mapped = [];
      let aggregateLength = 0;
      for (let index = 0; index < source.length; index += 1) {
        this.consume(`${location}[${index}]`);
        const callbackBindings = new Map([[parameterNames[0], source[index]]]);
        if (parameterNames[1]) {
          callbackBindings.set(parameterNames[1], index);
        }
        const value = this.evaluate(
          callback.body,
          callbackBindings,
          depth + 1,
          nextCallDepth,
          `${location}.callback[${index}]`
        );
        if (typeof value !== 'string') {
          fail(`${location}.callback[${index}]`, 'map callback must return a string');
        }
        aggregateLength += value.length;
        if (aggregateLength > STATIC_LIMITS.maxOutputLength) {
          fail(
            location,
            `map result exceeds ${STATIC_LIMITS.maxOutputLength} aggregate characters`
          );
        }
        mapped.push(value);
      }
      return mapped;
    }

    fail(location, `unsupported method call '${method}'`);
  }

  evaluate(
    node,
    bindings = new Map(),
    depth = 0,
    callDepth = 0,
    location = '$export'
  ) {
    this.consume(location);
    if (depth > STATIC_LIMITS.maxEvaluationDepth) {
      fail(
        location,
        `evaluation depth exceeds ${STATIC_LIMITS.maxEvaluationDepth}`
      );
    }

    switch (node.type) {
      case 'ObjectExpression': {
        const result = Object.create(null);
        const keys = new Set();
        for (let index = 0; index < node.properties.length; index += 1) {
          this.consume(`${location}.properties[${index}]`);
          const property = node.properties[index];
          const key = propertyKey(property, `${location}.properties[${index}]`);
          if (keys.has(key)) {
            fail(`${location}.${key}`, 'duplicate object property');
          }
          keys.add(key);
          result[key] = this.evaluate(
            property.value,
            bindings,
            depth + 1,
            callDepth,
            `${location}.${key}`
          );
        }
        return result;
      }

      case 'ArrayExpression': {
        const result = [];
        for (let index = 0; index < node.elements.length; index += 1) {
          this.consume(`${location}[${index}]`);
          result.push(
            this.evaluate(
              node.elements[index],
              bindings,
              depth + 1,
              callDepth,
              `${location}[${index}]`
            )
          );
        }
        return result;
      }

      case 'Literal': {
        const value = node.value;
        return typeof value === 'string'
          ? this.boundedString(value, location)
          : value;
      }

      case 'TemplateLiteral':
        return this.joinedString(
          node.quasis.map((part) => part.value.cooked ?? part.value.raw),
          '',
          location
        );

      case 'TaggedTemplateExpression':
        if (bindings.has('String')) {
          fail(location, "String.raw is shadowed by a callback binding");
        }
        return this.joinedString(
          node.quasi.quasis.map((part) => part.value.raw),
          '',
          location
        );

      case 'Identifier':
        if (!bindings.has(node.name)) {
          fail(location, `free identifier '${node.name}' is unsupported`);
        }
        return bindings.get(node.name);

      case 'UnaryExpression': {
        const value = node.argument.value;
        if (node.operator === '-') {
          if (typeof value !== 'number') fail(location, 'unary - requires a number');
          const result = -value;
          if (!Number.isFinite(result)) fail(location, 'unary result is not finite');
          return result;
        }
        if (node.operator === '+') {
          if (typeof value !== 'number') fail(location, 'unary + requires a number');
          const result = +value;
          if (!Number.isFinite(result)) fail(location, 'unary result is not finite');
          return result;
        }
        return !value;
      }

      case 'BinaryExpression': {
        const left = this.evaluate(
          node.left,
          bindings,
          depth + 1,
          callDepth,
          `${location}.left`
        );
        const right = this.evaluate(
          node.right,
          bindings,
          depth + 1,
          callDepth,
          `${location}.right`
        );
        if (typeof left === 'string' && typeof right === 'string') {
          const resultLength = left.length + right.length;
          if (resultLength > STATIC_LIMITS.maxStringLength) {
            fail(
              location,
              `string result exceeds ${STATIC_LIMITS.maxStringLength} characters`
            );
          }
          this.consumeCharacters(location, resultLength);
          return left + right;
        }
        if (typeof left === 'number' && typeof right === 'number') {
          const result = left + right;
          if (!Number.isFinite(result)) fail(location, 'binary result is not finite');
          return result;
        }
        fail(location, 'binary + operands must both be strings or both be numbers');
      }

      case 'ConditionalExpression': {
        const condition = this.evaluateCondition(
          node.test,
          `${location}.test`,
          bindings,
          depth + 1,
          callDepth
        );
        return this.evaluate(
          condition ? node.consequent : node.alternate,
          bindings,
          depth + 1,
          callDepth,
          condition ? `${location}.consequent` : `${location}.alternate`
        );
      }

      case 'CallExpression':
        return this.evaluateCall(node, location, bindings, depth, callDepth);

      default:
        fail(location, `unsupported AST node '${node.type}'`);
    }
  }
}

function exportedObjectNode(ast) {
  if (ast.body.length !== 1) {
    throw new Error('Module must contain exactly one object export');
  }
  const node = ast.body[0];

  if (
    node.type === 'ExportNamedDeclaration' &&
    node.declaration?.type === 'VariableDeclaration' &&
    node.declaration.kind === 'const' &&
    node.declaration.declarations.length === 1 &&
    node.declaration.declarations[0].id?.type === 'Identifier' &&
    node.declaration.declarations[0].init?.type === 'ObjectExpression'
  ) {
    const declaration = node.declaration.declarations[0];
    if (declaration.id.name === 'String') {
      throw new Error("Named export binding 'String' is unsupported");
    }
    return declaration.init;
  }

  if (
    node.type === 'ExportDefaultDeclaration' &&
    node.declaration?.type === 'ObjectExpression'
  ) {
    return node.declaration;
  }

  throw new Error('Module must export exactly one static object literal');
}

/**
 * Securely parse a JavaScript ES module and output its exported object as JSON.
 * The source is parsed and evaluated against a closed static grammar; it is
 * never imported or executed as JavaScript.
 */
async function parseJsModule(filePath) {
  try {
    const absolutePath = path.resolve(filePath);
    const fileContent = await readFile(absolutePath, 'utf-8');
    let tokenCount = 0;
    let syntaxDepth = 0;
    const openingTokens = new Set(['(', '[', '{', '${']);
    const closingTokens = new Set([')', ']', '}']);
    const ast = acorn.parse(fileContent, {
      ecmaVersion: 2022,
      sourceType: 'module',
      locations: false,
      onToken(token) {
        tokenCount += 1;
        if (tokenCount > STATIC_LIMITS.maxTokens) {
          throw new Error(
            `JavaScript token count exceeds ${STATIC_LIMITS.maxTokens}`
          );
        }
        const label = token.type.label;
        if (openingTokens.has(label)) {
          syntaxDepth += 1;
          if (syntaxDepth > STATIC_LIMITS.maxSyntaxNestingDepth) {
            throw new Error(
              `JavaScript syntax nesting exceeds ${STATIC_LIMITS.maxSyntaxNestingDepth}`
            );
          }
        } else if (closingTokens.has(label)) {
          syntaxDepth = Math.max(0, syntaxDepth - 1);
        }
      },
    });

    assertAstWithinLimits(ast);
    const objectNode = exportedObjectNode(ast);
    assertStaticValueAst(objectNode);
    const exported = new StaticEvaluator().evaluate(objectNode);
    assertSerializedOutputWithinLimit(exported);
    const output = JSON.stringify(exported);
    if (output.length > STATIC_LIMITS.maxOutputLength) {
      throw new Error(
        `Parser output exceeds ${STATIC_LIMITS.maxOutputLength} characters`
      );
    }
    process.stdout.write(output);
  } catch (error) {
    process.stderr.write(`Node.js Parser Error: ${error.message}\n`);
    if (error.stack) {
      process.stderr.write(error.stack + '\n');
    }
    process.exit(1);
  }
}

const filePath = process.argv[2];
if (!filePath) {
  process.stderr.write('Usage: node parse_js_module.mjs <path-to-js-file>\n');
  process.exit(1);
}

parseJsModule(filePath);
