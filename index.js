/**
 * learn-skill — minimal dsh bundle shim.
 *
 * The only code this package ships. Registers a read-only skill provider on
 * `ctx.skills` that serves the SKILL.md bundle at this package root.
 *
 * Deliberate boundaries:
 * - Registers no tools, manages no credentials, performs no network requests.
 * - Injects no resident system prompt: the skill appears in the catalog as
 *   name + description and loads only when invoked (progressive disclosure).
 *
 * The provider follows the same list/get contract as
 * `@deepseek-ai/dsh-skill-filesystem`, so bundled skills behave like
 * filesystem skills: bodies are re-read on each get() and relative
 * references/scripts/ paths resolve against the skill's own directory.
 */

import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const name = 'learn-skill'
export const inject = ['skills']

const PACKAGE_ROOT = fileURLToPath(new URL('./', import.meta.url))
const SKILL_FILE = join(PACKAGE_ROOT, 'SKILL.md')
const PROVIDER_NAME = 'learn-skill'
// Packaged skills rank below project/user/custom roots (100–500) so a user's
// own skill with the same name wins; matches the bundled rank used by
// @deepseek-ai/dsh-skill.
const PACK_RANK = 600
const SKILL_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

const TRUE_FORMS = new Set(['true', 'yes', 'on', '1'])
const FALSE_FORMS = new Set(['false', 'no', 'off', '0'])

/** Parse YAML frontmatter with plain scalars and |/> block scalars. */
function parseSkillText(text) {
  if (typeof text !== 'string' || !text.startsWith('---')) return undefined
  const firstNewline = text.indexOf('\n')
  if (firstNewline < 0) return undefined
  const closing = findClosingFrontmatter(text, firstNewline + 1)
  if (closing < 0) return undefined
  const lines = text.slice(firstNewline + 1, closing).split('\n')
  const fields = Object.create(null)
  let i = 0
  while (i < lines.length) {
    const trimmed = lines[i].trim()
    if (trimmed === '' || trimmed.startsWith('#')) { i += 1; continue }
    const match = /^([A-Za-z0-9_-]+):(.*)$/.exec(trimmed)
    if (match === null) { i += 1; continue }
    const key = match[1]
    const rest = match[2].trim()
    if (rest === '' || rest === '|' || rest === '>') {
      const block = []
      i += 1
      while (i < lines.length && (lines[i].trim() === '' || /^\s+\S/.test(lines[i]))) {
        block.push(lines[i].trim())
        i += 1
      }
      fields[key] = block.join('\n')
    } else {
      fields[key] = rest
      i += 1
    }
  }
  return { fields, body: text.slice(closing + 4).trim() }
}

function findClosingFrontmatter(text, start) {
  let lineStart = start
  while (lineStart <= text.length) {
    const nextNewline = text.indexOf('\n', lineStart)
    const lineEnd = nextNewline < 0 ? text.length : nextNewline
    if (text.slice(lineStart, lineEnd).replace(/\r$/, '') === '---') return lineStart
    if (nextNewline < 0) return -1
    lineStart = nextNewline + 1
  }
  return -1
}

function scalar(value) {
  if (value === undefined) return undefined
  return value.replace(/^(["'])(.*)\1$/, '$2')
}

function parseBoolean(value) {
  const normalized = String(value).trim().toLowerCase()
  if (TRUE_FORMS.has(normalized)) return true
  if (FALSE_FORMS.has(normalized)) return false
  return undefined
}

function parseInvocation(fields) {
  const disabled = parseBoolean(fields['disable-model-invocation'])
  const userInvocable = parseBoolean(fields['user-invocable'])
  return {
    modelInvocable: disabled === undefined ? true : !disabled,
    userInvocable: userInvocable === undefined ? true : userInvocable,
  }
}

function parseMetadata(fields) {
  const metadata = {}
  for (const [key, value] of Object.entries(fields)) {
    if (['name', 'description', 'whenToUse', 'disable-model-invocation', 'user-invocable'].includes(key)) continue
    if (value === undefined) continue
    metadata[key] = value
  }
  return Object.keys(metadata).length === 0 ? undefined : metadata
}

class PackSkillProvider {
  constructor(ctx) {
    this.ctx = ctx
    this.name = PROVIDER_NAME
  }

  async list() {
    const skill = await this.readSkill(SKILL_FILE)
    if (skill === undefined) return []
    if (!SKILL_NAME.test(skill.name)) {
      this.ctx.logger?.warn?.(`${PROVIDER_NAME}: skill ${JSON.stringify(skill.name)} ignored: invalid skill name`)
      return []
    }
    return [{
      name: skill.name,
      description: skill.description,
      ...(skill.whenToUse !== undefined ? { whenToUse: skill.whenToUse } : {}),
      invocation: skill.invocation,
      source: 'bundled',
      provider: PROVIDER_NAME,
      rank: PACK_RANK,
      locator: { dir: PACKAGE_ROOT },
      resourceBase: { kind: 'directory', path: PACKAGE_ROOT },
      path: SKILL_FILE,
      ...(skill.metadata !== undefined ? { metadata: skill.metadata } : {}),
    }]
  }

  async get(candidate) {
    const locator = candidate?.locator
    if (locator === undefined || typeof locator.dir !== 'string') return undefined
    const skill = await this.readSkill(join(locator.dir, 'SKILL.md'))
    if (skill === undefined || skill.name !== candidate.name) return undefined
    return {
      name: skill.name,
      description: skill.description,
      ...(skill.whenToUse !== undefined ? { whenToUse: skill.whenToUse } : {}),
      invocation: skill.invocation,
      source: candidate.source,
      provider: candidate.provider,
      resourceBase: candidate.resourceBase,
      path: candidate.path,
      ...(skill.metadata !== undefined ? { metadata: skill.metadata } : {}),
      content: skill.body,
    }
  }

  async readSkill(file) {
    let raw
    try {
      raw = await readFile(file, 'utf8')
    } catch (error) {
      if (error && typeof error === 'object' && 'code' in error && (error.code === 'ENOENT' || error.code === 'ENOTDIR')) return undefined
      throw error
    }
    const parsed = parseSkillText(raw)
    if (parsed === undefined) return undefined
    const { fields, body } = parsed
    const name = scalar(fields.name)
    const description = scalar(fields.description)
    if (name === undefined || description === undefined || name === '' || description === '') return undefined
    const whenToUse = scalar(fields.whenToUse)
    return {
      name,
      description,
      ...(whenToUse !== undefined ? { whenToUse } : {}),
      invocation: parseInvocation(fields),
      ...(parseMetadata(fields) !== undefined ? { metadata: parseMetadata(fields) } : {}),
      body,
    }
  }
}

export const apply = (ctx) => {
  ctx.skills.registerProvider(() => new PackSkillProvider(ctx))
}

// Parser helpers exported for tests and reuse.
export { parseSkillText, scalar, parseInvocation }
