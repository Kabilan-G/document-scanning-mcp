import os
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Optional
import re
from typing import List
import asyncio
import logging
import time

# Load .env manually
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())

# Config
mcp = FastMCP(name='Code Review Server')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions')
MODEL = os.environ.get('OPENAI_MODEL', 'models/gemini-2.5-flash ')


# LLM Helper
async def call_llm(prompt: str) -> str:
    if not OPENAI_API_KEY:
        return 'Error: OPENAI_API_KEY is not set. Add it to your .env file.'
    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': MODEL,
        'messages': [
            {
                'role': 'system',
                'content': ('You are an expert code reviewer. '
                            'Provide structured, actionable feedback. '
                            'Format: Summary, Issues (numbered), Recommendations.')
            },
            {'role': 'user', 'content': prompt}
        ],
        'temperature': 0.2
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(BASE_URL, headers=headers, json=payload, timeout=120.0)
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content']
    except httpx.HTTPStatusError as e:
        return f'HTTP Error {e.response.status_code}: {e.response.text}'
    except httpx.TimeoutException:
        return 'Error: Request timed out. Please try again.'
    except Exception as e:
        return f'Unexpected error: {str(e)}'


# Tool 1: Review a code snippet
@mcp.tool()
async def review_code(code: str, language: str = 'python', context=None) -> str:
    '''Review a code snippet for quality, bugs, security issues, and best practices.
    Args:
        code: The source code to review
        language: Programming language (python, apex, javascript, etc.)
        context: Optional context about what the code is supposed to do
    '''
    context_section = f'\nContext: {context}' if context else ''
    prompt = (f'Review this {language} code:{context_section}\n\n'
              f'```{language}\n{code}\n```\n\n'
              'Check for:\n'
              '1. Bugs and logical errors\n'
              '2. Security vulnerabilities\n'
              '3. Performance issues\n'
              '4. Code style and best practices\n'
              '5. Missing error handling\n'
              '6. Naming conventions\n'
              'Be specific with line references where possible.')
    return await call_llm(prompt)


# Tool 2: Review a file from disk
@mcp.tool()
async def review_file(file_path: str, language=None) -> str:
    '''Read a source file from disk and review it.
    Args:
        file_path: Absolute or relative path to the file
        language: Language hint (auto-detected from extension if not provided)
    '''
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
    except FileNotFoundError:
        return f'Error: File not found at path: {file_path}'
    except PermissionError:
        return f'Error: Permission denied reading file: {file_path}'
    except Exception as e:
        return f'Error reading file: {str(e)}'
    if not language:
        ext_map = {
            '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
            '.cls': 'apex', '.trigger': 'apex', '.html': 'html',
            '.css': 'css', '.java': 'java', '.json': 'json', '.xml': 'xml'
        }
        ext = '.' + file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else ''
        language = ext_map.get(ext, 'text')
    return await review_code(code=code, language=language)


# Tool 3: Suggest a refactor
@mcp.tool()
async def suggest_refactor(code: str, language: str = 'python', goal=None) -> str:
    '''Suggest a refactored version of the given code.
    Args:
        code: The source code to refactor
        language: Programming language
        goal: Optional refactoring goal (e.g., improve readability, add error handling)
    '''
    goal_section = f'\nRefactoring goal: {goal}' if goal else ''
    prompt = (f'Refactor this {language} code to be cleaner and more maintainable.{goal_section}\n\n'
              f'Original code:\n```{language}\n{code}\n```\n\n'
              'Provide:\n'
              '1. The refactored code in a code block\n'
              '2. A brief explanation of each change made\n'
              '3. Any trade-offs or assumptions made')
    return await call_llm(prompt)


# Tool 4: Explain code
@mcp.tool()
async def explain_code(code: str, language: str = 'python', audience: str = 'developer') -> str:
    '''Explain what a piece of code does in plain language.
    Args:
        code: The source code to explain
        language: Programming language
        audience: Target audience - developer, junior, or non-technical
    '''
    prompt = (f'Explain this {language} code for a {audience} audience:\n\n'
              f'```{language}\n{code}\n```\n\n'
              'Include:\n'
              '1. What the code does overall (1-2 sentences)\n'
              '2. Step-by-step breakdown of the logic\n'
              '3. Any important patterns or concepts used')
    return await call_llm(prompt)


