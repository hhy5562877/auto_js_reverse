/**
 * Browser Insight Node.js Worker - JS 解析与 Source Map 还原
 *
 * 通信协议: stdin/stdout JSON 行协议
 * 输入: { "command": "parse", "files": [...] }
 * 输出: { "status": "success"|"error", "results": [...] }
 *
 * 这是混合架构的核心解析引擎，利用 V8 原生能力处理 JS AST 和 Source Map。
 */

const fs = require('fs');
const path = require('path');
const acorn = require('acorn');
const walk = require('acorn-walk');

const LARGE_FILE_THRESHOLD = 5 * 1024 * 1024; // 5MB
const LINE_CHUNK_SIZE = 200;

let SourceMapConsumer = null;

async function initSourceMap() {
    if (SourceMapConsumer) return;
    const sourceMap = await import('source-map');
    SourceMapConsumer = sourceMap.SourceMapConsumer;
}

function chunkByLines(code, chunkSize) {
    const lines = code.split('\n');
    const chunks = [];
    for (let i = 0; i < lines.length; i += chunkSize) {
        const slice = lines.slice(i, i + chunkSize);
        chunks.push({
            content: slice.join('\n'),
            lineStart: i + 1,
            lineEnd: Math.min(i + chunkSize, lines.length)
        });
    }
    return chunks;
}

function extractSemanticChunks(code) {
    let ast;
    try {
        ast = acorn.parse(code, {
            ecmaVersion: 'latest',
            sourceType: 'module',
            locations: true,
            allowHashBang: true,
            allowImportExportEverywhere: true,
            allowReturnOutsideFunction: true,
        });
    } catch {
        try {
            ast = acorn.parse(code, {
                ecmaVersion: 'latest',
                sourceType: 'script',
                locations: true,
                allowHashBang: true,
                allowReturnOutsideFunction: true,
            });
        } catch {
            return chunkByLines(code, LINE_CHUNK_SIZE);
        }
    }

    const lines = code.split('\n');
    const chunks = [];
    const coveredRanges = [];

    function extractNode(node) {
        if (!node.loc) return;
        const lineStart = node.loc.start.line;
        const lineEnd = node.loc.end.line;
        const content = lines.slice(lineStart - 1, lineEnd).join('\n');
        if (content.trim().length > 0) {
            chunks.push({ content, lineStart, lineEnd });
            coveredRanges.push([lineStart, lineEnd]);
        }
    }

    walk.simple(ast, {
        FunctionDeclaration: extractNode,
        ClassDeclaration: extractNode,
        VariableDeclaration(node) {
            if (!node.declarations) return;
            for (const decl of node.declarations) {
                if (decl.init && (
                    decl.init.type === 'FunctionExpression' ||
                    decl.init.type === 'ArrowFunctionExpression' ||
                    decl.init.type === 'ClassExpression'
                )) {
                    extractNode(node);
                    return;
                }
            }
        },
        ExportNamedDeclaration(node) {
            if (node.declaration) extractNode(node);
        },
        ExportDefaultDeclaration(node) {
            if (node.declaration) extractNode(node);
        },
        MethodDefinition: extractNode,
    });

    if (chunks.length === 0) {
        return chunkByLines(code, LINE_CHUNK_SIZE);
    }

    coveredRanges.sort((a, b) => a[0] - b[0]);
    const uncoveredChunks = [];
    let lastEnd = 0;
    for (const [start, end] of coveredRanges) {
        if (start > lastEnd + 1) {
            const gapContent = lines.slice(lastEnd, start - 1).join('\n').trim();
            if (gapContent.length > 50) {
                uncoveredChunks.push({
                    content: gapContent,
                    lineStart: lastEnd + 1,
                    lineEnd: start - 1
                });
            }
        }
        lastEnd = Math.max(lastEnd, end);
    }
    if (lastEnd < lines.length) {
        const tailContent = lines.slice(lastEnd).join('\n').trim();
        if (tailContent.length > 50) {
            uncoveredChunks.push({
                content: tailContent,
                lineStart: lastEnd + 1,
                lineEnd: lines.length
            });
        }
    }

    return [...chunks, ...uncoveredChunks].sort((a, b) => a.lineStart - b.lineStart);
}

