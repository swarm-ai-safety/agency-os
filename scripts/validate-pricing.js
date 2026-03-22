#!/usr/bin/env node

/**
 * Pricing consistency validator
 *
 * Checks that docs/pricing.md, site/app/components/Pricing.tsx, and
 * site/app/components/pricing-utils.ts all match the canonical
 * pricing.schema.json.
 *
 * Validates: plan names, prices, periods, features, limits, model names,
 * model prices, execution fees, and volume discounts.
 *
 * Usage: node scripts/validate-pricing.js
 *        node scripts/validate-pricing.js --self-test
 * Exit 0 if consistent, 1 if drift detected
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const SCHEMA_PATH = path.join(__dirname, '../pricing.schema.json');
const DOCS_PATH = path.join(__dirname, '../docs/pricing.md');
const COMPONENT_PATH = path.join(__dirname, '../site/app/components/Pricing.tsx');
const PRICING_UTILS_PATH = path.join(__dirname, '../site/app/components/pricing-utils.ts');

function loadSchema(schemaPath) {
  const raw = fs.readFileSync(schemaPath || SCHEMA_PATH, 'utf8');
  return JSON.parse(raw);
}

/**
 * Format a number as a price string for comparison (e.g. 0.26 -> "$0.26")
 */
function fmtPrice(n) {
  if (n === null || n === undefined) return null;
  return `$${Number(n).toFixed(2)}`;
}

/**
 * Split docs into per-plan sections keyed by plan header.
 * Returns { "Free Demo": "section text...", "Pro": "...", ... }
 */