# Tool 5: Generate unit tests
@mcp.tool()
async def generate_tests(code: str, language: str = 'python', framework=None) -> str:
    '''Generate unit tests for a given function or class.
    Args:
        code: The source code to generate tests for
        language: Programming language
        framework: Test framework e.g. pytest, jest, junit, apex. Auto-selected if not provided.
    '''
    if not framework:
        defaults = {'python': 'pytest', 'javascript': 'jest', 'typescript': 'jest',
                    'java': 'junit', 'apex': 'Apex test class'}
        framework = defaults.get(language.lower(), 'appropriate test framework')
    prompt = (f'Generate comprehensive unit tests for this {language} code using {framework}:\n\n'
              f'```{language}\n{code}\n```\n\n'
              'Include:\n'
              '1. Happy path tests\n'
              '2. Edge case tests\n'
              '3. Error and exception handling tests\n'
              '4. Brief comments explaining each test purpose')
    return await call_llm(prompt)

def split_apex_into_blocks(code: str) -> List[dict]:
    """
    Split Apex code into logical blocks by method and inner class boundaries.
    Returns list of dicts with 'type', 'name', and 'code' keys.
    """
    blocks = []
    lines = code.split('\n')

    # Extract class header (annotations, class declaration, properties)
    header_lines = []
    class_body_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Detect start of first method or inner class
        if re.match(
            r'(public|private|protected|global|override|static|virtual|abstract)'
            r'.*\s+(void|String|Integer|Boolean|List|Map|Set|Id|SObject|Object|'
            r'[A-Z][a-zA-Z]+)\s+\w+\s*\(',
            stripped
        ) or re.match(r'(public|private|global)\s+(class|interface|enum)\s+\w+', stripped):
            class_body_start = i
            break
        header_lines.append(line)

    class_header = '\n'.join(header_lines)

    # Now extract individual methods and inner classes
    current_block_lines = []
    current_block_name = 'unknown'
    current_block_type = 'method'
    brace_depth = 0
    in_block = False

    for line in lines[class_body_start:]:
        stripped = line.strip()

        # Detect method signature
        method_match = re.match(
            r'(?:(?:public|private|protected|global|override|static|'
            r'virtual|abstract|testMethod|@\w+)\s+)*'
            r'(?:void|String|Integer|Boolean|List|Map|Set|Id|SObject|Object|[A-Z][a-zA-Z]+)'
            r'\s+(\w+)\s*\(',
            stripped
        )

        # Detect inner class
        inner_class_match = re.match(
            r'(?:public|private|global)\s+(?:class|interface|enum)\s+(\w+)',
            stripped
        )

        if (method_match or inner_class_match) and brace_depth == 0:
            # Save previous block
            if current_block_lines:
                blocks.append({
                    'type': current_block_type,
                    'name': current_block_name,
                    'code': class_header + '\n\n' + '\n'.join(current_block_lines)
                })
            current_block_lines = []
            current_block_name = (
                method_match.group(1) if method_match
                else inner_class_match.group(1)
            )
            current_block_type = 'inner_class' if inner_class_match else 'method'
            in_block = True

        if in_block:
            current_block_lines.append(line)

        brace_depth += line.count('{') - line.count('}')

        # Block ends when braces are balanced
        if in_block and brace_depth == 0 and current_block_lines:
            blocks.append({
                'type': current_block_type,
                'name': current_block_name,
                'code': class_header + '\n\n' + '\n'.join(current_block_lines)
            })
            current_block_lines = []
            current_block_name = 'unknown'
            in_block = False

    # Catch any remaining lines
    if current_block_lines:
        blocks.append({
            'type': current_block_type,
            'name': current_block_name,
            'code': class_header + '\n\n' + '\n'.join(current_block_lines)
        })

    return blocks if blocks else [{'type': 'full', 'name': 'full_class', 'code': code}]


# ── Logging setup ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

MAX_BLOCK_CHARS = 6000  # ~1500 tokens per block

# ── Tool 6: Review large Apex file ───────────────────────

# ── Error classification helpers ─────────────────────────

def is_llm_error(response: str) -> bool:
    """Check if response is any kind of error."""
    error_prefixes = (
        "HTTP Error", "Error:", "Unexpected error",
        "Request timed out", "API Error"
    )
    return any(response.strip().startswith(p) for p in error_prefixes)