async function restoreWithSourceMap(code, mapPath) {
    let rawMap;
    try {
        rawMap = JSON.parse(fs.readFileSync(mapPath, 'utf-8'));
    } catch {
        return null;
    }

    await initSourceMap();
    let consumer;
    try {
        consumer = await new SourceMapConsumer(rawMap);
    } catch {
        return null;
    }

    const restoredFiles = new Map();

    try {
        consumer.eachMapping((mapping) => {
            if (!mapping.source) return;
            if (!restoredFiles.has(mapping.source)) {
                const sourceContent = consumer.sourceContentFor(mapping.source, true);
                restoredFiles.set(mapping.source, {
                    originalFile: mapping.source,
                    content: sourceContent || null,
                });
            }
        });
    } finally {
        consumer.destroy();
    }

    const results = [];
    for (const [sourceName, info] of restoredFiles) {
        if (info.content) {
            const chunks = (Buffer.byteLength(info.content) > LARGE_FILE_THRESHOLD)
                ? chunkByLines(info.content, LINE_CHUNK_SIZE)
                : extractSemanticChunks(info.content);
            results.push({
                originalFile: sourceName,
                sourceMapRestored: true,
                chunks
            });
        }
    }

    return results.length > 0 ? results : null;
}

async function processFile(fileInfo) {
    const { path: filePath, mapPath, url } = fileInfo;

    let code;
    try {
        code = fs.readFileSync(filePath, 'utf-8');
    } catch (err) {
        return {
            error: `Failed to read file: ${err.message}`,
            url,
            results: []
        };
    }

    if (mapPath) {
        try {
            const restored = await restoreWithSourceMap(code, mapPath);
            if (restored && restored.length > 0) {
                return { url, results: restored };
            }
        } catch {
            // 降级：Source Map 解析失败，继续用混淆代码
        }
    }

    const isLarge = Buffer.byteLength(code) > LARGE_FILE_THRESHOLD;
    const chunks = isLarge ? chunkByLines(code, LINE_CHUNK_SIZE) : extractSemanticChunks(code);

    return {
        url,
        results: [{
            originalFile: url || path.basename(filePath),
            sourceMapRestored: false,
            chunks
        }]
    };
}

async function handleCommand(input) {
    if (input.command === 'parse') {
        const files = input.files || [];
        const allResults = [];
        for (const fileInfo of files) {
            try {
                const result = await processFile(fileInfo);
                allResults.push(result);
            } catch (err) {
                allResults.push({
                    url: fileInfo.url,
                    error: err.message,
                    results: []
                });
            }
        }
        return { status: 'success', results: allResults };
    }

    if (input.command === 'ping') {
        return { status: 'success', message: 'pong' };
    }

    return { status: 'error', message: `Unknown command: ${input.command}` };
}

let buffer = '';

process.stdin.setEncoding('utf-8');
process.stdin.on('data', async (chunk) => {
    buffer += chunk;
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        let input;
        try {
            input = JSON.parse(trimmed);
        } catch {
            const errResp = { status: 'error', message: 'Invalid JSON input' };
            process.stdout.write(JSON.stringify(errResp) + '\n');
            continue;
        }

        try {
            const result = await handleCommand(input);
            process.stdout.write(JSON.stringify(result) + '\n');
        } catch (err) {
            const errResp = { status: 'error', message: err.message };
            process.stdout.write(JSON.stringify(errResp) + '\n');
        }
    }
});

process.stdin.on('end', () => {
    process.exit(0);
});

process.on('uncaughtException', (err) => {
    const errResp = { status: 'error', message: `Uncaught: ${err.message}` };
    process.stdout.write(JSON.stringify(errResp) + '\n');
});
