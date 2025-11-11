// File: parse_js_module.mjs
// Purpose: Parse JavaScript ES modules and output as JSON
// Usage: node parse_js_module.mjs <path-to-js-file>

import { pathToFileURL } from 'url';
import path from 'path';

/**
 * Parse a JavaScript ES module and output its exported object as JSON
 */
async function parseJsModule(filePath) {
  try {
    // Convert to absolute path
    const absolutePath = path.resolve(filePath);

    // Convert to file:// URL (required for ES module imports)
    const fileUrl = pathToFileURL(absolutePath).href;

    // Dynamically import the module
    const module = await import(fileUrl);

    // Find the first exported object
    for (const key in module) {
      const exported = module[key];

      // Check if it's a plain object (not array, not null)
      if (typeof exported === 'object' && exported !== null && !Array.isArray(exported)) {
        // Output as standard JSON to stdout
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

// Get file path from command line arguments
const filePath = process.argv[2];

if (!filePath) {
  process.stderr.write('Usage: node parse_js_module.mjs <file-path>\n');
  process.exit(1);
}

parseJsModule(filePath);