def is_quota_error(response: str) -> bool:
    """Check if error is a quota/rate limit — do NOT retry these."""
    quota_signals = (
        "429", "quota", "RESOURCE_EXHAUSTED", "rate limit",
        "rate_limit", "too many requests", "exceeded",
        "dailylimitexceeded", "usagelimitexceeded", "billing"
    )
    lower = response.lower()
    return any(signal.lower() in lower for signal in quota_signals)


def is_timeout_error(response: str) -> bool:
    """Check if error is a timeout — safe to retry."""
    return "timed out" in response.lower() or "timeout" in response.lower()


def format_error_report(step: str, response: str, file_path: str,
                         elapsed: float, blocks_found: int = 0) -> str:
    """Format a clean, informative error report based on error type."""
    if is_quota_error(response):
        error_type = "🚫 API Quota Exceeded"
        advice = (
            "- Your Google API free quota has been exhausted\n"
            "- **Do not retry** — repeated calls will not succeed until quota resets\n"
            "- Free tier resets daily — try again tomorrow\n"
            "- Or upgrade to a paid tier at [aistudio.google.com](https://aistudio.google.com)\n"
            "- Consider reviewing smaller files or individual methods to reduce token usage"
        )
    elif is_timeout_error(response):
        error_type = "⏱️ Request Timed Out"
        advice = (
            "- The LLM took too long to respond\n"
            "- Try with a smaller file or pass a specific `focus` to reduce scope\n"
            "- Gemini may be under load — retry in a moment"
        )
    elif "401" in response or "403" in response:
        error_type = "🔑 Authentication Failed"
        advice = (
            "- Your API key is invalid or expired\n"
            "- Regenerate your key at [aistudio.google.com](https://aistudio.google.com)\n"
            "- Update `OPENAI_API_KEY` in your `.env` file and restart the server"
        )
    elif "404" in response:
        error_type = "🔍 Endpoint Not Found"
        advice = (
            "- The `OPENAI_BASE_URL` in your `.env` is incorrect\n"
            "- Correct URL: `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`"
        )
    else:
        error_type = "❌ Unexpected LLM Error"
        advice = (
            "- Check your API key and base URL in `.env`\n"
            "- Try again in a few seconds\n"
            "- Try with a smaller file to isolate the issue"
        )

    return (
        f"# {error_type}\n\n"
        f"**Failed at step:** {step}  \n"
        f"**File:** `{file_path}`  \n"
        f"**Failed after:** {elapsed:.1f}s  \n"
        f"**Blocks identified before failure:** {blocks_found}\n\n"
        f"## Error Details\n\n"
        f"```\n{response}\n```\n\n"
        f"## Suggested Actions\n\n"
        f"{advice}"
    )