function splitDocSections(docs) {
  const sections = {};
  const parts = docs.split(/^### /m);
  for (const part of parts) {
    if (!part.trim()) continue;
    const firstLine = part.split('\n')[0].trim();
    // Extract plan name from header like "Pro -- $49/month + usage"
    const nameMatch = firstLine.match(/^([^-]+?)(?:\s+--\s+|$)/);
    if (nameMatch) {
      const name = nameMatch[1].trim();
      sections[name] = part;
    }
  }
  return sections;
}

function checkDocs(schema) {
  const docs = fs.readFileSync(DOCS_PATH, 'utf8');
  const errors = [];
  const sections = splitDocSections(docs);

  // Check "Starter" is not used (legacy name)
  if (/### Starter/i.test(docs)) {
    errors.push('docs/pricing.md: Found deprecated "Starter" plan name (should be "Free")');
  }

  // ── Plan validation ──
  schema.plans.forEach(plan => {
    const nameRegex = new RegExp(`### ${escapeRegex(plan.displayName)}`, 'i');
    if (!nameRegex.test(docs)) {
      errors.push(`docs/pricing.md: Missing plan header "### ${plan.displayName}"`);
      return; // can't check further without the section
    }

    const section = sections[plan.displayName];
    if (!section) return;

    // Check price in header (skip free plans — price appears in description, not header)
    if (plan.priceDisplay !== 'Custom' && plan.price > 0) {
      const headerLine = section.split('\n')[0];
      if (!headerLine.includes(plan.priceDisplay)) {
        errors.push(`docs/pricing.md: Plan "${plan.displayName}" header should contain price "${plan.priceDisplay}", found: "${headerLine.trim()}"`);
      }
    }

    // Check period in header (e.g. "/mo + usage")
    if (plan.period && plan.period !== 'one-time') {
      const headerLine = section.split('\n')[0];
      // Normalize: schema says "/mo + usage", docs might say "/month + usage"
      const periodNorm = plan.period.replace('/mo ', '/month ').replace('/mo$', '/month');
      if (!headerLine.includes(plan.period) && !headerLine.includes(periodNorm)) {
        errors.push(`docs/pricing.md: Plan "${plan.displayName}" header should contain period "${plan.period}", found: "${headerLine.trim()}"`);
      }
    }

    // Check features
    plan.features.forEach(feature => {
      // Normalize for comparison: strip quotes, collapse spaces around /
      const normalize = (s) => s.replace(/[""\u201c\u201d]/g, '').replace(/\s*\/\s*/g, '/');
      if (!normalize(section).includes(normalize(feature))) {
        errors.push(`docs/pricing.md: Plan "${plan.displayName}" missing feature: "${feature}"`);
      }
    });

    // Check limits
    plan.limits.forEach(limit => {
      if (!section.includes(limit)) {
        errors.push(`docs/pricing.md: Plan "${plan.displayName}" missing limit: "${limit}"`);
      }
    });
  });

  // ── Model pricing validation ──
  const allModels = [
    ...(schema.models.openai || []),
    ...(schema.models.anthropic || []),
  ];

  allModels.forEach(model => {
    const nameRegex = new RegExp(escapeRegex(model.name));
    if (!nameRegex.test(docs)) {
      errors.push(`docs/pricing.md: Missing model "${model.name}" in pricing tables`);
      return;
    }

    // Extract the table row for this model and check prices
    const rowRegex = new RegExp(
      `\\|\\s*${escapeRegex(model.name)}\\s*\\|\\s*\\$([\\d.]+)\\s*\\|\\s*\\$([\\d.]+)\\s*\\|`
    );
    const match = docs.match(rowRegex);
    if (match) {
      const docInput = parseFloat(match[1]);
      const docOutput = parseFloat(match[2]);
      if (Math.abs(docInput - model.inputPer1M) > 0.001) {
        errors.push(`docs/pricing.md: Model "${model.name}" input price is $${match[1]}, expected ${fmtPrice(model.inputPer1M)}`);
      }
      if (Math.abs(docOutput - model.outputPer1M) > 0.001) {
        errors.push(`docs/pricing.md: Model "${model.name}" output price is $${match[2]}, expected ${fmtPrice(model.outputPer1M)}`);
      }
    } else {
      errors.push(`docs/pricing.md: Could not parse pricing row for model "${model.name}"`);
    }
  });

  // ── Execution pricing validation ──
  (schema.executionPricing || []).forEach(item => {
    const priceStr = fmtPrice(item.price);
    const rowRegex = new RegExp(
      `\\|\\s*${escapeRegex(item.action)}\\s*\\|\\s*\\$[\\d.]+\\s*\\|`
    );
    const match = docs.match(rowRegex);
    if (!match) {
      errors.push(`docs/pricing.md: Missing execution pricing row for "${item.action}"`);
    } else {
      const priceMatch = match[0].match(/\$[\d.]+/g);
      if (priceMatch) {
        const docPrice = parseFloat(priceMatch[0].replace('$', ''));
        if (Math.abs(docPrice - item.price) > 0.001) {
          errors.push(`docs/pricing.md: Execution "${item.action}" price is $${docPrice.toFixed(2)}, expected ${priceStr}`);
        }
      }
    }
  });

  // ── Volume discounts validation ──
  (schema.volumeDiscounts || []).forEach(tier => {
    if (tier.discount === null) {
      // Custom tier — just check "Custom" or "contact sales" appears
      if (!/custom.*contact.*sales/i.test(docs) && !/contact.*sales/i.test(docs)) {
        errors.push(`docs/pricing.md: Missing "Custom (contact sales)" volume discount tier`);
      }
      return;
    }
    if (tier.discount === 0) return; // The 0% tier (under 1M) just shows "--"

    const pctStr = `${Math.round(tier.discount * 100)}%`;
    if (!docs.includes(pctStr)) {
      errors.push(`docs/pricing.md: Missing volume discount "${pctStr}"`);
    }
  });

  return errors;
}

function checkComponent(schema) {
  const component = fs.readFileSync(COMPONENT_PATH, 'utf8');
  const errors = [];

  schema.plans.forEach(plan => {
    // Check tier name
    const nameRegex = new RegExp(`name:\\s*"${escapeRegex(plan.displayName)}"`, 'i');
    if (!nameRegex.test(component)) {
      errors.push(`Pricing.tsx: Missing tier name "${plan.displayName}"`);
      return;
    }

    // Check price
    const priceRegex = new RegExp(`price:\\s*"${escapeRegex(plan.priceDisplay)}"`, 'i');
    if (!priceRegex.test(component)) {
      errors.push(`Pricing.tsx: Plan "${plan.displayName}" price should be "${plan.priceDisplay}"`);
    }

    // Check period
    if (plan.period !== undefined) {
      const periodRegex = new RegExp(`period:\\s*"${escapeRegex(plan.period)}"`, 'i');
      if (!periodRegex.test(component)) {
        errors.push(`Pricing.tsx: Plan "${plan.displayName}" period should be "${plan.period}"`);
      }
    }

    // Check features
    plan.features.forEach(feature => {
      if (!component.includes(feature)) {
        // Try with escaped quotes
        const featureEscaped = feature.replace(/"/g, '\\"');
        if (!component.includes(featureEscaped)) {
          errors.push(`Pricing.tsx: Plan "${plan.displayName}" missing feature: "${feature}"`);
        }
      }
    });

    // Check limits
    plan.limits.forEach(limit => {
      if (!component.includes(limit)) {
        errors.push(`Pricing.tsx: Plan "${plan.displayName}" missing limit: "${limit}"`);
      }
    });
  });

  return errors;
}

function checkPricingUtils(schema) {
  const utils = fs.readFileSync(PRICING_UTILS_PATH, 'utf8');
  const errors = [];

  const allModels = [
    ...(schema.models.openai || []),
    ...(schema.models.anthropic || []),
  ];

  allModels.forEach(model => {
    // Check model name exists
    const nameRegex = new RegExp(`name:\\s*"${escapeRegex(model.name)}"`);
    if (!nameRegex.test(utils)) {
      errors.push(`pricing-utils.ts: Missing model "${model.name}"`);
      return;
    }

    // Extract the model entry and check input/output prices
    // Match pattern: { name: "Model", input: X.XX, output: X.XX, provider: "..." }
    const entryRegex = new RegExp(
      `\\{\\s*name:\\s*"${escapeRegex(model.name)}"\\s*,\\s*input:\\s*([\\d.]+)\\s*,\\s*output:\\s*([\\d.]+)`
    );
    const match = utils.match(entryRegex);
    if (match) {
      const utilsInput = parseFloat(match[1]);
      const utilsOutput = parseFloat(match[2]);
      if (Math.abs(utilsInput - model.inputPer1M) > 0.001) {
        errors.push(`pricing-utils.ts: Model "${model.name}" input price is ${match[1]}, expected ${model.inputPer1M}`);
      }
      if (Math.abs(utilsOutput - model.outputPer1M) > 0.001) {
        errors.push(`pricing-utils.ts: Model "${model.name}" output price is ${match[2]}, expected ${model.outputPer1M}`);
      }
    } else {
      errors.push(`pricing-utils.ts: Could not parse entry for model "${model.name}"`);
    }
  });

  return errors;
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function runSelfTest() {
  console.log('Running self-test...\n');

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'pricing-validate-'));
  const tmpSchema = path.join(tmpDir, 'pricing.schema.json');
  let passed = 0;
  let failed = 0;

  // Load original schema
  const originalSchema = loadSchema();

  // Test 1: Original schema should pass with current files
  {
    const docsErrors = checkDocs(originalSchema);
    const componentErrors = checkComponent(originalSchema);
    const utilsErrors = checkPricingUtils(originalSchema);
    const all = [...docsErrors, ...componentErrors, ...utilsErrors];
    if (all.length === 0) {
      console.log('  PASS: Current files are consistent with schema');
      passed++;
    } else {
      console.log('  FAIL: Current files have drift (fix drift before self-test):');
      all.forEach(e => console.log(`    - ${e}`));
      failed++;
    }
  }

  // Test 2: Mutated Pro price should be detected
  {
    const mutated = JSON.parse(JSON.stringify(originalSchema));
    mutated.plans[1].priceDisplay = '$99';
    mutated.plans[1].price = 99;
    const docsErrors = checkDocs(mutated);
    const componentErrors = checkComponent(mutated);
    const hasPriceError = [...docsErrors, ...componentErrors].some(
      e => e.includes('price') && e.includes('Pro')
    );
    if (hasPriceError) {
      console.log('  PASS: Detected Pro price mutation ($49 -> $99)');
      passed++;
    } else {
      console.log('  FAIL: Did not detect Pro price mutation');
      failed++;
    }
  }

  // Test 3: Mutated model price should be detected
  {
    const mutated = JSON.parse(JSON.stringify(originalSchema));
    mutated.models.openai[0].inputPer1M = 9.99;
    const docsErrors = checkDocs(mutated);
    const utilsErrors = checkPricingUtils(mutated);
    const hasModelError = [...docsErrors, ...utilsErrors].some(
      e => e.includes('GPT-4.1 Nano') && e.includes('input')
    );
    if (hasModelError) {
      console.log('  PASS: Detected model price mutation (GPT-4.1 Nano input)');
      passed++;
    } else {
      console.log('  FAIL: Did not detect model price mutation');
      failed++;
    }
  }

  // Test 4: Missing model should be detected
  {
    const mutated = JSON.parse(JSON.stringify(originalSchema));
    mutated.models.anthropic.push({ name: 'Claude Phantom 9', inputPer1M: 1.0, outputPer1M: 5.0 });
    const docsErrors = checkDocs(mutated);
    const utilsErrors = checkPricingUtils(mutated);
    const hasMissing = [...docsErrors, ...utilsErrors].some(
      e => e.includes('Claude Phantom 9')
    );
    if (hasMissing) {
      console.log('  PASS: Detected missing model (Claude Phantom 9)');
      passed++;
    } else {
      console.log('  FAIL: Did not detect missing model');
      failed++;
    }
  }

  // Cleanup
  try { fs.rmSync(tmpDir, { recursive: true }); } catch (e) { /* ignore */ }

  console.log(`\nSelf-test: ${passed} passed, ${failed} failed`);
  process.exit(failed > 0 ? 1 : 0);
}

function main() {
  if (process.argv.includes('--self-test')) {
    return runSelfTest();
  }

  console.log('Validating pricing consistency...\n');

  let schema;
  try {
    schema = loadSchema();
  } catch (err) {
    console.error(`ERROR: Could not load ${SCHEMA_PATH}`);
    console.error(err.message);
    process.exit(1);
  }

  const docsErrors = checkDocs(schema);
  const componentErrors = checkComponent(schema);
  const utilsErrors = checkPricingUtils(schema);

  const allErrors = [...docsErrors, ...componentErrors, ...utilsErrors];

  if (allErrors.length === 0) {
    console.log('✓ Pricing is consistent across schema, docs, site component, and pricing-utils');
    process.exit(0);
  } else {
    console.log('✗ Pricing drift detected:\n');
    allErrors.forEach(err => console.log(`  - ${err}`));
    console.log('\nFix drift by updating files to match pricing.schema.json');
    process.exit(1);
  }
}

main();