# ── Tool 6: Review large Apex file ───────────────────────
@mcp.tool()
async def review_large_apex_file(
    file_path: str,
    focus: Optional[str] = None
) -> str:
    """
    Review a large Apex file by:
    1. Generating a method inventory with descriptions
    2. Doing a holistic class-level review
    3. Reviewing each block in parallel
    4. Producing an overall summary

    Args:
        file_path: Path to the .cls or .trigger Apex file
        focus: Optional focus e.g. 'governor limits', 'bulkification'
    """
    start_time = time.time()
    logger.info(f"Starting review: {file_path}")

    # ── Read file ──────────────────────────────────────────
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return (
            f"# ❌ File Not Found\n\n"
            f"`{file_path}` does not exist. Check the path and try again."
        )
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return f"# ❌ File Read Error\n\n```\n{str(e)}\n```"

    total_lines = len(code.split('\n'))
    total_chars = len(code)
    blocks = split_apex_into_blocks(code)
    focus_note = f"\nPay special attention to: {focus}" if focus else ""

    logger.info(f"File stats: {total_lines} lines, {total_chars} chars, {len(blocks)} blocks found")
    for i, block in enumerate(blocks, 1):
        logger.info(
            f"  Block {i}: [{block['type']}] {block['name']} "
            f"— {len(block['code'].split(chr(10)))} lines"
        )

    # ── Step 1: Inventory + holistic review (parallel) ─────
    logger.info("Step 1: Generating method inventory and holistic review...")

    inventory_prompt = (
        f"Analyze this Apex class and produce a METHOD INVENTORY.\n\n"
        f"```apex\n{code[:8000]}\n```\n"
        f"{'[File truncated for inventory]' if len(code) > 8000 else ''}\n\n"
        "For each method/inner class found, provide:\n"
        "- Method name\n"
        "- Visibility (public/private/global)\n"
        "- Return type\n"
        "- One-line description of what it does\n"
        "- Any obvious concerns (e.g. 'contains SOQL', 'DML operation', 'recursive risk')\n\n"
        "Format as a markdown table: Method | Visibility | Returns | Description | Concerns"
    )

    holistic_prompt = (
        f"Review this Apex class AS A WHOLE — focus on overall design and architecture.{focus_note}\n\n"
        f"```apex\n{code[:8000]}\n```\n"
        f"{'[File truncated — focus on what is visible]' if len(code) > 8000 else ''}\n\n"
        "Evaluate:\n"
        "1. Overall class responsibility — is it doing too much? (Single Responsibility)\n"
        "2. Cross-method concerns — shared state risks, field usage patterns\n"
        "3. Trigger handler pattern compliance (if this is a trigger handler)\n"
        "4. Test coverage strategy — is it testable as designed?\n"
        "5. Dependency risks — hardcoded IDs, org-specific assumptions\n"
        "Keep to 5-7 key observations."
    )

    inventory_result, holistic_result = await asyncio.gather(
        call_llm(inventory_prompt),
        call_llm(holistic_prompt)
    )

    # Fail fast on Step 1 errors — no point continuing
    for label, result in [("Method Inventory", inventory_result),
                           ("Holistic Review", holistic_result)]:
        if is_llm_error(result):
            elapsed = time.time() - start_time
            logger.error(f"Step 1 failed [{label}]: {result}")
            return format_error_report(
                f"Step 1 — {label}", result, file_path, elapsed, len(blocks)
            )

    logger.info("Step 1 complete ✅")

    # ── Step 2: Per-block reviews in parallel ──────────────
    logger.info(f"Step 2: Reviewing {len(blocks)} blocks in parallel...")

    semaphore = asyncio.Semaphore(3)

    async def review_block(block, index):
        block_start = time.time()
        code_chunk = block['code']
        truncated_note = ""
        if len(code_chunk) > MAX_BLOCK_CHARS:
            code_chunk = code_chunk[:MAX_BLOCK_CHARS]
            truncated_note = "\n[Note: Block truncated to fit token limit]"

        prompt = (
            f"Review this Apex {block['type']} named '{block['name']}'. "
            f"Block {index} of {len(blocks)}.{focus_note}{truncated_note}\n\n"
            f"```apex\n{code_chunk}\n```\n\n"
            "Check specifically:\n"
            "1. Governor limit violations (SOQL/DML inside loops)\n"
            "2. Bulkification issues\n"
            "3. Missing null checks\n"
            "4. Security (CRUD/FLS checks)\n"
            "5. Error handling\n"
            "6. How this method interacts with others in the class\n"
            "Be concise — 3-5 key findings max."
        )

        async with semaphore:
            result = await call_llm(prompt)

        elapsed = time.time() - block_start
        if is_llm_error(result):
            # Log quota errors differently — flag them prominently
            if is_quota_error(result):
                logger.error(
                    f"  Block {index} '{block['name']}' — QUOTA EXCEEDED. "
                    f"Stopping further reviews."
                )
            else:
                logger.warning(
                    f"  Block {index} '{block['name']}' failed in {elapsed:.1f}s: {result}"
                )
        else:
            logger.info(f"  Block {index} '{block['name']}' reviewed in {elapsed:.1f}s ✅")

        return result

    block_reviews = await asyncio.gather(
        *[review_block(block, i+1) for i, block in enumerate(blocks)]
    )

    # Check for quota error in any block — abort immediately with clear message
    for i, review in enumerate(block_reviews):
        if is_quota_error(review):
            elapsed = time.time() - start_time
            successful = sum(1 for r in block_reviews if not is_llm_error(r))
            logger.error(
                f"Quota exceeded during block reviews. "
                f"{successful}/{len(blocks)} blocks completed before failure."
            )
            return format_error_report(
                f"Step 2 — Block Review (quota hit on block {i+1} "
                f"'{blocks[i]['name']}', {successful}/{len(blocks)} completed)",
                review, file_path, elapsed, len(blocks)
            )

    # Count other (non-quota) failures — partial success is okay
    failed_blocks = [
        (i+1, blocks[i]['name'], r)
        for i, r in enumerate(block_reviews)
        if is_llm_error(r)
    ]
    successful_count = len(blocks) - len(failed_blocks)

    if failed_blocks:
        logger.warning(
            f"{len(failed_blocks)} block(s) failed (non-quota), "
            f"continuing with {successful_count} successful"
        )

    logger.info("Step 2 complete ✅")

    # ── Step 3: Final summary ──────────────────────────────
    logger.info("Step 3: Generating final summary...")

    # Only include successful block reviews in summary
    combined_findings = '\n\n'.join(
        f"[{b['type']}] {b['name']}:\n{r}"
        for b, r in zip(blocks, block_reviews)
        if not is_llm_error(r)
    )

    summary_prompt = (
        f"You reviewed {successful_count} of {len(blocks)} blocks "
        f"of an Apex class at '{file_path}'.\n\n"
        f"Block findings:\n{combined_findings[:4000]}\n\n"
        f"Holistic review:\n{holistic_result[:1000]}\n\n"
        "Produce a FINAL REVIEW REPORT:\n"
        "1. **Critical Issues** (must fix before deployment)\n"
        "2. **Major Issues** (should fix soon)\n"
        "3. **Minor Issues** (nice to fix)\n"
        "4. **Overall Quality Score** (1-10 with justification)\n"
        "5. **Top Refactoring Recommendation**\n"
        "6. **Positive Observations**"
    )

    summary = await call_llm(summary_prompt)
    if is_llm_error(summary):
        elapsed = time.time() - start_time
        logger.error(f"Step 3 failed: {summary}")
        return format_error_report(
            "Step 3 — Final Summary", summary, file_path, elapsed, len(blocks)
        )

    logger.info("Step 3 complete ✅")

    # ── Assemble report ────────────────────────────────────
    total_elapsed = time.time() - start_time
    logger.info(f"Review complete in {total_elapsed:.1f}s ✅")

    # Warning note if some blocks failed
    warning_note = ""
    if failed_blocks:
        warning_note = (
            f"\n> ⚠️ **Warning:** {len(failed_blocks)} block(s) could not be reviewed: "
            + ", ".join(f"`{name}`" for _, name, _ in failed_blocks)
        )

    report = []
    report.append(
        f"# 📋 Apex Code Review Report\n"
        f"**File:** `{file_path}`  \n"
        f"**Lines:** {total_lines} | "
        f"**Blocks:** {successful_count}/{len(blocks)} reviewed | "
        f"**Time:** {total_elapsed:.1f}s"
        f"{warning_note}\n"
        f"{'─' * 60}"
    )
    report.append(f"\n## 🗂️ Method Inventory\n\n{inventory_result}")
    report.append(f"\n## 🏗️ Holistic Class Review\n\n{holistic_result}")
    report.append(f"\n## 🔍 Block-by-Block Review\n")

    for i, (block, review) in enumerate(zip(blocks, block_reviews), 1):
        block_lines = len(block['code'].split('\n'))
        if is_llm_error(review):
            status = "❌ Failed"
            content = f"> ⚠️ Could not review this block: `{review}`"
        else:
            status = "✅"
            content = review

        report.append(
            f"\n### Block {i}/{len(blocks)}: `{block['name']}` "
            f"({block['type']}, {block_lines} lines) {status}\n\n{content}"
        )

    report.append(f"\n{'─' * 60}\n## ✅ Final Review Summary\n\n{summary}")

    return '\n'.join(report)

def make_prompt(block, i):
    code = block['code']
    truncated = ""
    if len(code) > MAX_BLOCK_CHARS:
        code = code[:MAX_BLOCK_CHARS]
        truncated = "\n[Note: Block truncated to fit token limit]"
    return (
        f"Review this Apex {block['type']} '{block['name']}'{truncated}\n\n"
        f"```apex\n{code}\n```\n\n"
        "Check for governor limits, bulkification, null checks, security, error handling.\n"
        "Be concise — 3-5 findings max."
    )

# Entry point
if __name__ == '__main__':
    mcp.run(transport='stdio')